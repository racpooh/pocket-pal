"""Chat grounding (P0 1–3): server date context in the system prompt, server-computed spending facts, and the
monthly→per-income-event unit fix in insights. Chat model is SCRIPTED; this does not measure real-model quality."""

from __future__ import annotations

import json
import uuid

import pytest

from finassist.providers import ChatTurn, ScriptedChatModel
from finassist.services import agent, budget

from .conftest import User

pytestmark = pytest.mark.db
MARK = "Server context for this message (trusted, computed by the server, not from the user):\n"


def _owner(db, u: User):
    with db.connect() as c:
        return c.execute("select id from app_user where email=%s", (u.email,)).fetchone()["id"]


def _spend(u: User, amount: int, category: str | None, day: str, kind: str = "expense", refund_of: str | None = None) -> dict:
    body = {"kind": kind, "amount_satang": amount, "occurred_date": day, "occurred_at": f"{day}T12:00:00+07:00",
            "payee": f"shop-{uuid.uuid4().hex[:6]}"}
    if category:
        body["category"] = category
    if refund_of:
        body["refund_of"] = refund_of
    r = u.req("POST", "/transactions", idem=True, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _ctx(model: ScriptedChatModel) -> dict:
    system = model.systems[0]
    assert MARK in system
    return json.loads(system.split(MARK, 1)[1])


@pytest.mark.parametrize("now,today,this_start,last", [
    ("2026-10-31T17:30:00+00:00", "2026-11-01", "2026-11-01", ("2026-10-01", "2026-11-01")),  # 00:30 ICT next day
    ("2026-10-31T16:59:00+00:00", "2026-10-31", "2026-10-01", ("2026-09-01", "2026-10-01")),  # 23:59 ICT
])
def test_system_prompt_carries_server_date_in_user_timezone_without_identifiers(client, db, monkeypatch, now, today, this_start, last):
    u = User(client).onboard()
    owner = _owner(db, u)
    monkeypatch.setenv("FINASSIST_FIXED_NOW", now)
    model = ScriptedChatModel([ChatTurn("Hello.", [], True, "scripted")])
    with db.connect() as conn:
        out = agent.chat(conn, owner, "hi", model)
    assert out["tools_used"] == []  # a greeting does not force financial tools
    ctx = _ctx(model)
    assert ctx["today"] == today and ctx["timezone"] == "Asia/Bangkok"
    assert ctx["periods"]["today"] == {"start": today, "end_exclusive": ctx["periods"]["today"]["end_exclusive"]}
    assert ctx["periods"]["this_month_to_date"]["start"] == this_start
    assert (ctx["periods"]["last_month"]["start"], ctx["periods"]["last_month"]["end_exclusive"]) == last
    assert u.email not in model.systems[0] and str(owner) not in model.systems[0]


def test_get_spending_returns_server_ranked_totals_with_refunds_unassigned_and_predicted(client, db):
    u = User(client).onboard()
    owner = _owner(db, u)
    _spend(u, 30_000, "food", "2026-10-10")
    pred = _spend(u, 5_000, "food", "2026-10-11")
    shop = _spend(u, 35_000, "shopping", "2026-10-12")
    _spend(u, 12_000, None, "2026-10-13")                          # unassigned
    _spend(u, 2_000, None, "2026-10-14", kind="refund", refund_of=shop["id"])  # linked refund nets shopping
    _spend(u, 7_000, None, "2026-10-14", kind="refund")           # unlinked refund: reported, not netted
    _spend(u, 99_900, "food", "2026-09-30")                        # outside the range
    with db.connect() as conn:
        conn.execute("update txn set category_state='predicted' where id=%s", (pred["id"],))
        out = agent.run_tool(conn, owner, "get_spending", {"start": "2026-10-01", "end_exclusive": "2026-10-16"}, [])
    # Backward-compatible fields are unchanged in meaning.
    assert out["by_category"]["food"] == {"confirmed": 30_000, "predicted": 5_000}
    assert out["unassigned_satang"] == 12_000
    assert out["total_satang"] == 30_000 + 5_000 + 35_000 - 2_000 + 12_000
    # Added fields.
    assert [r["category"] for r in out["ranked_categories"]] == ["food", "shopping"]
    assert out["ranked_categories"][0] == {"category": "food", "total_satang": 35_000, "confirmed_satang": 30_000,
                                           "predicted_satang": 5_000, "display": "350.00"}
    assert out["ranked_categories"][1]["total_satang"] == 33_000
    assert out["unlinked_refunds_satang"] == 7_000
    assert out["display"] == {"total": "800.00", "unassigned": "120.00", "unlinked_refunds": "70.00"}
    assert out["period"] == {"start": "2026-10-01", "end_exclusive": "2026-10-16", "days": 15}
    assert out["counted_records"] == 6 and "empty_note" not in out


def test_get_spending_with_no_records_says_absence_not_zero_spending_and_rejects_bad_range(client, db):
    u = User(client).onboard()
    owner = _owner(db, u)
    with db.connect() as conn:
        out = agent.run_tool(conn, owner, "get_spending", {"start": "2026-09-01", "end_exclusive": "2026-10-01"}, [])
        bad = agent.run_tool(conn, owner, "get_spending", {"start": "2026-10-01", "end_exclusive": "2026-10-01"}, [])
    assert out["counted_records"] == 0 and out["ranked_categories"] == [] and out["total_satang"] == 0
    assert "not proof that nothing was spent" in out["empty_note"]
    assert bad["error"] == "invalid_range"


@pytest.mark.parametrize("frequency,added", [("monthly", 100_000), ("biweekly", 46_153), ("weekly", 23_076), ("irregular", None)])
def test_insights_converts_monthly_savings_to_per_income_event(client, db, frequency, added):
    u = User(client).onboard()
    r = u.req("PUT", "/me/profile", json={"income_satang": 2_000_000, "income_frequency": frequency, "next_income_date": "2026-11-01",
                                         "essentials": [{"name": "Rent", "amount_satang": 500_000, "due_day": 30}]})
    assert r.status_code == 200, r.text
    owner = _owner(db, u)
    _spend(u, 100_000, "food", "2026-08-10")
    _spend(u, 200_000, "food", "2026-09-10")   # last complete month +1,000 THB vs average → recommendation
    with db.connect() as conn:
        conn.execute("insert into goal(owner_id,name,target_satang,saved_satang,deadline,status) values (%s,'Trip',5000000,0,'2027-03-01','active')", (owner,))
        ins = budget.insights(conn, owner)
    rec = next(x for x in ins["recommendations"] if x["category"] == "food")
    assert rec["estimated_savings_per_month_satang"] == 100_000
    impact = rec["goal_impact"][0]
    if added is None:
        assert impact["goal_impact_unavailable"] is True and "feasible_after" not in impact
    else:
        assert impact["added_capacity_per_income_event_satang"] == added
        assert impact["income_frequency"] == frequency


def test_insights_does_not_project_goal_impact_from_unavailable_plan(client, db, monkeypatch):
    u = User(client).onboard()
    owner = _owner(db, u)
    _spend(u, 100_000, "food", "2026-08-10")
    _spend(u, 200_000, "food", "2026-09-10")
    # A previously valid income schedule becomes stale as the clock advances.
    monkeypatch.setenv("FINASSIST_FIXED_NOW", "2026-10-15T06:00:00+00:00")
    with db.connect() as conn:
        conn.execute("update income_schedule set next_income_date='2026-10-01' where owner_id=%s", (owner,))
        conn.execute("insert into goal(owner_id,name,target_satang,saved_satang,deadline,status) values (%s,'Trip',5000000,0,'2027-03-01','active')", (owner,))
        out = budget.insights(conn, owner)
    assert out["plan_unavailable"] == "NEXT_INCOME_DATE_PASSED"
    rec = next(r for r in out["recommendations"] if r["category"] == "food")
    assert rec["estimated_savings_per_month_satang"] == 100_000
    impact = rec["goal_impact"][0]
    assert impact["goal_impact_unavailable"] is True
    assert impact["plan_error"] == "NEXT_INCOME_DATE_PASSED"
    assert not any(k.startswith(("feasible_", "later_deadline_")) for k in impact)
    assert "added_capacity_per_income_event_satang" not in impact
