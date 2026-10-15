"""INT-* / CALC-* end-to-end via API + Postgres. Extraction is FAKE (perfect extractor from ground truth)."""

from __future__ import annotations

import pytest

from .conftest import User, drain, fields_from_gt, gt, gt_rows, register

pytestmark = pytest.mark.db


def test_e2e_slip_import_updates_plan(client, db, storage, provider):
    u = User(client).onboard()
    u.approve_plan()
    before = u.req("GET", "/plan").json()
    data = register(provider, "slip_004_transfer_out.png")  # 200.00 transport, 14 Oct 2026 (before balance anchor)
    r = u.upload(data)
    assert r.status_code == 202, r.text
    assert drain(db, storage, provider) == ["imported"]
    txns = u.req("GET", "/transactions").json()
    assert len(txns) == 1 and txns[0]["source"] == "auto_import" and txns[0]["amount_satang"] == 20_000
    after = u.req("GET", "/plan").json()
    # FI-8: the slip is dated before the balance observation → balance and money left unchanged
    assert after["cashflow"]["available_balance_satang"] == before["cashflow"]["available_balance_satang"]
    # The plan period starts today (15 Oct), so the 14 Oct slip is history only, not pocket spending.
    other = [p for p in after["pockets"] if p["pocket_id"] is None][0]
    assert other["unassigned_satang"] == 0


def test_slip_after_anchor_reduces_money_left(client, db, storage, provider):
    u = User(client).onboard()
    f = fields_from_gt(gt("slip_001_transfer_out.png"))
    f.update(date_text="2026-10-15", time_text="14:30")  # after 13:00 anchor
    data = register(provider, "slip_001_transfer_out.png", f)
    before = u.req("GET", "/plan").json()["cashflow"]["discretionary_satang"]
    u.upload(data, captured_at="2026-10-15T14:31:00+07:00")
    assert drain(db, storage, provider) == ["imported"]
    after = u.req("GET", "/plan").json()["cashflow"]["discretionary_satang"]
    assert before - after == 1_000


def test_exact_duplicate_image_is_idempotent(client, db, storage, provider):
    u = User(client).onboard()
    data = register(provider, "slip_001_transfer_out.png")
    a, b = u.upload(data).json(), u.upload(data).json()
    assert a["upload_id"] == b["upload_id"] and b["duplicate_image"] is True
    drain(db, storage, provider)
    assert len(u.req("GET", "/transactions").json()) == 1


def test_same_bank_ref_different_image_counts_once(client, db, storage, provider):
    u = User(client).onboard()
    rows = [r for r in gt_rows() if any(t.startswith("near_duplicate_of") for t in r["group_tags"])]
    near = rows[0]
    original = near["group_tags"][0].split(":", 1)[1]
    u.upload(register(provider, original))
    u.upload(register(provider, near["file"]))
    outcomes = drain(db, storage, provider)
    assert sorted(outcomes) == ["imported", "merged_duplicate"]
    assert len(u.req("GET", "/transactions").json()) == 1


def test_two_waters_same_amount_different_refs_are_two(client, db, storage, provider):
    u = User(client).onboard()
    pair = [r for r in gt_rows() if any(t.startswith("distinct_same_amount_as") for t in r["group_tags"])][0]
    other = pair["group_tags"][0].split(":", 1)[1]
    u.upload(register(provider, pair["file"]))
    u.upload(register(provider, other))
    assert sorted(drain(db, storage, provider)) == ["imported", "imported"]
    assert len(u.req("GET", "/transactions").json()) == 2


def test_receipt_and_slip_count_once(client, db, storage, provider):
    u = User(client).onboard()
    from .conftest import gt_rows

    rec = [r for r in gt_rows() if any(t.startswith("same_purchase_as") for t in r["group_tags"]) and r["doc_type"] == "receipt"][0]
    slip = rec["group_tags"][0].split(":", 1)[1] if gt(rec["group_tags"][0].split(":", 1)[1])["doc_type"] != "receipt" else None
    assert slip, "fixture must pair a receipt with a slip"
    u.upload(register(provider, slip))
    drain(db, storage, provider)
    u.upload(register(provider, rec["file"]))
    assert drain(db, storage, provider) == ["needs_review"]
    item = u.req("GET", "/review-items").json()["items"][0]
    assert item["reason"] == "receipt_link"
    r = u.req("POST", f"/review-items/{item['id']}/resolve", json={"decision": "link_receipt"})
    assert r.status_code == 200, r.text
    txns = u.req("GET", "/transactions").json()
    assert len(txns) == 1


