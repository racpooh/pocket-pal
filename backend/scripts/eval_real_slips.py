"""Real-slip evaluation (owner's own slips, private). Kept apart from the phone's database and the synthetic E2E.

Privacy rules (owner, 16 Oct 2026) — enforced here, not just documented:
- Images stay in backend/fixtures/real/ (gitignored). They are never copied into the repo, evidence or the cloud
  workspace. The only outside recipient is the extraction provider, and only in `run`, after explicit confirmation.
- Everything that can identify a person or a payment (file names, OCR/model output, names, account numbers, bank
  references, per-image results, labels) is written ONLY under eval/private/<round>/ (gitignored).
- The shareable evidence (evidence/runs/<UTC>-real-slip-<round>-*/manifest.json) holds aggregate counts only: no ids,
  no file names, no values, no per-image rows.
- Ground truth = the owner's labels made by looking at the images. Model output is never used as ground truth; labels
  must be complete and are frozen (sha256 recorded) BEFORE any model call.

Steps (run in backend/, owner's machine):
  1. prepare  — pick N images, write eval/private/<round>/selection.json + labels.csv (ids only)            $0
  2. owner fills labels.csv by looking at each image (amount, date, direction, counterparty, status, …)
  3. check    — validates labels.csv, shows what would be sent (count, sizes, model, worst-case cost)      $0
  4. run      — real extraction, explicit provider + confirmation flag, budget and request caps, fail closed $
  5. score    — offline from the recorded outputs: (a) extraction accuracy, (b) validation/review routing,
                (c) pipeline + dedup replay in the separate `realeval` database. Re-run freely after fixing
                logic; it never calls the model.                                                           $0

  uv run python scripts/eval_real_slips.py prepare --round r1 --n 5
  uv run python scripts/eval_real_slips.py check   --round r1
  uv run python scripts/eval_real_slips.py run     --round r1 --provider anthropic --budget-usd 0.10 --max-requests 5 \
      --confirm-send-to-anthropic
  uv run --with pixeltable-pgserver python scripts/eval_real_slips.py score --round r1
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import platform
import random
import re
import statistics
import sys
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
SOURCE = BACKEND / "fixtures" / "real" / "slip"
PRIVATE = REPO / "eval" / "private"
PUBLIC_LEDGER = REPO / "evidence" / "usage_ledger.jsonl"
sys.path.insert(0, str(BACKEND / "src"))
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

HARD_BUDGET_CAP_USD = 0.10  # round-1 ceiling agreed with the owner; raising it needs a code change + approval
HARD_REQUEST_CAP = 5
DOC_TYPES = ("transfer_out", "transfer_in", "receipt", "bill", "not_financial")
STATUSES = ("success", "pending", "failed", "unknown")
LABEL_COLUMNS = ["id", "doc_type", "amount", "date", "time", "direction", "counterparty", "status", "bank_ref",
                 "same_payment_as", "notes"]
STATUS_MAP = {"success": "completed", "pending": "pending", "failed": "failed", "unknown": None}


class Refused(SystemExit):
    def __init__(self, msg: str):
        super().__init__(f"REFUSED: {msg}")


# ---------------------------------------------------------------- guards

def require_gitignored() -> None:
    lines = {x.strip() for x in (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()}
    for needed in ("backend/fixtures/real/", "eval/private/"):
        if needed not in lines:
            raise Refused(f".gitignore must contain {needed!r} before any real slip is read")


def round_dir(name: str) -> Path:
    if not re.fullmatch(r"r\d{1,3}", name):
        raise Refused("round must look like r1, r2, …")
    d = PRIVATE / f"real-{name}"
    if PRIVATE.resolve() not in d.resolve().parents:
        raise Refused("private dir escaped eval/private")
    return d


def sniff(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    raise Refused("only JPEG/PNG (same rule as the upload API)")


def image_meta(data: bytes) -> dict:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as im:
        exif = im.getexif()
        sub = exif.get_ifd(0x8769)
        gps = exif.get_ifd(0x8825)
        taken = sub.get(36867) or exif.get(306)
        return {"width": im.width, "height": im.height, "has_gps": bool(gps),
                "exif_datetime": str(taken) if taken else None, "exif_offset": sub.get(36881)}


def captured_at_of(meta: dict) -> datetime | None:
    if not meta.get("exif_datetime"):
        return None
    try:
        dt = datetime.strptime(meta["exif_datetime"], "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    off = meta.get("exif_offset") or "+07:00"  # phone in Thailand when no offset is recorded
    sign = 1 if off[0] == "+" else -1
    h, m = (int(x) for x in off[1:].split(":"))
    return dt.replace(tzinfo=timezone(sign * timedelta(hours=h, minutes=m)))


# ---------------------------------------------------------------- labels

def read_labels(d: Path, ids: list[str], name: str = "labels.csv") -> tuple[dict[str, dict], list[str]]:
    if "/" in name or not re.fullmatch(r"labels[\w.-]*\.csv", name):
        raise Refused("labels file must be labels*.csv inside the round folder")
    p = d / name
    rows = {r["id"]: r for r in csv.DictReader(p.open(encoding="utf-8-sig"))}
    errs = []
    for i in ids:
        r = rows.get(i)
        if r is None:
            errs.append(f"{i}: missing row")
            continue
        r = {k: (v or "").strip() for k, v in r.items()}
        rows[i] = r
        if r["doc_type"] not in DOC_TYPES:
            errs.append(f"{i}: doc_type must be one of {DOC_TYPES}")
            continue
        if r["doc_type"] == "not_financial":
            continue
        if r["amount"] != "unreadable" and not re.fullmatch(r"\d+(\.\d{1,2})?", r["amount"].replace(",", "")):
            errs.append(f"{i}: amount like 1234.50 (or 'unreadable')")
        try:
            y = date.fromisoformat(r["date"]).year
            if y > 2200:
                errs.append(f"{i}: date must be Gregorian (YYYY-MM-DD, e.g. 2026-10-15), not Buddhist Era")
        except ValueError:
            errs.append(f"{i}: date YYYY-MM-DD")
        if r["time"] and not re.fullmatch(r"\d{2}:\d{2}", r["time"]):
            errs.append(f"{i}: time HH:MM or empty")
        if r["direction"] not in ("out", "in"):
            errs.append(f"{i}: direction out|in")
        if r["doc_type"] != "bill" and r["status"] not in STATUSES:
            errs.append(f"{i}: status one of {STATUSES}")
        if not r["counterparty"]:
            errs.append(f"{i}: counterparty as printed (or '-' if none is shown)")
        if r["same_payment_as"] and r["same_payment_as"] not in ids:
            errs.append(f"{i}: same_payment_as must be another id of this round")
    return rows, errs


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---------------------------------------------------------------- prepare / check

def cmd_prepare(a) -> int:
    require_gitignored()
    d = round_dir(a.round)
    if (d / "selection.json").exists():
        raise Refused(f"{d.relative_to(REPO)} already prepared (never overwritten; use a new round)")
    files = sorted(p for p in SOURCE.iterdir() if p.is_file() and not p.name.startswith("."))
    by_sha = {}
    for p in files:
        by_sha.setdefault(sha256_file(p), p)  # identical copies count once
    shas = sorted(by_sha)
    rng = random.Random(a.seed)
    picked = rng.sample(shas, min(a.n, len(shas)))
    d.mkdir(parents=True)
    sel = []
    for k, sha in enumerate(picked, 1):
        p = by_sha[sha]
        data = p.read_bytes()
        sel.append({"id": f"{a.round.upper()}-{k:02d}", "sha256": sha, "source": str(p.relative_to(BACKEND)),
                    "bytes": len(data), "mime": sniff(data), **image_meta(data)})
    (d / "selection.json").write_text(json.dumps({"round": a.round, "seed": a.seed, "source_unique_images": len(shas),
                                                  "items": sel}, indent=2, ensure_ascii=False), encoding="utf-8")
    with (d / "labels.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, LABEL_COLUMNS)
        w.writeheader()
        for s in sel:
            w.writerow({"id": s["id"]})
    (d / "LABELING.md").write_text(LABELING_HELP, encoding="utf-8")
    print(json.dumps({"round": a.round, "selected": len(sel), "from_unique_images": len(shas),
                      "with_gps": sum(s["has_gps"] for s in sel), "private_dir": str(d.relative_to(REPO))}))
    print(f"Next: open {d.relative_to(REPO)}/selection.json for the id → file mapping, fill labels.csv (see LABELING.md).")
    return 0


LABELING_HELP = """# Labeling (owner) — look at each image; never copy values from model output

