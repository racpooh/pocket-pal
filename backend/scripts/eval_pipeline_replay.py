"""End-to-end ledger check: recorded REAL model outputs → validation → dedup → ledger (no model calls, $0).

  TEST_DATABASE_URL=...<name>_test uv run python scripts/eval_pipeline_replay.py --run 20261015T091318Z-haiku-synth40-v02 --slug replay-v02

Answers the question "is the final ledger right and nothing counted twice?", not "did the model read each field".
- Replays the exact `raw` outputs recorded by scripts/eval_extraction.py (a real Haiku run) through the real worker
  pipeline (consent checks, validation, dedup, review routing, RLS roles) into a fresh *_test database.
- Expected ledger is derived from ground truth AFTER the replay: each real payment counted exactly once; exact and near
  duplicates and receipt+slip pairs collapse to one payment; pending/failed are recorded but not counted; bills become bills.
- `--adversarial` adds clearly-labelled SIMULATED inputs (not model outputs), e.g. a re-encoded copy of slip_021 whose
  reference is read correctly while the recorded run misread it — the case from the Codex review.
Writes evidence/runs/<UTC>-<slug>/{manifest.json, items.jsonl}.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND / "src"))
sys.path.insert(0, str(BACKEND))

FIXED_NOW = "2026-10-15T08:00:00+00:00"  # 15:00 ICT, after the latest synthetic slip
CAPTURED_AT = "2026-10-15T15:00:00+07:00"
SLIPS = BACKEND / "fixtures" / "synthetic" / "slips"


class ReplayProvider:
    """Returns the recorded model output for an image (by sha256 prefix). Unknown image → ProviderError."""

    def __init__(self, by_prefix: dict[str, dict], model_id: str):
        self.by_prefix, self.model_id, self.calls = by_prefix, model_id, 0

    def extract(self, image: bytes, mime: str):
        from finassist.providers import ExtractionResult, ProviderError

        self.calls += 1
        raw = self.by_prefix.get(hashlib.sha256(image).hexdigest()[:16])
        if raw is None:
            raise ProviderError("no recorded output for this image")
        return ExtractionResult(dict(raw), f"replay:{self.model_id}", 0)


def reencode(data: bytes) -> bytes:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as im:
        buf = io.BytesIO()
        im.convert("RGB").crop((2, 2, im.width - 2, im.height - 2)).save(buf, format="JPEG", quality=85)
        return buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="evidence run id of a real extraction eval (has items.jsonl)")
    ap.add_argument("--slug", required=True)
    ap.add_argument("--adversarial", action="store_true")
    a = ap.parse_args()
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        print("TEST_DATABASE_URL (a *_test database) is required", file=sys.stderr)
        return 2
    os.environ["FINASSIST_FIXED_NOW"] = FIXED_NOW

    from fastapi.testclient import TestClient

    from finassist.api.app import create_app
    from finassist.infra import Database
    from finassist.services.imports import LocalStorage, run_once
    from finassist.settings import Settings
    from tests.integration.conftest import _reset, app_url

    src = REPO / "evidence" / "runs" / a.run
    recorded = [json.loads(x) for x in (src / "items.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    manifest_src = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
    model_id = (manifest_src.get("model_identifiers_returned") or ["unknown"])[0]
    by_prefix = {r["sha256"]: r["raw"] for r in recorded if "raw" in r}
    files = sorted(p.name for p in SLIPS.glob("*.png"))
    uploads: list[tuple[str, bytes, str, bool]] = [(f, (SLIPS / f).read_bytes(), "image/png", False) for f in files]
    simulated = []
    if a.adversarial:
        gt21 = next(json.loads(x) for x in (SLIPS / "ground_truth.jsonl").read_text(encoding="utf-8").splitlines() if '"slip_021' in x)
        copy = reencode((SLIPS / "slip_021_transfer_out.png").read_bytes())
        raw = dict(next(r["raw"] for r in recorded if r["file"] == "slip_021_transfer_out.png"))
        raw["bank_ref"] = gt21["bank_ref"]  # SIMULATED: the same slip, reference read correctly
        by_prefix[hashlib.sha256(copy).hexdigest()[:16]] = raw
        uploads.append(("SIM_slip_021_reencoded_correct_ref.jpg", copy, "image/jpeg", True))
        simulated.append({"file": "SIM_slip_021_reencoded_correct_ref.jpg", "same_payment_as": "slip_021_transfer_out.png",
                          "what": "re-encoded/cropped copy; recorded raw output with the correct reference substituted"})

    _reset(url)
    storage = LocalStorage(str(BACKEND / "var" / "replay_uploads" / uuid.uuid4().hex))
    app = create_app(Settings(_env_file=None, model_provider="fake", database_url=url, storage_dir=str(storage.root)),
                     db=Database(app_url(url)), storage=storage)
    c = TestClient(app)
    c.post("/v1/auth/signup", json={"email": "replay@example.test", "password": "replay password 1"})
    H = {"Authorization": "Bearer " + c.post("/v1/auth/login", json={"email": "replay@example.test", "password": "replay password 1"}).json()["token"]}
    c.put("/v1/me/profile", headers=H, json={"income_satang": 2_000_000, "income_frequency": "monthly", "next_income_date": "2026-11-01"})
    acct = c.get("/v1/accounts", headers=H).json()[0]["id"]
    c.post(f"/v1/accounts/{acct}/balance-observations", headers=H, json={"amount_satang": 5_000_000, "as_of": "2026-07-01T00:00:00+07:00"})
    c.post("/v1/consents", headers=H, json={"scope": "photo_processing", "version": "v1", "params": {"scan_from": "2026-07-01"}})
    c.post("/v1/consents", headers=H, json={"scope": "auto_import", "version": "v1"})

    provider = ReplayProvider(by_prefix, model_id)
    wdb = Database(app_url(url, "finassist_worker"))
    sha_to_file: dict[str, str] = {}
    for name, data, mime, _ in uploads:
        r = c.post("/v1/uploads", headers=H, files={"image": (name, data, mime)}, data={"captured_at": CAPTURED_AT})
        sha_to_file.setdefault(hashlib.sha256(data).hexdigest(), name)
        while True:  # process immediately, in upload order, like a phone scanning the album in order
            with wdb.connect() as conn:
                if not run_once(conn, storage, provider):
                    break

    sup = Database(url)
    with sup.connect() as conn:
        txns = conn.execute("""select t.id, t.kind, t.amount_satang, t.occurred_date, t.payment_status, t.bank_ref_norm, u.sha256
                               from txn t join txn_evidence e on e.txn_id=t.id and e.relation='primary' join upload u on u.id=e.upload_id
                               where t.deleted_at is null""").fetchall()
        reviews = conn.execute("""select r.reason, u.sha256 from review_item r join upload u on u.id=r.upload_id where r.status='open'""").fetchall()
        bills = conn.execute("select b.amount_due_satang, b.due_date, u.sha256 from bill b join upload u on u.id=b.upload_id").fetchall()
        merged = conn.execute("select u.sha256 from upload u where u.status='merged_duplicate'").fetchall()

    gt = {json.loads(x)["file"]: json.loads(x) for x in (SLIPS / "ground_truth.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()}

    def key_of(file: str) -> str:
        """Ground-truth payment identity: duplicates and receipt/slip pairs share one key."""
        if file.startswith("SIM_slip_021"):
            return key_of("slip_021_transfer_out.png")
        g = gt[file]
        for t in g["group_tags"]:
            kind, _, other = t.partition(":")
            if kind in ("exact_duplicate_of", "near_duplicate_of"):
                return key_of(other)
            if kind == "same_purchase_as" and g["doc_type"] == "receipt":
                return key_of(other)
        return g.get("bank_ref") or file

    expected_counted: dict[str, dict] = {}
    expected_bills = []
    for f, g in gt.items():
        if g["doc_type"] == "bill":
            expected_bills.append(f)
            continue
        if g.get("payment_status") in ("pending", "failed"):
            continue
        k = key_of(f)
        if g.get("amount_satang") is not None and k not in expected_counted:
            expected_counted[k] = {"file": f, "amount": g["amount_satang"], "date": (g.get("occurred_at") or "")[:10],
                                   "kind": "income" if g["doc_type"] == "transfer_in" else "expense"}

    counted = [t for t in txns if t["payment_status"] == "completed"]
    actual_by_key: dict[str, list] = defaultdict(list)
    for t in counted:
        f = sha_to_file[bytes(t["sha256"]).hex()]
        actual_by_key[key_of(f)].append((f, t))
    review_keys = {key_of(sha_to_file[bytes(r["sha256"]).hex()]): r["reason"] for r in reviews}

    items, double, wrong, missed, held = [], [], [], [], []
    for k, exp in expected_counted.items():
        got = actual_by_key.get(k, [])
        status = "counted_once"
        if len(got) > 1:
            status = "DOUBLE_COUNTED"; double.append(k)
        elif not got:
            status = f"held_in_review:{review_keys[k]}" if k in review_keys else "MISSED_SILENTLY"
            (held if k in review_keys else missed).append(k)
        else:
            t = got[0][1]
            if t["amount_satang"] != exp["amount"] or str(t["occurred_date"]) != exp["date"] or t["kind"] != exp["kind"]:
                status = "WRONG_VALUE"; wrong.append({"key": k, "file": got[0][0], "amount": [t["amount_satang"], exp["amount"]],
                                                      "date": [str(t["occurred_date"]), exp["date"]], "kind": [t["kind"], exp["kind"]]})
        items.append({"payment_key": k, "expected_file": exp["file"], "status": status, "imported_from": [f for f, _ in got]})
    unexpected = [k for k in actual_by_key if k not in expected_counted]

    exp_out = sum(v["amount"] for v in expected_counted.values() if v["kind"] == "expense")
    act_out = sum(t["amount_satang"] for t in counted if t["kind"] == "expense")
    exp_out_resolved = sum(v["amount"] for k, v in expected_counted.items() if v["kind"] == "expense" and k not in held)
    summary = {
        "source_run": a.run, "source_model": model_id, "images_uploaded": len(uploads), "simulated_inputs": simulated,
        "expected_payments": len(expected_counted), "counted_once": sum(1 for i in items if i["status"] == "counted_once"),
        "double_counted": double, "wrong_value": wrong, "missed_silently": missed,
        "held_in_review": {k: review_keys[k] for k in held}, "unexpected_counted_keys": unexpected,
        "open_review_items_by_reason": dict(Counter(r["reason"] for r in reviews)),
        "bills": {"expected": len(expected_bills), "created": len(bills)},
        "merged_duplicates": len(merged),
        "expense_total_satang": {"expected_all": exp_out, "counted": act_out,
                                 "expected_excluding_items_waiting_for_user": exp_out_resolved,
                                 "difference_vs_resolvable": act_out - exp_out_resolved},
        "verdict": "PASS" if not (double or wrong or missed or unexpected) and act_out == exp_out_resolved else "FAIL",
    }
    started = datetime.now(timezone.utc)
    out = REPO / "evidence" / "runs" / (started.strftime("%Y%m%dT%H%M%SZ") + "-" + a.slug)
    out.mkdir(parents=True)
    (out / "items.jsonl").write_text("\n".join(json.dumps(i, ensure_ascii=False, default=str) for i in items), encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps({
        "run_id": out.name, "kind": "pipeline replay (recorded real model outputs; no model calls; $0)",
        "uses_mocks": ["ReplayProvider returns outputs recorded in " + a.run] + (["SIMULATED inputs: see summary.simulated_inputs"] if simulated else []),
        "fixed_now": FIXED_NOW, "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "summary": summary}, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({"run_id": out.name, **summary}, ensure_ascii=False, indent=1, default=str))
    return 0 if summary["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
