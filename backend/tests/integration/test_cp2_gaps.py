"""Gaps listed as untested in docs/design/08 (CP2): /data/delete with pending purge, goal_update via proposals,
chat-history retention on/off/revoke (including revocation during a model call), PATCH /transactions effects and
guards, and redaction of application logs. Extraction is FAKE, chat is SCRIPTED."""

from __future__ import annotations

import io
import logging
import uuid

import pytest
from fastapi.testclient import TestClient

from finassist.api.app import create_app
from finassist.providers import ChatTurn, ScriptedChatModel
from finassist.services import agent, budget
from finassist.services.imports import LocalStorage, StorageDeleteError
from finassist.settings import Settings

from .conftest import User, drain, register

pytestmark = pytest.mark.db


class FlakyStorage(LocalStorage):
    fail = False

    def delete(self, key: str) -> None:
        if self.fail:
            raise StorageDeleteError("PermissionDenied")
        super().delete(key)


@pytest.fixture
def storage(tmp_path):
    return FlakyStorage(str(tmp_path / "uploads"))


def _owner(db, u: User):
    with db.connect() as c:
        return c.execute("select id from app_user where email=%s", (u.email,)).fetchone()["id"]


def _spend(u: User, amount: int, category: str | None = "food", *, at: str = "2026-10-15T14:00:00+07:00", payee: str | None = None):
    body = {"kind": "expense", "amount_satang": amount, "occurred_date": at[:10], "occurred_at": at,
            "payee": payee or f"shop-{uuid.uuid4().hex[:6]}"}
    if category:
        body["category"] = category
    r = u.req("POST", "/transactions", idem=True, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _patch(u: User, t: dict, **changes):
    return u.req("PATCH", f"/transactions/{t['id']}", json={"version": t["version"], "changes": changes})


def _plan(u: User) -> dict:
    return u.req("GET", "/plan").json()


def _food(u: User) -> dict:
    return next(p for p in _plan(u)["pockets"] if p["name"] == "Food")


def _approve(u: User, v: dict):
    return u.req("POST", f"/proposals/{v['proposal_id']}/approve", idem=True,
                 json={"payload_hash": v["payload_hash"], "card_hash": v["card_hash"]})


# ---------------- /data/delete ----------------

def test_data_delete_reports_pending_purge_and_resumes(client, db, storage, provider):
    u = User(client).onboard()
    for f in ("slip_003_transfer_out.png", "slip_004_transfer_out.png"):
        assert u.upload(register(provider, f)).status_code in (201, 202)
    drain(db, storage, provider)
    assert len(u.req("GET", "/transactions").json()) == 2
    storage.fail = True
    r = u.req("POST", "/data/delete", json={"scope": "imported"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["uploads_processed"] == 2 and body["records_removed"] == 2
    assert body["complete"] is False and body["images_pending_purge"] == 2 and len(body["pending_upload_ids"]) == 2
    assert u.req("GET", "/transactions").json() == [] and u.req("GET", "/uploads").json() == []  # records gone, images unreachable
    assert len([f for f in storage.root.rglob("*") if f.is_file()]) == 2  # …but the image files still exist: not reported as erased
    storage.fail = False
    r2 = u.req("POST", "/data/delete", json={"scope": "imported"}).json()  # repeat resumes the purge
    assert r2["complete"] is True and r2["images_pending_purge"] == 0 and r2["image_purge"]["done"] == 2
    assert [f for f in storage.root.rglob("*") if f.is_file()] == []
    r3 = u.req("POST", "/data/delete", json={"scope": "imported"}).json()
    assert r3 == {**r3, "uploads_processed": 0, "complete": True}
    with db.connect() as c:
        acts = [r["details"]["images_pending"] for r in c.execute(
            "select details from audit_event where owner_id=%s and action='data_delete' order by id", (_owner(db, u),)).fetchall()]
    assert acts == [2, 0, 0]


def test_data_delete_keeps_manual_entries_and_is_owner_scoped(client, db, storage, provider):
    a, b = User(client).onboard(), User(client).onboard()
    a.upload(register(provider, "slip_003_transfer_out.png"))
    b.upload(register(provider, "slip_004_transfer_out.png"))
    drain(db, storage, provider)
    manual = _spend(a, 5_000)
    assert a.req("POST", "/data/delete", json={"scope": "imported"}).json()["uploads_processed"] == 1
    assert [t["id"] for t in a.req("GET", "/transactions").json()] == [manual["id"]]
    assert len(b.req("GET", "/transactions").json()) == 1 and len(b.req("GET", "/uploads").json()) == 1
    assert a.req("POST", "/data/delete", json={"scope": "everything"}).status_code == 400


# ---------------- goal_update via proposal ----------------

def _goal(u: User, **kw) -> str:
    payload = {"name": "Laptop", "target_satang": 1_000_000, "saved_satang": 0, "deadline": "2027-03-31",
               "contribution_satang_per_period": 100_000, **kw}
    v = u.req("POST", "/proposals", json={"kind": "goal_create", "payload": payload}).json()
    r = _approve(u, v)
    assert r.status_code == 200, r.text
    return r.json()["result"]["goal_id"]


def test_goal_update_requires_approval_and_applies_once(client):
    u = User(client).onboard()
    gid = _goal(u)
    v = u.req("POST", "/proposals", json={"kind": "goal_update", "payload": {"goal_id": gid, "contribution_satang_per_period": 250_000}}).json()
    assert v["card"]["changes"] == [{"field": "contribution_satang_per_period", "before": 100_000, "after": 250_000}]
    e = v["card"]["effects"]
    assert e["commitments"]["before"]["savings_satang"] == 100_000 and e["commitments"]["after"]["savings_satang"] == 250_000
    assert e["money_left"]["after_satang"] == e["money_left"]["before_satang"] - 150_000
    g = u.req("GET", "/goals").json()[0]
    assert g["contribution_satang_per_period"] == 100_000 and g["version"] == 1  # proposal alone changed nothing
    assert _approve(u, v).status_code == 200
    g = u.req("GET", "/goals").json()[0]
    assert g["contribution_satang_per_period"] == 250_000 and g["version"] == 2
    assert _approve(u, v).status_code == 409
    assert u.req("GET", "/plan").json()["cashflow"]["discretionary_satang"] == 1_000_000 - 250_000  # reserved as savings


def test_goal_update_stale_after_concurrent_goal_change(client):
    u = User(client).onboard()
    gid = _goal(u)
    p1 = u.req("POST", "/proposals", json={"kind": "goal_update", "payload": {"goal_id": gid, "target_satang": 1_200_000}}).json()
    p2 = u.req("POST", "/proposals", json={"kind": "goal_update", "payload": {"goal_id": gid, "deadline": "2027-06-30"}}).json()
    assert _approve(u, p2).status_code == 200
    r = _approve(u, p1)
    assert r.status_code == 409 and r.json()["error"]["code"] == "PROPOSAL_STALE"
    g = u.req("GET", "/goals").json()[0]
    assert (g["target_satang"], str(g["deadline"])) == (1_000_000, "2027-06-30")  # p1 did not apply on the new version


def test_goal_update_rejects_invalid_and_foreign_goals(client, db):
    u, other = User(client).onboard(), User(client).onboard()
    gid = _goal(u)
    def prop(owner: User, **payload):
        return owner.req("POST", "/proposals", json={"kind": "goal_update", "payload": {"goal_id": gid, **payload}})
    assert prop(other, target_satang=2_000_000).status_code == 404
    assert prop(u).json()["error"]["code"] == "NO_CHANGE"
    assert prop(u, target_satang=1_000_000).json()["error"]["code"] == "NO_CHANGE"
    assert prop(u, deadline="2026-10-15").json()["error"]["fields"][0]["issue"] == "not_in_future"
    assert prop(u, target_satang=0).status_code == 400
    with db.connect() as c:
        c.execute("update goal set status='archived' where id=%s", (gid,))
    assert prop(u, target_satang=2_000_000).json()["error"]["code"] == "GOAL_NOT_ACTIVE"


# ---------------- chat history retention ----------------

def _turn(text: str) -> ScriptedChatModel:
    return ScriptedChatModel([ChatTurn(text, [], True, "scripted")])


def _chat_rows(db, owner) -> list[str]:
    with db.connect() as c:
        return [r["content"]["text"] for r in c.execute("select content from chat_message where owner_id=%s order by created_at, (role='assistant')", (owner,)).fetchall()]


def test_chat_history_off_on_and_revoked(client, db):
    u = User(client).onboard()
    o = _owner(db, u)
    with db.connect() as conn:
        agent.chat(conn, o, "first (not kept)", _turn("ok1"))
    assert _chat_rows(db, o) == []
    assert u.req("POST", "/consents", json={"scope": "chat_history_retention", "version": "v1"}).status_code == 201
    with db.connect() as conn:
        agent.chat(conn, o, "second (kept)", _turn("ok2"))
        m = _turn("ok3")
        agent.chat(conn, o, "third", m)
    assert _chat_rows(db, o) == ["second (kept)", "ok2", "third", "ok3"]
    assert [x["content"] for x in m.seen[0]][:2] == ["second (kept)", "ok2"]  # history used only while consented
    assert "first (not kept)" not in str(m.seen[0])
    assert u.req("DELETE", "/consents/chat_history_retention").status_code == 200
    assert _chat_rows(db, o) == []  # revocation deletes history
    with db.connect() as conn:
        m2 = _turn("ok4")
        agent.chat(conn, o, "after revoke", m2)
    assert _chat_rows(db, o) == [] and len(m2.seen[0]) == 1  # not stored, no old history sent


class _RevokeDuringCall(ScriptedChatModel):
    """The user revokes retention while the model is still answering."""

    def __init__(self, user: User):
        super().__init__([ChatTurn("late reply", [], True, "scripted")])
        self.user = user

    def step(self, system, messages, tools):
        assert self.user.req("DELETE", "/consents/chat_history_retention").status_code == 200
        return super().step(system, messages, tools)


def test_chat_turn_not_stored_when_consent_revoked_mid_call(client, db):
    u = User(client).onboard()
    o = _owner(db, u)
    assert u.req("POST", "/consents", json={"scope": "chat_history_retention", "version": "v1"}).status_code == 201
    with db.connect() as conn:
        agent.chat(conn, o, "kept before", _turn("ok"))
        agent.chat(conn, o, "sensitive question", _RevokeDuringCall(u))
    assert _chat_rows(db, o) == []
    with db.connect() as c:
        last = c.execute("select details from audit_event where owner_id=%s and action='chat_turn' order by id desc limit 1", (o,)).fetchone()
    assert last["details"]["history_stored"] is False
    # re-granting during a turn does not make that turn's text stored under the new grant
    class _RevokeRegrant(_RevokeDuringCall):
        def step(self, system, messages, tools):
            out = super().step(system, messages, tools)
            assert self.user.req("POST", "/consents", json={"scope": "chat_history_retention", "version": "v2"}).status_code == 201
            return out
    assert u.req("POST", "/consents", json={"scope": "chat_history_retention", "version": "v1b"}).status_code == 201
    with db.connect() as conn:
        agent.chat(conn, o, "during flip", _RevokeRegrant(u))
    assert _chat_rows(db, o) == []


# ---------------- PATCH /transactions ----------------

def test_patch_amount_updates_totals_pockets_and_staleness(client):
    u = User(client).onboard()
    u.approve_plan()
    t = _spend(u, 30_000)  # after the 13:00 balance entry → reduces money left
    plan = _plan(u)
    assert plan["cashflow"]["discretionary_satang"] == 1_000_000 - 30_000 and _food(u)["spent_confirmed_satang"] == 30_000
    v = u.req("POST", "/proposals", json={"kind": "reallocate", "payload": {"plan_id": plan["plan"]["id"], "from_pocket": u.pockets["Food"],
                                                                            "to_pocket": u.pockets["Shopping"], "amount_satang": 10_000}}).json()
    r = _patch(u, t, amount_satang=45_000)
    assert r.status_code == 200, r.text
    assert r.json()["amount_satang"] == 45_000 and r.json()["version"] == t["version"] + 1 and r.json()["amount_state"] == "confirmed"
    assert _plan(u)["cashflow"]["discretionary_satang"] == 1_000_000 - 45_000 and _food(u)["spent_confirmed_satang"] == 45_000
    spend = u.req("GET", "/spending?from=2026-10-01&to=2026-11-01").json()
    assert spend["total_satang"] == 45_000
    a = _approve(u, v)
    assert a.status_code == 409 and a.json()["error"]["code"] == "PROPOSAL_STALE"  # card numbers were computed before the edit
    assert _patch(u, t, amount_satang=1).json()["error"]["code"] == "VERSION_CONFLICT"


def test_patch_date_moves_across_balance_anchor_and_period(client):
    u = User(client).onboard()
    u.approve_plan()
    t = _spend(u, 30_000)
    r = _patch(u, t, occurred_at="2026-10-15T09:00:00+07:00")  # before the 13:00 balance entry → already in the balance (FI-8)
    assert r.status_code == 200 and r.json()["occurred_date"] == "2026-10-15"
    assert _plan(u)["cashflow"]["discretionary_satang"] == 1_000_000
    assert _food(u)["spent_confirmed_satang"] == 30_000  # still this period's spending
    t2 = r.json()
    r2 = _patch(u, t2, occurred_date="2026-10-10", occurred_at="2026-10-10T09:00:00+07:00")  # before the plan period
    assert r2.status_code == 200 and _food(u)["spent_confirmed_satang"] == 0
    t3 = r2.json()
    bad = _patch(u, t3, occurred_date="2026-10-11")  # timed record moved without its time
    assert bad.status_code == 400 and bad.json()["error"]["fields"][0]["issue"] == "inconsistent"
    mismatch = _patch(u, t3, occurred_date="2026-10-12", occurred_at="2026-10-11T09:00:00+07:00")
    assert mismatch.status_code == 400
    ok = _patch(u, t3, occurred_date="2026-10-11", occurred_at=None)  # becomes date-only
    assert ok.status_code == 200 and ok.json()["occurred_at"] is None


def test_patch_category_moves_spending_between_pockets(client):
    u = User(client).onboard()
    u.approve_plan()
    t = _spend(u, 30_000, "food")
    r = _patch(u, t, category="shopping")
    assert r.status_code == 200 and r.json()["category_code"] == "shopping" and r.json()["category_state"] == "confirmed"
    pockets = {p["name"]: p for p in _plan(u)["pockets"]}
    assert pockets["Food"]["spent_confirmed_satang"] == 0 and pockets["Shopping"]["spent_confirmed_satang"] == 30_000
    assert _patch(u, r.json(), category="no_such").json()["error"]["fields"][0]["issue"] == "unknown"


def test_patch_rejects_bad_values_without_server_errors(client):
    u = User(client).onboard()
    t = _spend(u, 30_000)
    for changes in ({"amount_satang": -5}, {"amount_satang": "lots"}, {"kind": "transfer_in"}, {"payment_status": "unknown"},
                    {"occurred_at": "2026-10-15T09:00:00"}, {"owner_id": str(uuid.uuid4())}, {"bank_ref_norm": "X"}, {},
                    {"amount_satang": None}):
        r = _patch(u, t, **changes)
        assert r.status_code == 400, (changes, r.status_code, r.text)
    assert u.req("GET", "/transactions").json()[0]["amount_satang"] == 30_000


def test_patch_keeps_bill_and_refund_links_consistent(client):
    u = User(client).onboard()
    bill = u.req("POST", "/bills", json={"biller": "Water", "amount_due_satang": 20_000, "due_date": "2026-10-20"}).json()
    pay = _spend(u, 20_000, "bills")
    assert u.req("POST", f"/bills/{bill['id']}/link-payment", json={"txn_id": pay["id"]}).status_code == 200
    r = _patch(u, pay, amount_satang=25_000)
    assert r.status_code == 409 and r.json()["error"]["code"] == "TXN_LINKED_TO_BILL"
    assert _patch(u, pay, payment_status="failed").status_code == 409
    assert _patch(u, pay, kind="income").status_code == 409
    assert _patch(u, pay, description="quarterly").status_code == 200  # harmless fields stay editable
    src = _spend(u, 50_000, "shopping")
    rf = u.req("POST", "/transactions", idem=True, json={"kind": "refund", "amount_satang": 30_000, "occurred_date": "2026-10-15",
                                                         "refund_of": src["id"]}).json()
    assert _patch(u, src, amount_satang=29_000).json()["error"]["fields"][0]["issue"] == "below_refunded"
    assert _patch(u, rf, amount_satang=50_001).json()["error"]["fields"][0]["issue"] == "refund_exceeds_source"
    assert _patch(u, rf, amount_satang=50_000).status_code == 200
    assert _patch(u, src, kind="income").json()["error"]["code"] == "TXN_LINKED"


# ---------------- application log redaction ----------------

def test_third_party_log_lines_are_pattern_redacted():
    """Second layer for messages we do not word ourselves (e.g. a library logging a Postgres error)."""
    from finassist.logsafe import RedactingFilter, redact

    rec = logging.LogRecord("psycopg", logging.WARNING, __file__, 1, "conn %s failed: %s", ("postgresql://u:secretpw@h/db",
                            'DETAIL:  Key (lower(email))=(a@b.test) already exists'), None)
    RedactingFilter().filter(rec)
    msg = rec.getMessage()
    assert "secretpw" not in msg and "a@b.test" not in msg and "[REDACTED]" in msg
    assert redact("Authorization: Bearer abcdefghijklmnopqrstuvwxyz") == "Authorization: [REDACTED]"
    assert redact("key sk-ant-api03-abcDEF_123") == "key [REDACTED_KEY]"
    assert redact("ref 2026101512345678 ok") == "ref [NUMBER] ok"
    keep = "id 550e8400-e29b-41d4-a716-446655440000 at 2026-10-15 06:00:00 amount_satang=30000"
    assert redact(keep) == keep  # ids, timestamps and small numbers stay readable


def test_unhandled_error_log_is_redacted(app_db, storage, monkeypatch):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        app = create_app(Settings(_env_file=None, model_provider="fake", database_url="postgresql://x", storage_dir=str(storage.root)),
                         db=app_db, storage=storage)  # installs redaction on existing handlers
        c = TestClient(app, raise_server_exceptions=False)
        u = User(c).onboard()
        secret_email, ref = "victim.person@example.test", "DS01812026101599887766"

        def boom(conn, owner_id):
            raise RuntimeError(f"DETAIL:  Key (lower(email))=({secret_email}) already exists; ref {ref}; "
                               f"Authorization: {u.h['Authorization']} postgresql://finassist:pw@db/x payee ร้านป้าสมาน")

        monkeypatch.setattr(budget, "get_plan", boom)
        r = c.get("/v1/plan", headers=u.h)
        assert r.status_code == 500 and r.json()["error"]["code"] == "INTERNAL"
        assert secret_email not in r.text and "RuntimeError" not in r.text  # nothing leaks to the client
        out = stream.getvalue()
        assert "unhandled request_id=" in out and "route=/v1/plan" in out and "exc=RuntimeError" in out
        assert r.json()["error"]["request_id"] in out  # still traceable
        assert "test_cp2_gaps.py" in out  # stack frames kept for debugging
        for leaked in (secret_email, ref, u.h["Authorization"][7:], ":pw@", "ร้านป้าสมาน"):
            assert leaked not in out, leaked
    finally:
        root.removeHandler(handler)