`selection.json` maps each id (R1-01 …) to its file. Fill one row per id in `labels.csv`:

| column | value |
|---|---|
| doc_type | transfer_out (you sent money) · transfer_in (you received) · receipt (shop receipt) · bill (invoice not yet paid) · not_financial |
| amount | total as a number, e.g. 1234.50 (no ฿, commas OK); `unreadable` if you cannot read it |
| date | Gregorian YYYY-MM-DD (slip says 15 ต.ค. 69 → 2026-10-15) |
| time | HH:MM as printed, empty if none |
| direction | out or in (from YOUR point of view) |
| counterparty | the other party exactly as printed (receiver for out, sender for in, shop, biller); `-` if none |
| status | success · pending · failed · unknown (bills: leave empty) |
| bank_ref | optional: the transaction reference as printed (only used for scoring the reference, stays private) |
| same_payment_as | id of another image in this round that is the SAME payment (duplicate, receipt of that slip); else empty |
| notes | anything odd (cropped, blurry, two amounts …) |

The labels are frozen (sha256 recorded) when `run` starts; edit them before that, not after.
"""


def load_selection(d: Path) -> dict:
    p = d / "selection.json"
    if not p.exists():
        raise Refused("run `prepare` first")
    sel = json.loads(p.read_text(encoding="utf-8"))
    for s in sel["items"]:
        data = (BACKEND / s["source"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != s["sha256"]:
            raise Refused(f"{s['id']}: image changed since prepare")
    return sel


def estimate(sel: dict, model: str, max_out: int) -> float:
    from finassist.providers import UsageMeter, image_tokens_estimate

    m = UsageMeter(budget_usd=1e9, max_requests=10**6)
    return sum(m.cost(model, image_tokens_estimate((BACKEND / s["source"]).read_bytes()) + 1500, max_out) for s in sel["items"])


def cmd_check(a) -> int:
    require_gitignored()
    from finassist.settings import get_settings

    d = round_dir(a.round)
    sel = load_selection(d)
    ids = [s["id"] for s in sel["items"]]
    _, errs = read_labels(d, ids)
    s = get_settings()
    print(json.dumps({"round": a.round, "images": len(ids), "labels_complete": not errs, "label_problems": errs,
                      "bytes_total": sum(x["bytes"] for x in sel["items"]), "with_gps": sum(x["has_gps"] for x in sel["items"]),
                      "extraction_model": s.extraction_model,
                      "worst_case_cost_usd": round(estimate(sel, s.extraction_model, s.extraction_max_output_tokens), 4),
                      "hard_caps": {"budget_usd": HARD_BUDGET_CAP_USD, "requests": HARD_REQUEST_CAP}}, indent=1, ensure_ascii=False))
    return 0 if not errs else 1


# ---------------------------------------------------------------- run (billed)

def cmd_run(a) -> int:
    require_gitignored()
    from finassist.providers import (AnthropicExtractionProvider, BudgetExceeded, EXTRACTION_SCHEMA_VERSION, EXTRACTION_SYSTEM,
                                     EXTRACTION_TOOL, FatalProviderError, ProviderError, UsageMeter, verify_model_access)
    from finassist.settings import get_settings

    if a.provider != "anthropic":
        raise Refused("--provider anthropic must be given explicitly (no default, no mock)")
    if not a.confirm_send_to_anthropic:
        raise Refused("--confirm-send-to-anthropic is required: the owner must have approved sending these images")
    if a.budget_usd > HARD_BUDGET_CAP_USD or a.max_requests > HARD_REQUEST_CAP:
        raise Refused(f"caps for this round are ${HARD_BUDGET_CAP_USD} and {HARD_REQUEST_CAP} requests")
    d = round_dir(a.round)
    sel = load_selection(d)
    ids = [s["id"] for s in sel["items"]]
    if len(ids) > a.max_requests:
        raise Refused(f"{len(ids)} images but only {a.max_requests} requests allowed")
    _, errs = read_labels(d, ids)
    if errs:
        raise Refused("labels.csv incomplete — ground truth must be fixed BEFORE model calls: " + "; ".join(errs[:5]))
    if any(s["has_gps"] for s in sel["items"]):
        raise Refused("an image carries GPS metadata; remove it from the round")
    s = get_settings()
    s.model_provider = "anthropic"
    s.require_real_provider()  # fail closed: key and model ids must be present
    labels_sha = sha256_file(d / "labels.csv")
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ") + f"-real-slip-{a.round}-extract"
    outp = d / "runs" / run_id
    outp.mkdir(parents=True)
    key = s.model_api_key.get_secret_value()
    try:
        access = verify_model_access(key, s.extraction_model)  # Models API, not billed
    except FatalProviderError as e:
        (outp / "STOPPED.txt").write_text(f"stopped before any billed call: {e}\n", encoding="utf-8")
        print(f"STOP before any billed call: {e}", file=sys.stderr)
        return 3
    meter = UsageMeter(budget_usd=a.budget_usd, max_requests=a.max_requests, ledger_path=str(d / "usage_ledger.jsonl"))
    provider = AnthropicExtractionProvider(key, s.extraction_model, meter=meter, max_output_tokens=s.extraction_max_output_tokens,
                                           max_retries=0, run_id=run_id)
    recs, stop = [], None
    for item in sel["items"]:
        data = (BACKEND / item["source"]).read_bytes()  # exactly the bytes the upload API would receive
        rec = {"id": item["id"], "sha256": item["sha256"]}
        try:
            res = provider.extract(data, item["mime"])
        except BudgetExceeded as e:
            stop = f"budget: {e}"
            break
        except FatalProviderError as e:
            stop = f"fatal provider error: {e}"
            break
        except ProviderError as e:
            rec["provider_error"] = str(e)  # recorded, NOT retried automatically
            recs.append(rec)
            continue
        rec.update(model_id=res.model_id, latency_ms=res.latency_ms, input_tokens=res.input_tokens, output_tokens=res.output_tokens,
                   raw=res.fields)
        recs.append(rec)
    (outp / "outputs.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs), encoding="utf-8")
    usage = meter.summary()
    meta = {"run_id": run_id, "round": a.round, "started_at_utc": started.isoformat(), "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "model_access_check": access, "labels_sha256_frozen_before_calls": labels_sha, "stopped_early": stop,
            "prompt": {"schema_version": EXTRACTION_SCHEMA_VERSION, "system_sha256_16": hashlib.sha256(EXTRACTION_SYSTEM.encode()).hexdigest()[:16],
                       "tool_schema_sha256_16": hashlib.sha256(json.dumps(EXTRACTION_TOOL, sort_keys=True).encode()).hexdigest()[:16]},
            "caps": {"budget_usd": a.budget_usd, "max_requests": a.max_requests, "retries": 0}, "usage": usage}
    (outp / "run.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    with PUBLIC_LEDGER.open("a", encoding="utf-8") as f:  # cost transparency: aggregate only, no ids or content
        f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "run_id": run_id, "purpose": "real-slip-eval (private data; aggregate)",
                            "model": s.extraction_model, "requests": usage.get("requests"), "input_tokens": usage.get("input_tokens"),
                            "output_tokens": usage.get("output_tokens"), "cost_usd": usage.get("estimated_cost_usd"),
                            "cost_kind": "estimated from returned token counts x list price; not an invoice amount"}) + "\n")
    print(json.dumps({"run_id": run_id, "called": len(recs), "provider_errors": sum("provider_error" in r for r in recs),
                      "stopped_early": stop, "usage": usage}, default=str))
    return 1 if stop else 0


# ---------------------------------------------------------------- score (offline)

def _amount(text):
    from finassist.domain.money import parse_thb

    try:
        return parse_thb(text) if text else None
    except Exception:
        return None


def _date(text):
    from finassist.domain.extraction_validation import parse_thai_date

    try:
        return parse_thai_date(text).isoformat() if text else None
    except Exception:
        return None


def _time(text):
    from finassist.domain.extraction_validation import parse_time

    try:
        t = parse_time(text)
        return t.strftime("%H:%M") if t else None
    except Exception:
        return None


def _direction(doc_type):
    return {"transfer_in": "in", "transfer_out": "out", "receipt": "out", "bill": "out"}.get(doc_type)


def extraction_fields(raw: dict) -> dict:
    from finassist.domain.classify import normalize_payee
    from finassist.domain.dedup import normalize_ref

    return {"doc_type": raw.get("doc_type"), "amount": _amount(raw.get("amount_text")), "date": _date(raw.get("date_text")),
            "time": _time(raw.get("time_text")), "direction": _direction(raw.get("doc_type")),
            "counterparty": normalize_payee(raw.get("payee")), "status": STATUS_MAP.get(raw.get("status") or "unknown"),
            "bank_ref": normalize_ref(raw.get("bank_ref"))}


def label_fields(lab: dict) -> dict:
    from finassist.domain.classify import normalize_payee
    from finassist.domain.dedup import normalize_ref

    nf = lab["doc_type"] == "not_financial"
    amt = None if nf or lab["amount"] == "unreadable" else _amount(lab["amount"])  # integer satang, same parser
    return {"doc_type": lab["doc_type"], "amount": amt, "date": None if nf else lab["date"], "time": lab["time"] or None,
            "direction": None if nf else lab["direction"],
            "counterparty": None if nf or lab["counterparty"] in ("", "-") else normalize_payee(lab["counterparty"]),
            "status": None if nf or lab["doc_type"] == "bill" else STATUS_MAP[lab["status"]],
            "bank_ref": normalize_ref(lab["bank_ref"]) if lab.get("bank_ref") else None}


def _loose(a: str | None, b: str | None) -> bool:
    """Counterparty 'loose' match: one normalized string contains the other (masked/truncated names)."""
    return bool(a and b and (a in b or b in a))


def cmd_score(a) -> int:
    require_gitignored()
    d = round_dir(a.round)
    sel = load_selection(d)
    ids = [s["id"] for s in sel["items"]]
    labels, errs = read_labels(d, ids, a.labels)
    if errs:
        raise Refused("labels incomplete: " + "; ".join(errs[:5]))
    runs = sorted((d / "runs").glob("*-extract")) if (d / "runs").exists() else []
    src = (d / "runs" / a.run) if a.run else (runs[-1] if runs else None)
    if not src or not (src / "outputs.jsonl").exists():
        raise Refused("no recorded outputs yet (run `run` first)")
    run_meta = json.loads((src / "run.json").read_text(encoding="utf-8"))
    recs = {r["id"]: r for r in (json.loads(x) for x in (src / "outputs.jsonl").read_text(encoding="utf-8").splitlines() if x.strip())}
    res = score_round(d, sel, labels, recs, with_pipeline=not a.skip_pipeline)
    summary = res["summary"]
    summary["usage"] = run_meta.get("usage")
    labels_sha = sha256_file(d / a.labels)
    summary["labels"] = {"file": a.labels if a.labels == "labels.csv" else "corrected version (see private label log)",
                         "is_frozen_version": run_meta["labels_sha256_frozen_before_calls"] == labels_sha}
    summary["labels_changed_after_model_run"] = not summary["labels"]["is_frozen_version"]
    summary["code"] = {"validation_sha256_16": hashlib.sha256((BACKEND / "src/finassist/domain/extraction_validation.py").read_bytes()).hexdigest()[:16],
                       "harness_sha256_16": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]}
    summary["cost_note"] = "estimated from returned token counts x list price; not an invoice amount"
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    (d / f"score-{stamp}.json").write_text(json.dumps({"source_run": src.name, **res}, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    write_public(a.round, stamp, src.name, run_meta, summary)
    print(json.dumps({"private_report": str((d / f"score-{stamp}.json").relative_to(REPO)), "summary": summary}, indent=1, default=str))
    return 0


def score_round(d: Path, sel: dict, labels: dict, recs: dict, *, with_pipeline: bool) -> dict:
    from finassist.domain import extraction_validation as ev

    by_id = {s["id"]: s for s in sel["items"]}
    ids = list(by_id)
    now = datetime.now(timezone.utc)

    per_image, fields = [], ("doc_type", "amount", "date", "time", "direction", "counterparty", "status", "bank_ref")
    acc = {k: {"n": 0, "correct": 0} for k in fields}
    acc["counterparty_loose"] = {"n": 0, "correct": 0}
    routing = Counter()
    for i in ids:
        lab = label_fields(labels[i])
        rec = recs.get(i)
        row = {"id": i, "label": lab}
        if rec is None or "raw" not in rec:
            row["model"] = None
            row["error"] = (rec or {}).get("provider_error", "not called")
            routing["not_extracted"] += 1
            per_image.append(row)
            continue
        got = extraction_fields(rec["raw"])
        row["model"] = got
        row["readability"] = rec["raw"].get("readability")
        row["field_ok"] = {}
        for k in fields:
            if lab[k] is None:
                continue  # not applicable / not labeled
            acc[k]["n"] += 1
            ok = got[k] == lab[k]
            acc[k]["correct"] += ok
            row["field_ok"][k] = ok
        if lab["counterparty"] is not None:
            acc["counterparty_loose"]["n"] += 1
            acc["counterparty_loose"]["correct"] += _loose(got["counterparty"], lab["counterparty"])
        # (b) validation / review routing — production validation on the recorded output, scored separately
        cap = captured_at_of(by_id[i])
        v = ev.validate(rec["raw"], captured_at=cap, scan_from=None, scan_to=None, reference_at=now)
        auto = v.critical_ok
        crit = ("amount", "date", "direction", "doc_type") + (("status",) if lab["status"] is not None else ())
        critical_right = all(row["field_ok"].get(k, True) for k in crit) and lab["doc_type"] != "not_financial"
        row["routing"] = {"auto_import": auto, "critical_fields_right": critical_right, "problems": v.problems,
                          "field_states": v.field_states, "captured_at_source": "exif" if cap else "none"}
        routing[("auto" if auto else "review") + "_" + ("right" if critical_right else "wrong")] += 1
        per_image.append(row)

    pipeline = replay_pipeline(d, sel, labels, recs) if with_pipeline else {"skipped": True}

    lat = [r["latency_ms"] for r in recs.values() if "latency_ms" in r]
    summary = {
        "images": len(ids), "extracted": sum(1 for r in recs.values() if "raw" in r),
        "provider_errors": sum(1 for r in recs.values() if "provider_error" in r),
        "a_extraction_accuracy": acc,
        "b_routing": {"auto_import_and_critical_right": routing["auto_right"],
                      "auto_import_with_wrong_critical_UNSAFE": routing["auto_wrong"],
                      "review_and_critical_wrong_caught": routing["review_wrong"],
                      "review_although_critical_right": routing["review_right"], "not_extracted": routing["not_extracted"]},
        "c_pipeline_dedup": pipeline.get("aggregate", pipeline),
        "latency_ms": {"p50": statistics.median(lat) if lat else None, "max": max(lat) if lat else None},
    }
    return {"summary": summary, "per_image": per_image, "pipeline_detail": pipeline.get("detail")}


def write_public(rnd: str, stamp: str, src_run: str, run_meta: dict, summary: dict) -> None:
    """Shareable evidence: aggregate counts only. Asserts that no private value leaks into it."""
    out = REPO / "evidence" / "runs" / f"{stamp}-real-slip-{rnd}-score"
    out.mkdir(parents=True)
    manifest = {"run_id": out.name, "kind": "real-slip evaluation — AGGREGATE ONLY (per-image results, labels, outputs stay in eval/private/)",
                "extraction_run": src_run.split("-real-slip")[0] + "-real-slip-" + rnd + "-extract",
                "ground_truth": "owner's labels from the images, frozen before the model call; model output never used as truth",
                "model": (run_meta.get("model_access_check") or {}).get("resolved_id"), "prompt": run_meta.get("prompt"),
                "caps": run_meta.get("caps"), "stopped_early": bool(run_meta.get("stopped_early")),
                "environment": {"python": platform.python_version(), "platform": platform.platform()},
                "uses_mocks": ["pipeline replay: ReplayProvider returns the recorded real outputs (no second model call)",
                               "dedup probe: one re-encoded copy is SIMULATED (labelled), not a separate photo"],
                "limits": ["tiny sample: counts, not rates; not a competition score",
                           "images chosen at random from the owner's own slips; not representative of all banks"],
                "summary": summary}
    text = json.dumps(manifest, indent=2, ensure_ascii=False, default=str)
    if re.search(r"R\d+-\d{2}|\.jpe?g|\.png|[฀-๿]", text):
        raise Refused("public manifest would contain an id, a file name or Thai text; not written")
    (out / "manifest.json").write_text(text, encoding="utf-8")


def replay_pipeline(d: Path, sel: dict, labels: dict, recs: dict) -> dict:
    """(c) The recorded outputs through the REAL worker pipeline (validation, dedup, review routing, RLS) in the separate
    `realeval` database (own cluster; never the phone's or the E2E's). Images go to a temp storage dir outside the repo."""
    import shutil
    import tempfile

    from fastapi.testclient import TestClient

    import local_envs
    from finassist.api.app import create_app
    from finassist.infra import Database
    from finassist.providers import ExtractionResult, ProviderError
    from finassist.services.imports import LocalStorage, run_once
    from finassist.settings import Settings
    from tests.integration.conftest import _reset, app_url

    by_sha = {r["sha256"]: r["raw"] for r in recs.values() if "raw" in r}

    class Replay:
        def extract(self, image: bytes, mime: str):
            raw = by_sha.get(hashlib.sha256(image).hexdigest())
            if raw is None:
                raise ProviderError("no recorded output for this image")
            return ExtractionResult(dict(raw), "replay", 0)

    url = local_envs.local_admin_url(local_envs.PROFILES["realeval"])
    _reset(url)  # refuses anything not named *_test
    tmp = Path(tempfile.mkdtemp(prefix="realeval-uploads-"))
    try:
        storage = LocalStorage(str(tmp))
        app = create_app(Settings(_env_file=None, env="test", model_provider="fake", database_url=url, storage_dir=str(tmp)),
                         db=Database(app_url(url)), storage=storage)
        c = TestClient(app)
        c.post("/v1/auth/signup", json={"email": "realeval@example.test", "password": "realeval password 1"})
        H = {"Authorization": "Bearer " + c.post("/v1/auth/login", json={"email": "realeval@example.test", "password": "realeval password 1"}).json()["token"]}
        dates = [labels[i]["date"] for i in labels if labels[i].get("date")]
        scan_from = (min(date.fromisoformat(x) for x in dates) - timedelta(days=1)).isoformat() if dates else "2000-01-01"
        c.post("/v1/consents", headers=H, json={"scope": "photo_processing", "version": "v1", "params": {"scan_from": scan_from}})
        c.post("/v1/consents", headers=H, json={"scope": "auto_import", "version": "v1"})
        wdb = Database(app_url(url, "finassist_worker"))
        provider = Replay()

        def upload(data: bytes, mime: str, cap: datetime | None) -> dict:
            form = {"captured_at": cap.isoformat()} if cap else {"confirmed_undated": "true"}
            r = c.post("/v1/uploads", headers=H, files={"image": ("x", data, mime)}, data=form)
            while True:
                with wdb.connect() as conn:
                    if not run_once(conn, storage, provider):
                        break
            return {"http": r.status_code, **(r.json() if r.headers.get("content-type", "").startswith("application/json") else {})}

        sha_to_id, probes = {}, {}
        for s in sel["items"]:
            data = (BACKEND / s["source"]).read_bytes()
            sha_to_id[s["sha256"]] = s["id"]
            upload(data, s["mime"], captured_at_of(s))
        first = sel["items"][0]
        data0 = (BACKEND / first["source"]).read_bytes()
        again = upload(data0, first["mime"], captured_at_of(first))  # exact same bytes again
        probes["exact_reupload_flagged_duplicate"] = bool(again.get("duplicate_image"))
        if first["sha256"] in by_sha:  # SIMULATED near-duplicate: re-encoded + cropped copy, same recorded output
            from PIL import Image

            with Image.open(io.BytesIO(data0)) as im:
                buf = io.BytesIO()
                im.convert("RGB").crop((2, 2, im.width - 2, im.height - 2)).save(buf, format="JPEG", quality=85)
            copy = buf.getvalue()
            by_sha[hashlib.sha256(copy).hexdigest()] = by_sha[first["sha256"]]
            sha_to_id[hashlib.sha256(copy).hexdigest()] = first["id"] + "~sim"
            upload(copy, "image/jpeg", captured_at_of(first))

        sup = Database(url)
        with sup.connect() as conn:
            txns = conn.execute("""select t.kind, t.amount_satang, t.occurred_date, t.payment_status, u.sha256 from txn t
                                   join txn_evidence e on e.txn_id=t.id and e.relation='primary' join upload u on u.id=e.upload_id
                                   where t.deleted_at is null""").fetchall()
            reviews = conn.execute("select r.reason, u.sha256 from review_item r join upload u on u.id=r.upload_id where r.status='open'").fetchall()
            bills = conn.execute("select u.sha256 from bill b join upload u on u.id=b.upload_id").fetchall()
            failed = conn.execute("select u.sha256, u.status from upload u where u.status in ('extract_failed','rejected')").fetchall()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    def root(i: str) -> str:
        i = i.removesuffix("~sim")
        seen = set()
        while labels[i].get("same_payment_as") and i not in seen:
            seen.add(i)
            i = labels[i]["same_payment_as"]
        return i

    expected = {}
    for i, lab in labels.items():
        if i not in sha_to_id.values():
            continue
        if lab["doc_type"] in ("bill", "not_financial") or lab.get("status") != "success" or lab["amount"] == "unreadable":
            continue
        expected.setdefault(root(i), {"amount": _amount(lab["amount"]), "date": lab["date"],
                                      "kind": "income" if lab["direction"] == "in" else "expense"})
    counted = defaultdict(list)
    for t in txns:
        if t["payment_status"] == "completed":
            counted[root(sha_to_id[bytes(t["sha256"]).hex()])].append(t)
    review_roots = {root(sha_to_id[bytes(r["sha256"]).hex()]): r["reason"] for r in reviews}
    detail, agg = [], Counter()
    for k, exp in expected.items():
        got = counted.get(k, [])
        if len(got) > 1:
            st = "DOUBLE_COUNTED"
        elif not got:
            st = "held_in_review" if k in review_roots else "MISSED_SILENTLY"
        else:
            t = got[0]
            st = "counted_once" if (t["amount_satang"], str(t["occurred_date"]), t["kind"]) == (exp["amount"], exp["date"], exp["kind"]) else "WRONG_VALUE"
        agg[st] += 1
        detail.append({"payment": k, "status": st, "review_reason": review_roots.get(k)})
    unexpected = [k for k in counted if k not in expected]
    return {"aggregate": {"expected_payments": len(expected), **{k: agg[k] for k in ("counted_once", "held_in_review", "DOUBLE_COUNTED",
                                                                                     "WRONG_VALUE", "MISSED_SILENTLY")},
                          "unexpected_counted": len(unexpected), "open_reviews_by_reason": dict(Counter(r["reason"] for r in reviews)),
                          "bills_created": len(bills), "uploads_failed_or_rejected": len(failed),
                          "dedup_probes": {**probes, "simulated_near_duplicate_not_double_counted": len(counted.get(root(first["id"]), [])) <= 1}},
            "detail": detail + [{"unexpected_counted": k} for k in unexpected]}


def cmd_selftest(a) -> int:
    """$0 harness check on SYNTHETIC slips (no real image, no model): fabricated 'recorded outputs' from the synthetic
    ground truth, with one amount deliberately wrong, must be scored as exactly that error; the pipeline replay must count
    the duplicate pair once. Uses a temp private dir; writes no public evidence."""
    import tempfile

    global SOURCE, PRIVATE
    from tests.integration.conftest import SLIPS, fields_from_gt, gt_rows

    rows = {r["file"]: r for r in gt_rows()}
    pick = ["slip_003_transfer_out.png", "slip_004_transfer_out.png", "slip_015_transfer_out.png", "slip_016_receipt.png",
            "slip_028_bill.png"]
    tmp = Path(tempfile.mkdtemp(prefix="realeval-selftest-"))
    SOURCE, PRIVATE = SLIPS, tmp / "private"
    d = PRIVATE / "real-r0"
    d.mkdir(parents=True)
    items, labels, recs = [], [], []
    for k, f in enumerate(pick, 1):
        data = (SLIPS / f).read_bytes()
        i = f"R0-{k:02d}"
        g = rows[f]
        meta = image_meta(data)
        meta["exif_datetime"] = "2026:10:15 13:00:00"
        items.append({"id": i, "sha256": hashlib.sha256(data).hexdigest(), "source": str((SLIPS / f).relative_to(BACKEND)),
                      "bytes": len(data), "mime": "image/png", **meta})
        occ = g.get("occurred_at") or g.get("occurred_date") or ""
        labels.append({"id": i, "doc_type": g["doc_type"], "amount": f"{g['amount_satang'] / 100:.2f}" if g.get("amount_satang") else "unreadable",
                       "date": occ[:10], "time": occ[11:16] if len(occ) > 10 else "", "direction": "in" if g["doc_type"] == "transfer_in" else "out",
                       "counterparty": g.get("payee_display") or "-",
                       "status": "" if g["doc_type"] == "bill" else {"completed": "success"}.get(g.get("payment_status"), g.get("payment_status") or "unknown"),
                       "bank_ref": g.get("bank_ref") or "", "same_payment_as": "", "notes": ""})
        raw = fields_from_gt(g)
        recs.append({"id": i, "sha256": hashlib.sha256(data).hexdigest(), "model_id": "selftest", "latency_ms": 1, "raw": raw})
    labels[3]["same_payment_as"] = "R0-03"  # receipt 016 is the same purchase as slip 015
    recs[1]["raw"] = dict(recs[1]["raw"], amount_text="9,999.00", amount_text_second=None)  # deliberate model error on R0-02
    (d / "selection.json").write_text(json.dumps({"round": "r0", "items": items}), encoding="utf-8")
    with (d / "labels.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, LABEL_COLUMNS)
        w.writeheader()
        w.writerows(labels)
    run = d / "runs" / "00000000T000000Z-real-slip-r0-extract"
    run.mkdir(parents=True)
    (run / "outputs.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs), encoding="utf-8")
    (run / "run.json").write_text(json.dumps({"labels_sha256_frozen_before_calls": sha256_file(d / "labels.csv"), "usage": {}}), encoding="utf-8")
    ids = [x["id"] for x in items]
    lab, errs = read_labels(d, ids)
    assert not errs, errs
    res = score_round(d, {"items": items}, lab, {r["id"]: r for r in recs}, with_pipeline=not a.skip_pipeline)
    acc, pipe = res["summary"]["a_extraction_accuracy"], res["summary"]["c_pipeline_dedup"]
    checks = {
        "amount: exactly the planted error": acc["amount"]["n"] - acc["amount"]["correct"] == 1
                                             and [r["id"] for r in res["per_image"] if r.get("field_ok", {}).get("amount") is False] == ["R0-02"],
        "doc_type all right": acc["doc_type"]["correct"] == acc["doc_type"]["n"] == 5,
        "date all right": acc["date"]["correct"] == acc["date"]["n"],
        "routing: wrong amount is not counted as right": res["summary"]["b_routing"]["auto_import_and_critical_right"] <= 4,
    }
    if not a.skip_pipeline:
        checks.update({
            "pipeline: no double count": pipe["DOUBLE_COUNTED"] == 0,
            "pipeline: receipt+slip pair counted once": next(x for x in res["pipeline_detail"] if x.get("payment") == "R0-03")["status"] in ("counted_once", "held_in_review"),
            "pipeline: planted wrong amount not silently counted right": next(x for x in res["pipeline_detail"] if x.get("payment") == "R0-02")["status"] != "counted_once",
            "pipeline: exact re-upload flagged": pipe["dedup_probes"]["exact_reupload_flagged_duplicate"],
            "pipeline: simulated near-duplicate not double counted": pipe["dedup_probes"]["simulated_near_duplicate_not_double_counted"],
            "pipeline: bill created": pipe["bills_created"] == 1,
        })
    result = {"selftest": "PASS" if all(checks.values()) else "FAIL", "checks": checks, "accuracy": acc, "pipeline": pipe,
              "routing": res["summary"]["b_routing"]}
    out = REPO / "evidence" / "runs" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-real-slip-harness-selftest")
    out.mkdir(parents=True)
    (out / "manifest.json").write_text(json.dumps({
        "run_id": out.name, "kind": "harness self-test of scripts/eval_real_slips.py — SYNTHETIC slips only, no model call, $0",
        "uses_mocks": ["recorded outputs FABRICATED from the synthetic ground truth, with one amount deliberately wrong (R0-02)",
                       "pipeline replay in the separate realeval database; simulated near-duplicate"],
        "environment": {"python": platform.python_version(), "platform": platform.platform()}, **result}, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"run_id": out.name, **result}, indent=1, ensure_ascii=False, default=str))
    return 0 if all(checks.values()) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--round", required=True)
    p.add_argument("--n", type=int, default=5)
    p.add_argument("--seed", type=int, default=20261016)
    p = sub.add_parser("check")
    p.add_argument("--round", required=True)
    p = sub.add_parser("run")
    p.add_argument("--round", required=True)
    p.add_argument("--provider", required=True)
    p.add_argument("--budget-usd", type=float, required=True)
    p.add_argument("--max-requests", type=int, required=True)
    p.add_argument("--confirm-send-to-anthropic", action="store_true")
    p = sub.add_parser("score")
    p.add_argument("--round", required=True)
    p.add_argument("--run", default=None, help="extraction run id under eval/private/<round>/runs (default: latest)")
    p.add_argument("--skip-pipeline", action="store_true")
    p.add_argument("--labels", default="labels.csv", help="labels*.csv in the round folder (default: the frozen labels.csv)")
    p = sub.add_parser("selftest", help="$0 harness check on synthetic slips")
    p.add_argument("--skip-pipeline", action="store_true")
    a = ap.parse_args()
    return {"prepare": cmd_prepare, "check": cmd_check, "run": cmd_run, "score": cmd_score, "selftest": cmd_selftest}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
