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


def test_web_review_preserves_readable_bill_due_date(client, db, storage, provider):
    """The web form must receive a due date already read while reviewing another field."""
    import hashlib
    u = User(client).onboard()
    file, fields = _variant("var_bill_no_due_date.png")
    fields = {**fields, "due_date_text": "2026-10-20", "amount_text": None}
    data = (VARIANTS / file).read_bytes()
    provider.by_sha[hashlib.sha256(data).hexdigest()] = fields
    uid = u.upload(data).json()["upload_id"]
    drain(db, storage, provider)
    item = next(i for i in u.req("GET", "/review-items").json()["items"] if i["upload_id"] == uid)
    assert item["extracted"]["due_date_text"] == "2026-10-20"


def test_web_replanning_uses_latest_period_and_does_not_revive_old_plan(client, db):
    from datetime import date, timedelta
    from finassist.services import budget
    from finassist.infra import set_owner
    u = User(client).onboard()
    today = date.fromisoformat(u.req("GET", "/plan").json()["today"])
    for start, end, buffer in ((today-timedelta(days=1), today+timedelta(days=10), 0),
                               (today, today+timedelta(days=2), 50_000)):
        card = u.req("POST", "/proposals", json={"kind":"budget_plan", "payload":{
            "period_start":str(start), "period_end":str(end), "buffer_satang":buffer,
            "allocations":{u.pockets["Food"]:100_000}}}).json()
        response = u.req("POST", f"/proposals/{card['proposal_id']}/approve", idem=True,
                         json={"payload_hash":card["payload_hash"],"card_hash":card["card_hash"]})
        assert response.status_code == 200, response.text
    plan = u.req("GET", "/plan").json()["plan"]
    assert plan["period_start"] == str(today) and plan["buffer_satang"] == 50_000
    owner = u.req("GET", "/me").json()["user_id"]
    with db.connect() as conn:
        set_owner(conn, owner)
        assert budget.current_plan(conn, owner, today+timedelta(days=3)) is None


def test_category_assignment_updates_only_its_budget_period_and_chat_explains_scope(client, db):
    """Reproduce category editing through the API, including a historical slip."""
    from finassist.infra import set_owner
    from finassist.services.agent import run_tool
    u = User(client).onboard()
    u.approve_plan()
    def food_spent():
        return next(p for p in u.req("GET", "/plan").json()["pockets"] if p["pocket_id"] == u.pockets["Food"])["spent_confirmed_satang"]
    assert food_spent() == 0
    for day, amount, expected in (("2026-10-13", 10_000, 0), ("2026-10-15", 12_000, 12_000)):
        created = u.req("POST", "/transactions", idem=True, json={"kind":"expense", "amount_satang":amount, "occurred_date":day, "payee":"Synthetic cafe"})
        assert created.status_code == 201, created.text
        txn = next(t for t in u.req("GET", "/transactions").json() if t["occurred_date"] == day)
        changed = u.req("PATCH", f"/transactions/{txn['id']}", json={"version":txn["version"], "changes":{"category":"food"}})
        assert changed.status_code == 200, changed.text
        assert food_spent() == expected
    assert u.req("GET", "/spending?from=2026-10-01&to=2026-11-01").json()["total_satang"] == 22_000
    owner = u.req("GET", "/me").json()["user_id"]
    with db.connect() as conn:
        set_owner(conn, owner)
        result = run_tool(conn, owner, "get_overview", {}, [])
    assert result["today"] == "2026-10-15"
    assert result["next_income_date"] == "2026-11-01"
    assert result["budget_period"] == {"start":"2026-10-15", "end_exclusive":"2026-11-01"}
    assert "older categorized transactions" in result["pocket_spending_scope"]
    assert "on or after" in result["bill_reservation_policy"]
