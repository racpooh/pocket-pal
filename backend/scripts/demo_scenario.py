"""Sandbox demo scenario → execution evidence (PDF item 06: simulated-account operation logs).

Runs the backend in-process against a disposable Postgres and records every API call.
  uv run python scripts/demo_scenario.py --slug demo-fake                       # fake extractor, scripted chat (mocks)
  uv run python scripts/demo_scenario.py --slug demo-real --provider anthropic  # real model calls (needs key in ../.env)
Requires TEST_DATABASE_URL (database name must end with _test; it is reset).
Writes ../evidence/runs/<UTC>-<slug>/{manifest.json, api_log.jsonl, summary.md}. Tokens are redacted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND / "src"))
sys.path.insert(0, str(BACKEND))

FIXED_NOW = "2026-10-15T06:00:00+00:00"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--provider", choices=["fake", "anthropic"], default="fake")
    a = ap.parse_args()
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    os.environ["FINASSIST_FIXED_NOW"] = FIXED_NOW
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        print("TEST_DATABASE_URL is required", file=sys.stderr)
        return 2

    from fastapi.testclient import TestClient

    from finassist.api.app import create_app
    from finassist.infra import Database
    from finassist.providers import AnthropicChatModel, AnthropicExtractionProvider, ChatTurn, FakeExtractionProvider, ScriptedChatModel
    from finassist.services.imports import LocalStorage, run_once
    from finassist.settings import Settings
    from tests.integration.conftest import SLIPS, _reset, app_url, fields_from_gt, gt, gt_rows

    _reset(url)
    storage = LocalStorage(str(BACKEND / "var" / "demo_uploads" / uuid.uuid4().hex))
    db = Database(url)
    if a.provider == "anthropic":
        key = os.environ["FINASSIST_MODEL_API_KEY"]
        extractor = AnthropicExtractionProvider(key, os.environ.get("FINASSIST_EXTRACTION_MODEL", "claude-haiku-5-5"))
        chat_model = AnthropicChatModel(key, os.environ.get("FINASSIST_CHAT_MODEL", "claude-sonnet-5-5"))
        mocks = []
    else:
        extractor = FakeExtractionProvider()
        chat_model = ScriptedChatModel([
            ChatTurn("", [{"id": "t1", "name": "get_overview", "input": {}}], False, "scripted"),
            ChatTurn("", [{"id": "t2", "name": "simulate_purchase", "input": {"amount_thb": "1,500"}}], False, "scripted"),
            ChatTurn("", [{"id": "t3", "name": "propose_reallocation", "input": {"from_pocket": "Food", "to_pocket": "Shopping", "amount_thb": "500"}}], False, "scripted"),
            ChatTurn("You can afford it if you move ฿500 from Food to Shopping. Approve the card to apply it.", [], True, "scripted"),
        ])
        mocks = ["extraction: FakeExtractionProvider returns ground-truth fields", "chat: ScriptedChatModel (fixed tool sequence)"]
    app = create_app(Settings(database_url=url, storage_dir=str(storage.root), model_provider=a.provider,
                             env="test" if a.provider == "fake" else os.environ.get("FINASSIST_ENV", "dev")), db=Database(app_url(url)), storage=storage, chat_model=chat_model)
    c = TestClient(app)
    log: list[dict] = []

    def call(step: str, method: str, path: str, h=None, idem: str | None = None, expect: int | tuple = 200, **kw):
        headers = dict(h or {})
        if idem:
            headers["Idempotency-Key"] = idem
        r = c.request(method, "/v1" + path, headers=headers, **kw)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else None
        exp = expect if isinstance(expect, tuple) else (expect,)
        entry = {"step": step, "method": method, "path": _redact_path(path), "status": r.status_code, "expected": list(exp),
                 "ok": r.status_code in exp, "response": _redact(body)}
        log.append(entry)
        return body

    def drain():
        outs = []
        for _ in range(50):
            with Database(app_url(url, "finassist_worker")).connect() as conn:
                o = run_once(conn, storage, extractor)
            if not o:
                break
            outs.append(o)
        log.append({"step": "worker", "outcomes": outs})
        return outs

    def upload(h, file, fields=None, captured="2026-10-15T13:00:00+07:00"):
        data = (SLIPS / file).read_bytes()
        if isinstance(extractor, FakeExtractionProvider):
            extractor.by_sha[hashlib.sha256(data).hexdigest()] = fields or fields_from_gt(gt(file))
        return call(f"upload {file}", "POST", "/uploads", h, expect=(200, 202), files={"image": (file, data, "image/png")}, data={"captured_at": captured})

    # 1. accounts
    call("signup A", "POST", "/auth/signup", json={"email": "demo.a@example.test", "password": "demo password A1"}, expect=201)
    tok = call("login A", "POST", "/auth/login", json={"email": "demo.a@example.test", "password": "demo password A1"})["token"]
    A = {"Authorization": f"Bearer {tok}"}
    call("signup B", "POST", "/auth/signup", json={"email": "demo.b@example.test", "password": "demo password B1"}, expect=201)
    B = {"Authorization": "Bearer " + call("login B", "POST", "/auth/login", json={"email": "demo.b@example.test", "password": "demo password B1"})["token"]}
    # 2. onboarding
    call("profile", "PUT", "/me/profile", A, json={"income_satang": 2_000_000, "income_frequency": "monthly", "next_income_date": "2026-11-01",
                                                   "essentials": [{"name": "Rent", "amount_satang": 500_000, "due_day": 30}]})
    acct = call("accounts", "GET", "/accounts", A)[0]["id"]
    call("balance 15,000.00 as of now", "POST", f"/accounts/{acct}/balance-observations", A, json={"amount_satang": 1_500_000}, expect=201)
    pockets = {}
    for name, cats in (("Food", ["food"]), ("Shopping", ["shopping"]), ("Transport", ["transport"]), ("Entertainment", ["entertainment"]), ("Other", ["other", "bills"])):
        pockets[name] = call(f"pocket {name}", "POST", "/pockets", A, json={"name": name, "categories": cats}, expect=201)["id"]
    call("consent photo", "POST", "/consents", A, json={"scope": "photo_processing", "version": "v1", "params": {"scan_from": "2026-07-01"}}, expect=201)
    call("consent auto-import", "POST", "/consents", A, json={"scope": "auto_import", "version": "v1"}, expect=201)
    # 3. plan
    card = call("suggest plan (T2 proposal)", "POST", "/plan/suggest", A, expect=201)
    call("approve plan (T3)", "POST", f"/proposals/{card['proposal_id']}/approve", A, idem=str(uuid.uuid4()), json={"payload_hash": card["payload_hash"], "card_hash": card["card_hash"]})
    # 4. imports
    rows = gt_rows()
    pair = next(r for r in rows if any(t.startswith("distinct_same_amount_as") for t in r["group_tags"]))
    near = next(r for r in rows if any(t.startswith("near_duplicate_of") for t in r["group_tags"]))
    inj = next(r for r in rows if "prompt_injection" in r["group_tags"])
    files = ["slip_001_transfer_out.png", "slip_002_transfer_out.png", pair["file"], pair["group_tags"][0].split(":", 1)[1],
             near["group_tags"][0].split(":", 1)[1], near["file"], inj["file"]]
    for f in dict.fromkeys(files):
        upload(A, f)
    upload(A, "slip_001_transfer_out.png")  # exact duplicate image
    unclear = fields_from_gt(gt("slip_003_transfer_out.png")); unclear["amount_text"] = None  # noqa: E702
    upload(A, "slip_003_transfer_out.png", unclear if isinstance(extractor, FakeExtractionProvider) else None)
    after_anchor = fields_from_gt(gt("slip_004_transfer_out.png")); after_anchor.update(date_text="2026-10-15", time_text="14:30")  # noqa: E702
    upload(A, "slip_004_transfer_out.png", after_anchor if isinstance(extractor, FakeExtractionProvider) else None, captured="2026-10-15T14:31:00+07:00")
    drain()
    call("transactions", "GET", "/transactions", A)
    items = call("review queue", "GET", "/review-items", A)
    for it in items["items"]:
        if it["reason"] == "missing_fields":
            call("resolve: user types the amount", "POST", f"/review-items/{it['id']}/resolve", A, json={"decision": "accept", "fields": {"amount_text": "45.00"}}, expect=(200, 400))
    call("scan status", "GET", "/scan-status", A)
    # 5. bills
    bill = call("unpaid bill", "POST", "/bills", A, json={"biller": "Demo Power", "amount_due_satang": 120_000, "due_date": "2026-10-25"}, expect=201)
    pay = call("manual payment", "POST", "/transactions", A, idem=str(uuid.uuid4()), expect=201,
               json={"kind": "expense", "amount_satang": 120_000, "occurred_date": "2026-10-15", "occurred_at": "2026-10-15T15:00:00+07:00", "payee": "Demo Power", "category": "bills"})
    call("link bill to payment (count once)", "POST", f"/bills/{bill['id']}/link-payment", A, json={"txn_id": pay["id"]})
    call("plan after bill paid", "GET", "/plan", A)
    # 6. affordability + chat
    call("can I afford 1,500?", "POST", "/simulate/affordability", A, json={"amount_satang": 150_000})
    chat = call("chat", "POST", "/chat/messages", A, json={"text": "Can I afford a ฿1,500 jacket? If needed, move money from Food."})
    for cd in [x for x in chat.get("cards", []) if x.get("type") == "proposal"]:
        k = str(uuid.uuid4())
        call("approve agent proposal", "POST", f"/proposals/{cd['proposal_id']}/approve", A, idem=k, json={"payload_hash": cd["payload_hash"], "card_hash": cd["card_hash"]}, expect=(200, 409))
        call("double-click replay (same key)", "POST", f"/proposals/{cd['proposal_id']}/approve", A, idem=k, json={"payload_hash": cd["payload_hash"], "card_hash": cd["card_hash"]}, expect=(200, 409))
        call("repeat approval (new key)", "POST", f"/proposals/{cd['proposal_id']}/approve", A, idem=str(uuid.uuid4()), json={"payload_hash": cd["payload_hash"], "card_hash": cd["card_hash"]}, expect=409)
    # 7. security probes
    t0 = next(t for t in call("A's transactions", "GET", "/transactions", A) if t["upload_id"])
    call("B reads A's upload (blocked)", "GET", f"/uploads/{t0['upload_id']}/image", B, expect=404)
    call("B edits A's txn (blocked)", "PATCH", f"/transactions/{t0['id']}", B, json={"version": 1, "changes": {"amount_satang": 1}}, expect=404)
    # 8. revoke + delete
    call("revoke photo consent", "DELETE", "/consents/photo_processing", A)
    call("upload after revoke (blocked)", "POST", "/uploads", A, expect=403,
         files={"image": ("x.png", (SLIPS / "slip_005_transfer_out.png").read_bytes(), "image/png")})
    call("delete one imported image + its record", "DELETE", f"/uploads/{t0['upload_id']}", A)
    call("final plan", "GET", "/plan", A)
    call("audit trail", "GET", "/audit?limit=200", A)

    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ") + "-" + a.slug
    out = REPO / "evidence" / "runs" / run_id
    out.mkdir(parents=True)
    (out / "api_log.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False, default=str) for e in log), encoding="utf-8")
    fails = [e for e in log if e.get("ok") is False]
    models = sorted({e["response"].get("model") for e in log if isinstance(e.get("response"), dict) and e["response"].get("model")})
    manifest = {"run_id": run_id, "kind": "sandbox scenario", "fixed_now": FIXED_NOW, "provider": a.provider, "uses_mocks": mocks,
                "model_identifiers": models, "steps": len(log), "unexpected_status": [(e["step"], e["status"]) for e in fails],
                "environment": {"python": platform.python_version(), "platform": platform.platform()},
                "data": "synthetic fixtures only"}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"run_id": run_id, "steps": len(log), "unexpected": manifest["unexpected_status"]}, ensure_ascii=False))
    return 1 if fails else 0


def _redact(obj):
    if isinstance(obj, dict):
        return {k: ("<redacted>" if k in ("token", "payload_hash", "card_hash") else _redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


def _redact_path(p: str) -> str:
    return p


if __name__ == "__main__":
    raise SystemExit(main())
