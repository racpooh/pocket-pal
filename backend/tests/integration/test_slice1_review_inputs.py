"""UI slice 1 (Codex review finding 1): the inputs the app now offers in review are enough for the server to accept
items whose problem was a missing due date or an unknown transfer status, and the ledger follows the user's choice."""

from __future__ import annotations

import json

import pytest

from .conftest import BACKEND, User, drain, register

pytestmark = pytest.mark.db
VARIANTS = BACKEND / "fixtures" / "synthetic" / "review_variants"


def _variant(name: str) -> tuple[str, dict]:
    v = next(json.loads(x) for x in (VARIANTS / "variants.jsonl").read_text().splitlines() if x.strip() and json.loads(x)["file"] == name)
    return v["file"], v["fields"]


def _upload_variant(u: User, provider, db, storage, name: str) -> dict:
    file, fields = _variant(name)
    data = (VARIANTS / file).read_bytes()
    import hashlib

    provider.by_sha[hashlib.sha256(data).hexdigest()] = fields
    uid = u.upload(data).json()["upload_id"]
    drain(db, storage, provider)
    return next(i for i in u.req("GET", "/review-items").json()["items"] if i["upload_id"] == uid)


def test_bill_missing_due_date_resolves_to_a_bill_not_an_expense(client, db, storage, provider):
    u = User(client).onboard()
    item = _upload_variant(u, provider, db, storage, "var_bill_no_due_date.png")
    assert item["reason"] == "missing_fields" and item["problem_fields"] == ["due_date"]
    assert "accept" in item["allowed_decisions"]
    no_due = u.req("POST", f"/review-items/{item['id']}/resolve", json={"decision": "accept"})
    assert no_due.status_code == 400 and {"path": "due_date", "issue": "missing"} in no_due.json()["error"]["fields"]
    before = len(u.req("GET", "/transactions").json())
    r = u.req("POST", f"/review-items/{item['id']}/resolve", json={"decision": "accept", "fields": {"due_date_text": "2026-10-20"}})
    assert r.status_code == 200 and r.json().get("bill_id") and "txn_id" not in r.json()
    bill = next(b for b in u.req("GET", "/bills").json() if b["id"] == r.json()["bill_id"])
    assert bill["due_date"] == "2026-10-20" and bill["amount_due_satang"] == 360_000 and bill["status"] == "unpaid"
    assert len(u.req("GET", "/transactions").json()) == before  # no expense was created


@pytest.mark.parametrize("variant,choice,status,counted", [
    ("var_slip_status_unknown_a.png", "success", "completed", True),
    ("var_slip_status_unknown_b.png", "failed", "failed", False),
])
def test_unknown_status_follows_the_users_choice_in_the_ledger(client, db, storage, provider, variant, choice, status, counted):
    u = User(client).onboard()
    item = _upload_variant(u, provider, db, storage, variant)
    assert item["problem_fields"] == ["payment_status"] and item["extracted"]["status"] == "unknown"
    spend_before = u.req("GET", "/spending?from=2026-07-01&to=2026-11-01").json()["total_satang"]
    unchosen = u.req("POST", f"/review-items/{item['id']}/resolve", json={"decision": "accept"})
    assert unchosen.status_code == 400  # no status → nothing recorded; the app never picks one for the user
    r = u.req("POST", f"/review-items/{item['id']}/resolve", json={"decision": "accept", "fields": {"status": choice}})
    assert r.status_code == 200
    t = next(t for t in u.req("GET", "/transactions").json() if t["id"] == r.json()["txn_id"])
    assert t["payment_status"] == status
    spend_after = u.req("GET", "/spending?from=2026-07-01&to=2026-11-01").json()["total_satang"]
    assert (spend_after - spend_before) == (t["amount_satang"] if counted else 0)
