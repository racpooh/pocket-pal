"""Follow-up turns (polish item 5) with a SCRIPTED chat model: proposal status is read fresh from the server after
approval/cancel, spending is refreshed after new records, and history is context only. Not a real-model evaluation."""

from __future__ import annotations

import json
import uuid

import pytest

from finassist.providers import ChatTurn, ScriptedChatModel
from finassist.services import agent

from .conftest import User

pytestmark = pytest.mark.db


def _consent(u: User):
    assert u.req("POST", "/consents", json={"scope": "chat_history_retention", "version": "1"}).status_code == 201


def _tool(name: str, args: dict | None = None) -> ChatTurn:
    return ChatTurn("", [{"id": f"t{uuid.uuid4().hex[:6]}", "name": name, "input": args or {}}], False, "scripted")


def _done(text: str) -> ChatTurn:
    return ChatTurn(text, [], True, "scripted")


def _last_tool_result(model: ScriptedChatModel) -> dict:
    return json.loads(model.seen[-1][-1]["content"])


def _send(u: User, text: str) -> dict:
    r = u.req("POST", "/chat/messages", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()


def test_status_after_approval_is_read_from_server_not_from_history(client, app):
    u = User(client).onboard()
    u.approve_plan()
    _consent(u)
    model = ScriptedChatModel([
        _tool("propose_reallocation", {"from_pocket": "Food", "to_pocket": "Shopping", "amount_thb": "500"}), _done("Prepared; approve it in the app."),
        _tool("list_proposals"), _done("It is pending."),
        _tool("list_proposals"), _done("It was applied."),
    ])
    app.state.chat_model = model
    card = next(c for c in _send(u, "move 500 from food to shopping")["cards"] if c["type"] == "proposal")
    _send(u, "did it go through?")
    before = _last_tool_result(model)["proposals"][0]
    assert before["proposal_id"] == card["proposal_id"] and before["status"] == "pending"
    r = u.req("POST", f"/proposals/{card['proposal_id']}/approve", idem=True, json={"payload_hash": card["payload_hash"], "card_hash": card["card_hash"]})
    assert r.status_code == 200, r.text
    _send(u, "and now?")
    after = _last_tool_result(model)
    assert after["proposals"][0]["status"] == "applied" and after["proposals"][0]["decided_at"]
    # History reaches the model only as earlier text ("It is pending." is stale context); the fresh status comes from the tool.
    assert "It is pending." in [m["content"] for m in model.seen[-2] if isinstance(m["content"], str)]
    raw = json.dumps(after)
    assert "payload_hash" not in raw and "card_hash" not in raw and "actions" not in raw  # no approval material for the model
    assert agent.TOOL_TIERS["list_proposals"] == "T0"


def test_cancelled_proposal_is_reported_cancelled(client, app):
    u = User(client).onboard()
    u.approve_plan()
    model = ScriptedChatModel([
        _tool("propose_reallocation", {"from_pocket": "Food", "to_pocket": "Shopping", "amount_thb": "200"}), _done("Prepared."),
        _tool("list_proposals"), _done("Cancelled."),
    ])
    app.state.chat_model = model
    card = next(c for c in _send(u, "move 200")["cards"] if c["type"] == "proposal")
    assert u.req("POST", f"/proposals/{card['proposal_id']}/cancel").status_code == 200
    _send(u, "status?")
    assert _last_tool_result(model)["proposals"][0]["status"] == "cancelled"


def test_follow_up_after_new_spending_gets_fresh_totals(client, app):
    u = User(client).onboard()
    _consent(u)
    rng = {"start": "2026-10-01", "end_exclusive": "2026-10-16"}
    model = ScriptedChatModel([_tool("get_spending", rng), _done("You spent ฿300.00 so far."),
                               _tool("get_spending", rng), _done("Updated.")])
    app.state.chat_model = model
    for amt in (20_000, 10_000):
        assert u.req("POST", "/transactions", idem=True, json={"kind": "expense", "amount_satang": amt, "occurred_date": "2026-10-14",
                                                              "category": "food", "payee": f"p-{uuid.uuid4().hex[:6]}"}).status_code == 201
    _send(u, "how much this month?")
    assert _last_tool_result(model)["total_satang"] == 30_000
    assert u.req("POST", "/transactions", idem=True, json={"kind": "expense", "amount_satang": 5_000, "occurred_date": "2026-10-15",
                                                          "category": "shopping", "payee": "p-new"}).status_code == 201
    _send(u, "and now?")
    fresh = _last_tool_result(model)
    assert fresh["total_satang"] == 35_000 and fresh["display"]["total"] == "350.00"
    assert [r["category"] for r in fresh["ranked_categories"]] == ["food", "shopping"]


def test_system_rules_cover_answer_shape_and_fact_kinds():
    for phrase in ("Answer shape", "at most three short supporting facts", "what-if simulation that records nothing",
                   "Call list_proposals before saying what its status is", "do not describe monthly patterns",
                   "cannot verify bank settlement", "without calling tools"):
        assert phrase in agent.SYSTEM


@pytest.mark.parametrize("turns,expected", [
    ([ChatTurn("", [], True, "scripted", "max_tokens")], agent.TRUNCATED_NOTE),
    ([ChatTurn("ยอดเดือนนี้คือ", [], True, "scripted", "max_tokens")], "ยอดเดือนนี้คือ\n\n" + agent.TRUNCATED_NOTE),
    ([_tool("get_overview"), ChatTurn("", [], True, "scripted", "end_turn")], agent.EMPTY_REPLY),
])
def test_cut_off_or_empty_model_answers_are_never_shown_as_blank(client, app, turns, expected):
    # Live eval 20261018T122238Z: a Thai answer hit max_tokens and the user saw an empty reply.
    u = User(client).onboard()
    app.state.chat_model = ScriptedChatModel(list(turns))
    assert _send(u, "เดือนนี้ใช้เงินหมวดไหนมากที่สุด")["reply"] == expected


def test_language_rule_defaults_to_english():
    assert "LATEST message" in agent.SYSTEM and "English is the default" in agent.SYSTEM


@pytest.mark.parametrize("text,lang", [("Did my budget change go through?", "English"), ("ผ่านไหม ฿300", "Thai"), ("฿300 ok?", "English"),
                                       ("¿Cuánto gasté?", "English")])
def test_server_states_reply_language_of_latest_message(client, app, text, lang):
    u = User(client).onboard()
    model = ScriptedChatModel([_done("ok")])
    app.state.chat_model = model
    _send(u, text)
    ctx = json.loads(model.systems[0].split("not from the user):\n", 1)[1])
    assert ctx["reply_language"] == lang
