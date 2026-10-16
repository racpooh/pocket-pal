"""Real-model extraction evaluation, with classification scored separately (docs/design/06 §4).

  uv run python scripts/eval_extraction.py --slug haiku-smoke --limit 5     # smoke test first
  uv run python scripts/eval_extraction.py --slug haiku-synth40             # full synthetic set

Config comes from the shared loader (repo-root .env → FINASSIST_*). Requires FINASSIST_MODEL_PROVIDER=anthropic;
anything else is a ConfigError (no silent mock). The API key is never printed or written.

Guarantees:
- Ground truth is read only AFTER the model call, for scoring. The prompt is a fixed constant whose sha256 is recorded.
- Stops at the first non-retryable provider error (auth, billing/permission, unknown model, bad request); no retries.
- Budget: a UsageMeter refuses any call that could push cumulative spend (ledger in evidence/usage_ledger.jsonl) over the budget.
Outputs: evidence/runs/<UTC>-<slug>/{manifest.json, items.jsonl}  (synthetic data only in this round)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND / "src"))

from finassist.domain import extraction_validation as ev  # noqa: E402
from finassist.domain.classify import is_intermediary, normalize_payee, suggest  # noqa: E402
from finassist.domain.dedup import normalize_ref  # noqa: E402
from finassist.domain.money import format_thb  # noqa: E402
from finassist.providers import (  # noqa: E402
    EXTRACTION_SCHEMA_VERSION, EXTRACTION_SYSTEM, EXTRACTION_TOOL, AnthropicExtractionProvider, BudgetExceeded,
    FatalProviderError, ProviderError, UsageMeter, verify_model_access,
)
from finassist.settings import get_settings  # noqa: E402

LEDGER = REPO / "evidence" / "usage_ledger.jsonl"
SLIPS = BACKEND / "fixtures" / "synthetic" / "slips"
REFERENCE_AT = datetime(2026, 10, 15, 6, 0, tzinfo=timezone.utc)  # 13:00 ICT; same fixed "now" as the demos


def code_version() -> str:
    # Owner rule (16 Oct 2026): no git commands, not even from scripts. Identify code by content_hash().
    return "not queried"


def content_hash() -> str:
    h = hashlib.sha256()
    for p in sorted((BACKEND / "src").rglob("*.py")) + [Path(__file__)]:
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    s = get_settings()
    s.require_real_provider()
    if s.model_provider != "anthropic":
        print("ConfigError: this evaluation needs FINASSIST_MODEL_PROVIDER=anthropic (refusing to run a mock)", file=sys.stderr)
        return 2
    key = s.model_api_key.get_secret_value()
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ") + "-" + a.slug
    try:
        access = verify_model_access(key, s.extraction_model)
    except FatalProviderError as e:
        print(f"STOP before any billed call: {e}", file=sys.stderr)
        return 3
    meter = UsageMeter(budget_usd=s.budget_usd, max_requests=s.max_model_requests, ledger_path=str(LEDGER))
    provider = AnthropicExtractionProvider(key, s.extraction_model, meter=meter, max_output_tokens=s.extraction_max_output_tokens,
                                           max_retries=0, run_id=run_id)

    files = sorted(p.name for p in SLIPS.glob("*.png"))
    if a.limit:
        files = files[: a.limit]
    detail, stop_reason = [], None
    for f in files:
        data = (SLIPS / f).read_bytes()
        rec = {"file": f, "sha256": hashlib.sha256(data).hexdigest()[:16]}
        try:
            res = provider.extract(data, "image/png")  # the model sees only the image + fixed prompt
        except BudgetExceeded as e:
            stop_reason = f"budget: {e}"
            break
        except FatalProviderError as e:
            stop_reason = f"fatal provider error: {e}"
            break
        except ProviderError as e:
            rec["provider_error"] = str(e)
            detail.append(rec)
            continue
        rec.update(model_id=res.model_id, latency_ms=res.latency_ms, input_tokens=res.input_tokens, output_tokens=res.output_tokens,
                   raw=res.fields, unexpected_keys=sorted(set(res.fields) - set(EXTRACTION_TOOL["input_schema"]["properties"])))
        detail.append(rec)

    # ---- scoring: ground truth is loaded only now ----
    gt = {json.loads(x)["file"]: json.loads(x) for x in (SLIPS / "ground_truth.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()}
    for rec in detail:
        if "raw" not in rec:
            continue
        g = gt[rec["file"]]
        # Same validation as production. reference_at = the synthetic set's "today" (deployment-like config, not ground truth).
        v = ev.validate(rec["raw"], captured_at=None, scan_from=None, scan_to=None, reference_at=REFERENCE_AT)
        g_occ = g.get("occurred_at") or g.get("occurred_date")
        g_date = g_occ[:10] if g_occ else None
        g_time = g_occ[11:16] if g_occ and len(g_occ) > 10 else None
        status_map = {"success": "completed", "pending": "pending", "failed": "failed"}
        rec["validation"] = {"critical_ok": v.critical_ok, "field_states": v.field_states}
        rec["fields"] = {
            "doc_type": (rec["raw"].get("doc_type"), g["doc_type"]),
            "amount": (v.amount_satang, g.get("amount_satang")),
            "date": (v.occurred_date.isoformat() if v.occurred_date else None, g_date),
            "time": (v.occurred_at.strftime("%H:%M") if v.occurred_at else None, g_time),
            "payee": (normalize_payee(v.payee_display), normalize_payee(g.get("payee_display"))),
            "bank_ref": (normalize_ref(v.bank_ref), normalize_ref(g.get("bank_ref"))),
            "status": (v.payment_status if g["doc_type"] in ("transfer_out", "transfer_in") else None,
                       g.get("payment_status") if g["doc_type"] in ("transfer_out", "transfer_in") else None),
            "due_date": (v.due_date.isoformat() if v.due_date else None, g.get("bill_due_date")),
        }
        rec["tags"] = g.get("group_tags", [])
        # Safety: would this record be auto-imported with a wrong critical value?
        wrong_critical = [k for k in ("amount", "date", "doc_type") if rec["fields"][k][1] is not None and rec["fields"][k][0] != rec["fields"][k][1]]
        rec["auto_import_eligible"] = v.critical_ok
        rec["auto_import_with_wrong_critical"] = v.critical_ok and bool(wrong_critical)
        rec["errors"] = [k for k, (p, t) in rec["fields"].items() if t is not None and p != t]
        rec["gt_amount_unreadable_by_design"] = g.get("amount_satang") is None

    scored = [r for r in detail if "fields" in r]
    field_acc = {}
    for k in ("doc_type", "amount", "date", "time", "payee", "bank_ref", "status", "due_date"):
        pairs = [r["fields"][k] for r in scored if r["fields"][k][1] is not None]
        field_acc[k] = {"n": len(pairs), "correct": sum(1 for p, t in pairs if p == t)}
    unreadable = [r for r in scored if r["gt_amount_unreadable_by_design"]]

    # ---- classification, scored separately: chronological replay with no labels in any prompt ----
    seq = sorted(scored, key=lambda r: (gt[r["file"]].get("occurred_at") or gt[r["file"]].get("occurred_date") or ""))
    hist: dict[str, list[str]] = {}
    cls = {"n": 0, "predicted": 0, "predicted_correct": 0, "abstained": 0, "first_seen_payee": 0, "first_seen_abstained": 0}
    for r in seq:
        g = gt[r["file"]]
        if g["doc_type"] not in ("transfer_out", "receipt"):
            continue
        pk = r["fields"]["payee"][0]
        prior = hist.get(pk or "", [])
        sug = suggest(pk, user_default=None, confirmed_history=prior, seed={}, intermediary=is_intermediary(r["raw"].get("payee")))
        cls["n"] += 1
        if not prior:
            cls["first_seen_payee"] += 1
            cls["first_seen_abstained"] += sug.state == "unclassified"
        if sug.state == "predicted":
            cls["predicted"] += 1
            cls["predicted_correct"] += sug.category_code == g["category"]
        else:
            cls["abstained"] += 1
        if pk:
            hist.setdefault(pk, []).append(g["category"])  # simulated user confirmation AFTER the decision

    lat = [r["latency_ms"] for r in scored]
    summary = {
        "images_attempted": len(files), "images_called": len(detail), "provider_errors": sum(1 for r in detail if "provider_error" in r),
        "stopped_early": stop_reason, "schema_unexpected_keys": sum(1 for r in scored if r["unexpected_keys"]),
        "validation_critical_ok": sum(1 for r in scored if r["validation"]["critical_ok"]),
        "field_accuracy": field_acc,
        "auto_import_eligible": sum(1 for r in scored if r["auto_import_eligible"]),
        "auto_import_with_wrong_critical_value": [r["file"] for r in scored if r["auto_import_with_wrong_critical"]],
        "unreadable_amount_by_design": [{"file": r["file"], "model_amount": r["fields"]["amount"][0], "went_to_review": not r["validation"]["critical_ok"]} for r in unreadable],
        "injection_slips": [{"file": r["file"], "errors": r["errors"], "unexpected_keys": r["unexpected_keys"]} for r in scored if "prompt_injection" in r["tags"]],
        "classification_replay_separate": cls,
        "latency_ms": {"p50": statistics.median(lat) if lat else None, "max": max(lat) if lat else None},
        "usage": meter.summary(),
    }
    out = REPO / "evidence" / "runs" / run_id
    out.mkdir(parents=True, exist_ok=False)
    manifest = {
        "run_id": run_id, "kind": "evaluation (real model calls, synthetic data only)", "started_at_utc": started.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(), "command": " ".join(sys.argv),
        "code_version": {"git_head": code_version(), "content_sha256_16": content_hash()},
        "config": s.describe(), "model_access_check": access,
        "model_identifiers_returned": sorted({r["model_id"] for r in scored}),
        "validation": {"reference_at": REFERENCE_AT.isoformat(), "max_age_days": ev.MAX_AGE.days},
        "prompt": {"schema_version": EXTRACTION_SCHEMA_VERSION, "system_sha256": hashlib.sha256(EXTRACTION_SYSTEM.encode()).hexdigest()[:16],
                   "tool_schema_sha256": hashlib.sha256(json.dumps(EXTRACTION_TOOL, sort_keys=True).encode()).hexdigest()[:16],
                   "ground_truth_in_prompt": False},
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "uses_mocks": [], "thresholds": {"N_MIN": 2, "P_MIN_BPS": 8000}, "summary": summary,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    (out / "items.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in detail), encoding="utf-8")
    print(json.dumps({"run_id": run_id, "summary": summary}, ensure_ascii=False, indent=1, default=str))
    return 1 if stop_reason else 0


if __name__ == "__main__":
    raise SystemExit(main())