def test_unclear_amount_goes_to_review_and_is_excluded(client, db, storage, provider):
    u = User(client).onboard()
    f = fields_from_gt(gt("slip_001_transfer_out.png"))
    f["amount_text"] = None
    u.upload(register(provider, "slip_001_transfer_out.png", f))
    assert drain(db, storage, provider) == ["needs_review"]
    assert u.req("GET", "/transactions").json() == []
    item = u.req("GET", "/review-items").json()["items"][0]
    assert item["reason"] == "missing_fields" and "amount" in item["problem_fields"]
    r = u.req("POST", f"/review-items/{item['id']}/resolve", json={"decision": "accept", "fields": {"amount_text": "10.00"}})
    assert r.status_code == 200, r.text
    assert len(u.req("GET", "/transactions").json()) == 1


def test_no_auto_import_consent_means_confirm_in_review(client, db, storage, provider):
    u = User(client).onboard(auto_import=False)
    u.upload(register(provider, "slip_001_transfer_out.png"))
    assert drain(db, storage, provider) == ["needs_review"]
    assert u.req("GET", "/review-items").json()["items"][0]["reason"] == "confirm_import"


def test_pending_slip_recorded_but_excluded_from_totals(client, db, storage, provider):
    u = User(client).onboard()
    f = fields_from_gt(gt("slip_001_transfer_out.png"))
    f.update(status="pending", date_text="2026-10-15", time_text="14:00")
    u.upload(register(provider, "slip_001_transfer_out.png", f), captured_at="2026-10-15T14:01:00+07:00")
    before = u.req("GET", "/plan").json()["cashflow"]["discretionary_satang"]
    drain(db, storage, provider)
    t = u.req("GET", "/transactions").json()[0]
    assert t["payment_status"] == "pending"
    assert u.req("GET", "/plan").json()["cashflow"]["discretionary_satang"] == before


def test_bill_then_payment_counts_once(client, db, storage, provider):
    u = User(client).onboard()
    bill = u.req("POST", "/bills", json={"biller": "Demo Power", "amount_due_satang": 120_000, "due_date": "2026-10-25"}).json()
    p1 = u.req("GET", "/plan").json()["cashflow"]
    pay = u.req("POST", "/transactions", idem=True, json={"kind": "expense", "amount_satang": 120_000, "occurred_date": "2026-10-15",
                                                          "occurred_at": "2026-10-15T14:00:00+07:00", "payee": "Demo Power", "category": "bills"}).json()
    p2 = u.req("GET", "/plan").json()["cashflow"]
    # before linking, the bill is still a commitment AND the payment reduced the balance → counted twice (visible)
    assert p1["discretionary_satang"] - p2["discretionary_satang"] == 120_000
    r = u.req("POST", f"/bills/{bill['id']}/link-payment", json={"txn_id": pay["id"]})
    assert r.status_code == 200 and r.json()["status"] == "paid"
    p3 = u.req("GET", "/plan").json()["cashflow"]
    assert p3["discretionary_satang"] == p1["discretionary_satang"]  # counted once
    again = u.req("POST", f"/bills/{bill['id']}/link-payment", json={"txn_id": pay["id"]})
    assert again.status_code == 409


def test_manual_duplicate_check_and_confirm(client, db, storage, provider):
    u = User(client).onboard()
    u.upload(register(provider, "slip_001_transfer_out.png"))
    drain(db, storage, provider)
    t = gt("slip_001_transfer_out.png")
    body = {"kind": "expense", "amount_satang": t["amount_satang"], "occurred_date": t["occurred_at"][:10], "payee": t["payee_display"]}
    r = u.req("POST", "/transactions", idem=True, json=body)
    assert r.status_code == 409 and r.json()["error"]["code"] == "POSSIBLE_DUPLICATE"
    r2 = u.req("POST", "/transactions", idem=True, json={**body, "confirm_distinct": True})
    assert r2.status_code == 201


def test_refund_reconciles_and_cannot_exceed(client):
    u = User(client).onboard()
    e = u.req("POST", "/transactions", idem=True, json={"kind": "expense", "amount_satang": 50_000, "occurred_date": "2026-10-15",
                                                        "occurred_at": "2026-10-15T14:00:00+07:00", "category": "shopping"}).json()
    ok = u.req("POST", "/transactions", idem=True, json={"kind": "refund", "amount_satang": 20_000, "occurred_date": "2026-10-15",
                                                         "occurred_at": "2026-10-15T15:00:00+07:00", "refund_of": e["id"]})
    assert ok.status_code == 201
    over = u.req("POST", "/transactions", idem=True, json={"kind": "refund", "amount_satang": 30_001, "occurred_date": "2026-10-15",
                                                           "refund_of": e["id"]})
    assert over.status_code == 400


def test_affordability_has_no_side_effects(client, db):
    u = User(client).onboard()
    with db.connect() as c:
        counts = lambda: [c.execute(f"select count(*) n from {t}").fetchone()["n"] for t in ("txn", "proposal", "bill", "budget_plan")]  # noqa: E731
        before = counts()
        r = u.req("POST", "/simulate/affordability", json={"amount_satang": 300_000})
        assert r.status_code == 200 and r.json()["recorded"] is False
        assert counts() == before


