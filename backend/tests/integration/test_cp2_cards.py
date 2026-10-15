"""Approval cards (FI-31..FI-33): deterministic content, persistence across reloads, binding to the approval,
edit = new proposal. Chat model is SCRIPTED where used; no model computes anything here."""

from __future__ import annotations

import uuid

import psycopg
import pytest

from finassist.infra import canonical_json, sha256
from finassist.providers import ChatTurn, ScriptedChatModel
from finassist.services import agent

from .conftest import User

pytestmark = pytest.mark.db


def _owner(db, u: User):
    with db.connect() as c:
        return c.execute("select id from app_user where email=%s", (u.email,)).fetchone()["id"]


def _spend(u: User, amount: int, category: str | None, *, day: str = "2026-10-15", hour: int = 12):
    body = {"kind": "expense", "amount_satang": amount, "occurred_date": day, "occurred_at": f"{day}T{hour:02d}:00:00+07:00",
            "payee": f"shop-{uuid.uuid4().hex[:6]}"}
    if category:
        body["category"] = category
    r = u.req("POST", "/transactions", idem=True, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _plan(u: User) -> dict:
    return u.req("GET", "/plan").json()


def _pocket(u: User, name: str) -> dict:
    return next(p for p in _plan(u)["pockets"] if p["name"] == name)


def _realloc(u: User, amount: int, src: str = "Food", dst: str = "Shopping"):
    plan = _plan(u)["plan"]
    return u.req("POST", "/proposals", json={"kind": "reallocate", "payload": {
        "plan_id": plan["id"], "from_pocket": u.pockets[src], "to_pocket": u.pockets[dst], "amount_satang": amount}})


def _approve(u: User, view: dict, **override):
    body = {"payload_hash": view["payload_hash"], "card_hash": view["card_hash"], **override}
    return u.req("POST", f"/proposals/{view['proposal_id']}/approve", idem=True, json=body)


def _codes(view: dict, key: str = "warnings") -> list[str]:
    return [w["code"] for w in view["card"][key]]


# ---------------- content ----------------

def test_card_move_all_remaining_food_to_shopping(client):
    """The case seen in the real agent demo: move all unspent Food to Shopping."""
    u = User(client).onboard()
    u.approve_plan()                      # Food 4,000 / Shopping 1,500 of 10,000 money left
    _spend(u, 25_000, "food")             # ฿250 spent on food → ฿3,750 unspent
    r = _realloc(u, 375_000)
    assert r.status_code == 201, r.text
    v = r.json()
    c = v["card"]
    assert c["summary"] == {"code": "REALLOCATE", "text": "Move ฿3,750.00 of budget from Food to Shopping."}
    food, shop = (next(x for x in c["changes"] if x["name"] == n) for n in ("Food", "Shopping"))
    assert (food["allocation_before_satang"], food["allocation_after_satang"]) == (400_000, 25_000)
    assert (food["remaining_before_satang"], food["remaining_after_satang"]) == (375_000, 0)
    assert (shop["allocation_before_satang"], shop["allocation_after_satang"]) == (150_000, 525_000)
    assert c["transfer"]["amount_satang"] == 375_000 and c["transfer"]["from"]["remaining_after_satang"] == 0
    assert _codes(v) == ["MOVES_ALL_REMAINING"] and c["warnings"][0]["severity"] == "high"
    e = c["effects"]
    # the ฿250 was spent at 12:00, before the 13:00 balance entry → already in the balance (FI-8): money left stays ฿10,000
    assert e["money_left"]["before_satang"] == e["money_left"]["after_satang"] == 1_000_000
    assert e["buffer"] == {"before_satang": 0, "after_satang": 0}
    assert e["commitments"]["changed"] is False and e["commitments"]["before"]["essentials_satang"] == 500_000
    assert e["unspent_budget"]["before_satang"] == e["unspent_budget"]["after_satang"]
    assert e["goals"]["changed"] is False
    assert c["days_until_income"] == 17 and c["policy"]["version"] == "card-policy@0.1"
    assert [a["action"] for a in v["actions"]] == ["approve", "edit", "cancel"]
    assert v["expires_at"] and v["card"]["payload_hash"] == v["payload_hash"]


def test_card_thresholds_small_large_and_low(client):
    u = User(client).onboard()
    u.approve_plan()                                       # Food ฿4,000 unspent
    quiet = _realloc(u, 10_000).json()                     # ฿100: routine top-up
    assert _codes(quiet) == []
    large = _realloc(u, 250_000).json()                    # 62.5 % of Food's remaining → LARGE_MOVE
    assert _codes(large) == ["LARGE_MOVE"]
    low = _realloc(u, 370_000).json()                      # leaves ฿300 < 10 % of ฿4,000 → LOW + LARGE
    assert sorted(_codes(low)) == ["LARGE_MOVE", "POCKET_LOW_AFTER"]
    assert all(w["severity"] == "medium" for w in low["card"]["warnings"])


def test_card_reports_predicted_unassigned_and_review_uncertainty(client, db):
    u = User(client).onboard()
    u.approve_plan()
    t = _spend(u, 40_000, "food")
    _spend(u, 7_000, None)  # no category → unassigned
    with db.connect() as c:  # simulate a history-based guess (worker path) without a model
        c.execute("update txn set category_state='predicted', category_source='history' where id=%s", (t["id"],))
    v = _realloc(u, 10_000).json()
    food = next(x for x in v["card"]["changes"] if x["name"] == "Food")
    assert food["spent_predicted_satang"] == 40_000 and food["spent_confirmed_satang"] == 0
    unc = {x["code"]: x["params"] for x in v["card"]["uncertainty"]}
    assert unc["PREDICTED_CATEGORY_SPENDING"] == {"satang": 40_000}
    assert unc["UNASSIGNED_SPENDING"] == {"satang": 7_000}


def test_card_goal_effects_and_plan_overcommit_warning(client):
    u = User(client).onboard()
    u.approve_plan()  # pockets use all ฿10,000 money left
    r = u.req("POST", "/proposals", json={"kind": "goal_create", "payload": {
        "name": "Laptop", "target_satang": 3_000_000, "saved_satang": 0, "deadline": "2027-01-31", "contribution_satang_per_period": 200_000}})
    assert r.status_code == 201, r.text
    c = r.json()["card"]
    e = c["effects"]
    assert e["commitments"]["before"]["savings_satang"] == 0 and e["commitments"]["after"]["savings_satang"] == 200_000
    assert e["money_left"]["after_satang"] == e["money_left"]["before_satang"] - 200_000
    # 3 income dates (1 Nov, 1 Dec, 1 Jan) → ฿10,000 each needed; ฿2,000 offered
    assert e["this_goal"] == {"contribution_events_until_deadline": 3, "required_per_event_satang": 1_000_000,
                              "contribution_per_event_satang": 200_000, "contribution_covers_required": False}
    assert e["unspent_budget"]["fits"] is False
    codes = [w["code"] for w in c["warnings"]]
    assert codes[0] == "PLAN_EXCEEDS_MONEY_LEFT_AFTER" and "GOAL_CONTRIBUTION_BELOW_REQUIRED" in codes


def test_card_buffer_change_shows_goal_feasibility_before_after(client):
    u = User(client).onboard()
    # goal needing ฿5,000 per income: feasible with ฿10,000 money left, not with a ฿6,000 buffer
    assert u.req("POST", "/proposals", json={"kind": "goal_create", "payload": {
        "name": "Trip", "target_satang": 500_000, "saved_satang": 0, "deadline": "2026-11-15", "contribution_satang_per_period": 0}}).status_code == 201
    v = [p for p in u.req("GET", "/proposals?status=pending").json() if p["kind"] == "goal_create"][0]
    assert _approve(u, v).status_code == 200
    plan = u.req("POST", "/plan/suggest?buffer_satang=600000").json()
    c = plan["card"]
    assert c["effects"]["buffer"] == {"before_satang": 0, "after_satang": 600_000}
    g = c["effects"]["goals"]["goals"][0]
    assert (g["name"], g["feasible_before"], g["feasible_after"]) == ("Trip", True, False)
    assert "GOAL_BECOMES_INFEASIBLE" in _codes(plan)
    assert "SUGGESTED_BY_ASSISTANT" in _codes(plan)  # /plan/suggest is an assistant suggestion


# ---------------- persistence and binding ----------------

def test_card_is_identical_after_reload_and_hash_binds_it(client):
    u = User(client).onboard()
    u.approve_plan()
    v = _realloc(u, 50_000).json()
    again = u.req("GET", f"/proposals/{v['proposal_id']}").json()
    assert again["card"] == v["card"] and again["card_hash"] == v["card_hash"] and again["payload"] == v["payload"]
    assert again["card_hash"] == "sha256:" + sha256(canonical_json(again["card"])).hex()
    listed = [p for p in u.req("GET", "/proposals?status=pending").json() if p["proposal_id"] == v["proposal_id"]]
    assert listed and listed[0]["card"] == v["card"]
    r = _approve(u, v)
    assert r.status_code == 200
    done = u.req("GET", f"/proposals/{v['proposal_id']}").json()
    assert done["status"] == "applied" and done["actions"] == [] and done["card"] == v["card"]
    applied = {p["name"]: p["allocation_satang"] for p in _plan(u)["pockets"] if p["pocket_id"]}
    for ch in v["card"]["changes"]:
        assert applied[ch["name"]] == ch["allocation_after_satang"]  # what was shown is what was applied


def test_card_hash_mismatch_is_rejected_and_nothing_changes(client, db):
    u = User(client).onboard()
    u.approve_plan()
    v = _realloc(u, 50_000).json()
    before = _pocket(u, "Food")["allocation_satang"]
    r = _approve(u, v, card_hash="sha256:" + "0" * 64)
    assert r.status_code == 409 and r.json()["error"]["code"] == "PROPOSAL_MISMATCH"
    assert _pocket(u, "Food")["allocation_satang"] == before
    assert u.req("GET", f"/proposals/{v['proposal_id']}").json()["status"] == "pending"
    missing = u.req("POST", f"/proposals/{v['proposal_id']}/approve", idem=True, json={"payload_hash": v["payload_hash"]})
    assert missing.status_code == 400  # card_hash is required
    with db.connect() as c:
        why = c.execute("select details->>'why' w from audit_event where subject_id=%s and action='proposal_approve'",
                        (v["proposal_id"],)).fetchone()["w"]
    assert why == "card_mismatch"


def test_db_refuses_to_change_stored_card_or_reopen_final_proposal(client, db):
    u = User(client).onboard()
    u.approve_plan()
    v = _realloc(u, 50_000).json()
    with db.connect() as c:
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute("update proposal set card = card || '{\"summary\": {\"text\": \"tampered\"}}' where id=%s", (v["proposal_id"],))
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute("update proposal set payload = jsonb_set(payload, '{amount_satang}', '1') where id=%s", (v["proposal_id"],))
    assert _approve(u, v).status_code == 200
    with db.connect() as c:
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute("update proposal set status='pending' where id=%s", (v["proposal_id"],))


def test_stale_replacement_has_a_recomputed_card(client):
    u = User(client).onboard()
    u.approve_plan()
    v = _realloc(u, 100_000).json()
    _spend(u, 300_000, "food")  # data changes after the card was computed
    r = _approve(u, v)
    assert r.status_code == 409 and r.json()["error"]["code"] == "PROPOSAL_STALE"
    rep = r.json()["error"]["details"]["replacement"]
    old_food = next(x for x in v["card"]["changes"] if x["name"] == "Food")
    new_food = next(x for x in rep["card"]["changes"] if x["name"] == "Food")
    assert old_food["remaining_before_satang"] == 400_000 and new_food["remaining_before_satang"] == 100_000
    assert new_food["remaining_after_satang"] == 0 and "MOVES_ALL_REMAINING" in _codes(rep)  # now it empties Food
    assert rep["card_hash"] != v["card_hash"] and rep["payload_hash"] == v["payload_hash"]
    assert _approve(u, v).status_code == 409  # the old one stays dead
    assert _approve(u, rep).status_code == 200


# ---------------- edit ----------------

def test_edit_creates_new_proposal_and_old_approval_cannot_apply(client):
    u = User(client).onboard()
    u.approve_plan()
    old = _realloc(u, 50_000).json()
    payload = {**old["payload"], "amount_satang": 20_000}
    r = u.req("POST", f"/proposals/{old['proposal_id']}/edit", json={"payload_hash": old["payload_hash"], "payload": payload})
    assert r.status_code == 201, r.text
    new = r.json()
    assert new["proposal_id"] != old["proposal_id"] and new["edited_from"] == old["proposal_id"] and new["created_by"] == "user"
    assert new["payload_hash"] != old["payload_hash"] and new["card_hash"] != old["card_hash"]
    assert new["card"]["transfer"]["amount_satang"] == 20_000 and new["card"]["edited_from"] == old["proposal_id"]
    o = u.req("GET", f"/proposals/{old['proposal_id']}").json()
    assert o["status"] == "superseded" and o["superseded_by"] == new["proposal_id"] and o["actions"] == []
    food = _pocket(u, "Food")["allocation_satang"]
    r_old = _approve(u, old)
    assert r_old.status_code == 409 and r_old.json()["error"]["code"] == "PROPOSAL_NOT_PENDING"
    cross = u.req("POST", f"/proposals/{new['proposal_id']}/approve", idem=True,
                  json={"payload_hash": old["payload_hash"], "card_hash": old["card_hash"]})
    assert cross.status_code == 409 and cross.json()["error"]["code"] == "PROPOSAL_MISMATCH"
    assert _pocket(u, "Food")["allocation_satang"] == food  # neither attempt changed anything
    assert _approve(u, new).status_code == 200
    assert _pocket(u, "Food")["allocation_satang"] == food - 20_000
    again = u.req("POST", f"/proposals/{old['proposal_id']}/edit", json={"payload_hash": old["payload_hash"], "payload": payload})
    assert again.status_code == 409 and again.json()["error"]["details"]["superseded_by"] == new["proposal_id"]


def test_edit_is_validated_like_a_new_proposal(client):
    u = User(client).onboard()
    u.approve_plan()
    old = _realloc(u, 50_000).json()
    same = u.req("POST", f"/proposals/{old['proposal_id']}/edit", json={"payload_hash": old["payload_hash"], "payload": old["payload"]})
    assert same.status_code == 400 and same.json()["error"]["code"] == "NO_CHANGE"
    too_much = u.req("POST", f"/proposals/{old['proposal_id']}/edit", json={"payload_hash": old["payload_hash"],
                                                                           "payload": {**old["payload"], "amount_satang": 400_001}})
    assert too_much.status_code == 400
    wrong_base = u.req("POST", f"/proposals/{old['proposal_id']}/edit", json={"payload_hash": "sha256:" + "0" * 64,
                                                                             "payload": {**old["payload"], "amount_satang": 1}})
    assert wrong_base.status_code == 409
    other = User(client).onboard()
    assert other.req("POST", f"/proposals/{old['proposal_id']}/edit", json={"payload_hash": old["payload_hash"],
                                                                           "payload": {**old["payload"], "amount_satang": 1}}).status_code == 404
    assert u.req("GET", f"/proposals/{old['proposal_id']}").json()["status"] == "pending"  # failed edits leave it intact


def test_expired_proposal_is_reported_expired_on_reload(client, monkeypatch):
    u = User(client).onboard()
    u.approve_plan()
    v = _realloc(u, 50_000).json()
    monkeypatch.setenv("FINASSIST_FIXED_NOW", "2026-10-15T07:00:00+00:00")  # +60 min > 30 min TTL
    got = u.req("GET", f"/proposals/{v['proposal_id']}").json()
    assert got["status"] == "expired" and got["actions"] == [] and got["card"] == v["card"]
    assert all(p["proposal_id"] != v["proposal_id"] for p in u.req("GET", "/proposals?status=pending").json())


def test_agent_sees_code_computed_warnings_only_as_tool_result(client, db):
    u = User(client).onboard()
    u.approve_plan()
    model = ScriptedChatModel([
        ChatTurn("", [{"id": "a", "name": "propose_reallocation",
                       "input": {"from_pocket": "Food", "to_pocket": "Shopping", "amount_thb": "4000"}}], False, "scripted"),
        ChatTurn("Prepared.", [], True, "scripted"),
    ])
    with db.connect() as conn:
        out = agent.chat(conn, _owner(db, u), "move all food budget to shopping", model)
    card = next(c for c in out["cards"] if c["type"] == "proposal")
    assert {"MOVES_ALL_REMAINING", "SUGGESTED_BY_ASSISTANT"} <= set(_codes(card))
    tool_result = model.seen[-1][-1]["content"][0]["content"]
    assert "MOVES_ALL_REMAINING" in tool_result and "requires_user_approval" in tool_result
    stored = u.req("GET", f"/proposals/{card['proposal_id']}").json()
    assert stored["card"] == card["card"] and stored["status"] == "pending"