def test_budget_plan_reconciles(client):
    u = User(client).onboard()
    card = u.req("POST", "/plan/suggest").json()
    disc = card["card"]["extra"]["calculation"]["discretionary_satang"]
    assert sum(card["payload"]["allocations"].values()) == disc  # FI-16: allocations + unallocated == discretionary
    r = u.req("POST", f"/proposals/{card['proposal_id']}/approve", idem=True, json={"payload_hash": card["payload_hash"], "card_hash": card["card_hash"]})
    assert r.status_code == 200
    pockets = u.req("GET", "/plan").json()["pockets"]
    assert sum(p["allocation_satang"] for p in pockets if p["pocket_id"]) == disc


def test_reallocation_conserves_total_and_creates_no_expense(client):
    u = User(client).onboard()
    u.approve_plan()
    plan = u.req("GET", "/plan").json()
    total = sum(p["allocation_satang"] for p in plan["pockets"] if p["pocket_id"])
    card = u.req("POST", "/proposals", json={"kind": "reallocate", "payload": {
        "plan_id": plan["plan"]["id"], "from_pocket": u.pockets["Food"], "to_pocket": u.pockets["Shopping"], "amount_satang": 50_000}}).json()
    assert u.req("POST", f"/proposals/{card['proposal_id']}/approve", idem=True, json={"payload_hash": card["payload_hash"], "card_hash": card["card_hash"]}).status_code == 200
    plan2 = u.req("GET", "/plan").json()
    assert sum(p["allocation_satang"] for p in plan2["pockets"] if p["pocket_id"]) == total
    assert u.req("GET", "/transactions").json() == []
    assert plan2["cashflow"]["discretionary_satang"] == plan["cashflow"]["discretionary_satang"]


def test_goal_feasibility_and_alternatives(client):
    u = User(client).onboard()
    r = u.req("POST", "/goals/feasibility", json={"target_satang": 50_000_000, "saved_satang": 0, "deadline": "2027-01-31"}).json()
    assert r["feasible"] is False and r["later_deadline"] and r["smaller_target_satang"] is not None


def test_scan_status_reports_last_success_and_pause(client, db, storage, provider):
    u = User(client).onboard()
    u.upload(register(provider, "slip_001_transfer_out.png"))
    drain(db, storage, provider)
    s = u.req("GET", "/scan-status").json()
    assert s["processing_allowed"] is True and s["last_successful_processing_at"] and s["counts"] == {"imported": 1}
    u.req("DELETE", "/consents/photo_processing")
    assert u.req("GET", "/scan-status").json()["processing_allowed"] is False


def test_tradeoff_proposal_conserves_and_requires_approval(client):
    u = User(client).onboard()
    u.approve_plan()
    u.req("POST", "/transactions", idem=True, json={"kind": "expense", "amount_satang": 30_000, "occurred_date": "2026-10-15",
                                                    "occurred_at": "2026-10-15T14:00:00+07:00", "category": "food"})
    before = {p["name"]: p["allocation_satang"] for p in u.req("GET", "/plan").json()["pockets"] if p["pocket_id"]}
    card = u.req("POST", "/plan/tradeoff", json={"pocket_id": u.pockets["Shopping"], "increase_satang": 100_000})
    assert card.status_code == 201, card.text
    card = card.json()
    assert {p["name"]: p["allocation_satang"] for p in u.req("GET", "/plan").json()["pockets"] if p["pocket_id"]} == before
    r = u.req("POST", f"/proposals/{card['proposal_id']}/approve", idem=True, json={"payload_hash": card["payload_hash"], "card_hash": card["card_hash"]})
    assert r.status_code == 200, r.text
    after = {p["name"]: p["allocation_satang"] for p in u.req("GET", "/plan").json()["pockets"] if p["pocket_id"]}
    assert sum(after.values()) == sum(before.values())
    assert after["Shopping"] == before["Shopping"] + 100_000


def test_insights_and_spending_report(client):
    u = User(client).onboard()
    for i, (d, amt) in enumerate([("2026-07-01", 41_900), ("2026-08-01", 41_900), ("2026-09-01", 49_900)]):
        u.req("POST", "/transactions", idem=True, json={"kind": "expense", "amount_satang": amt, "occurred_date": d, "payee": "Demo Stream", "category": "entertainment"})
    ins = u.req("GET", "/insights").json()
    assert ins["recurring"] and ins["recurring"][0]["payee_key"] == "demo stream" and ins["recurring"][0]["changed"] is True
    rep = u.req("GET", "/spending?from=2026-07-01&to=2026-10-01").json()
    assert rep["total_satang"] == 133_700 and rep["top_payees"][0]["payee_key"] == "demo stream"
