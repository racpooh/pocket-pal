"""Regression tests for the Codex CP2 review (15 Oct 2026).

#1 [P1] changing payment status/time/deletion of ONE transfer leg made money appear from nowhere
#2 [P1] approval could interleave with an uncommitted ledger change (check → apply not exclusive)
#3 [P2] the embedded worker logged exception messages (free text such as payee names)
Two-connection tests control the timing explicitly; no model calls.
"""

from __future__ import annotations

import io
import logging
import threading
import time
import uuid
from datetime import date

import psycopg
import pytest
from fastapi.testclient import TestClient

from finassist.services import budget, core

from .conftest import User

pytestmark = pytest.mark.db


def _owner(db, u: User):
    with db.connect() as c:
        return c.execute("select id from app_user where email=%s", (u.email,)).fetchone()["id"]


# ---------------- #1 transfer legs ----------------

def _two_accounts_with_transfer(client, db) -> tuple[User, dict]:
    """Main ฿15,000 and Wallet ฿5,000 (both spending, balances at 13:00); transfer ฿2,000 Main → Wallet at 14:00."""
    u = User(client).onboard()
    o = _owner(db, u)
    gid = uuid.uuid4()
    with db.connect() as c, c.transaction():
        wallet = c.execute("insert into account(owner_id,name,kind) values (%s,'Wallet','spending') returning id", (o,)).fetchone()["id"]
        c.execute("insert into balance_observation(owner_id,account_id,amount_satang,as_of,as_of_is_date_only) values (%s,%s,500000,%s,false)",
                  (o, wallet, "2026-10-15T13:00:00+07:00"))
        legs = {}
        for kind, acct in (("transfer_out", u.account), ("transfer_in", wallet)):
            legs[kind] = c.execute(
                """insert into txn(owner_id,account_id,kind,amount_satang,occurred_at,occurred_date,payment_status,amount_state,
                   direction_state,source,transfer_group_id) values (%s,%s,%s,200000,'2026-10-15T14:00:00+07:00','2026-10-15','completed',
                   'confirmed','confirmed','manual',%s) returning id,version""", (o, acct, kind, gid)).fetchone()
    return u, {"out": legs["transfer_out"], "in": legs["transfer_in"], "wallet": str(wallet)}


def _balances(u: User) -> dict[str, int]:
    return {a["account_id"]: a["projected_satang"] for a in u.req("GET", "/plan").json()["accounts"]}


def test_r1_status_change_on_one_leg_moves_both_and_total_is_unchanged(client, db):
    u, t = _two_accounts_with_transfer(client, db)
    before = _balances(u)
    assert before == {u.account: 1_300_000, t["wallet"]: 700_000} and sum(before.values()) == 2_000_000
    r = u.req("PATCH", f"/transactions/{t['out']['id']}", json={"version": t["out"]["version"], "changes": {"payment_status": "failed"}})
    assert r.status_code == 200, r.text
    rows = {x["kind"]: x for x in u.req("GET", "/transactions").json()}
    assert rows["transfer_out"]["payment_status"] == rows["transfer_in"]["payment_status"] == "failed"
    after = _balances(u)
    assert after == {u.account: 1_500_000, t["wallet"]: 500_000}  # failed transfer: neither leg counts
    assert sum(after.values()) == sum(before.values())          # no money created or lost


def test_r1_time_change_on_one_leg_moves_both(client, db):
    u, t = _two_accounts_with_transfer(client, db)
    total = sum(_balances(u).values())
    r = u.req("PATCH", f"/transactions/{t['in']['id']}", json={"version": t["in"]["version"],
                                                                "changes": {"occurred_at": "2026-10-15T09:00:00+07:00"}})
    assert r.status_code == 200, r.text
    rows = {x["kind"]: x for x in u.req("GET", "/transactions").json()}
    assert rows["transfer_out"]["occurred_at"] == rows["transfer_in"]["occurred_at"]
    assert sum(_balances(u).values()) == total
    assert u.req("PATCH", f"/transactions/{t['out']['id']}", json={"version": rows["transfer_out"]["version"],
                                                                    "changes": {"amount_satang": 1}}).status_code == 409


def test_r1_deleting_one_leg_deletes_the_transfer(client, db):
    u, t = _two_accounts_with_transfer(client, db)
    total = sum(_balances(u).values())
    assert u.req("DELETE", f"/transactions/{t['out']['id']}").status_code == 204
    assert [x for x in u.req("GET", "/transactions").json() if x["kind"].startswith("transfer")] == []
    assert sum(_balances(u).values()) == total


def test_r1_database_rejects_a_one_leg_change_from_any_code_path(client, db):
    u, t = _two_accounts_with_transfer(client, db)
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.connect() as c, c.transaction():
            c.execute("update txn set payment_status='failed' where id=%s", (t["out"]["id"],))
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.connect() as c, c.transaction():
            c.execute("update txn set deleted_at=now() where id=%s", (t["in"]["id"],))
    with db.connect() as c, c.transaction():  # both legs together is fine
        c.execute("update txn set payment_status='pending' where id = any(%s)", ([t["out"]["id"], t["in"]["id"]],))


def _insert_leg(c, o, account, kind, gid):
    return c.execute(
        """insert into txn(owner_id,account_id,kind,amount_satang,occurred_at,occurred_date,payment_status,amount_state,
           direction_state,source,transfer_group_id) values (%s,%s,%s,50000,'2026-10-15T15:00:00+07:00','2026-10-15','completed',
           'confirmed','confirmed','manual',%s) returning id""", (o, account, kind, gid)).fetchone()["id"]


def test_r1b_hard_delete_of_one_leg_is_rejected_but_both_is_allowed(client, db):
    """Codex CP2 re-review: 0006 only caught a lone leg next to a soft-deleted partner, not a SQL DELETE."""
    u, t = _two_accounts_with_transfer(client, db)
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.connect() as c, c.transaction():
            c.execute("delete from txn where id=%s", (t["out"]["id"],))
    assert len([x for x in u.req("GET", "/transactions").json() if x["kind"].startswith("transfer")]) == 2  # rolled back
    with db.connect() as c, c.transaction():
        c.execute("delete from txn where id = any(%s)", ([t["out"]["id"], t["in"]["id"]],))
    assert [x for x in u.req("GET", "/transactions").json() if x["kind"].startswith("transfer")] == []


def test_r1b_groups_must_be_pairs_and_external_single_leg_has_no_group(client, db):
    u, t = _two_accounts_with_transfer(client, db)
    o = _owner(db, u)
    with db.connect() as c, c.transaction():  # transfer to an external/untracked account: one leg, no group id → allowed
        c.execute("""insert into txn(owner_id,account_id,kind,amount_satang,occurred_date,payment_status,amount_state,direction_state,source)
                     values (%s,%s,'transfer_out',70000,'2026-10-15','completed','confirmed','confirmed','manual')""", (o, u.account))
    with pytest.raises(psycopg.errors.CheckViolation):  # a lone leg WITH a group id is not a transfer between own accounts
        with db.connect() as c, c.transaction():
            _insert_leg(c, o, u.account, "transfer_out", uuid.uuid4())
    with db.connect() as c, c.transaction():  # a complete pair inserted in one transaction → allowed
        g = uuid.uuid4()
        _insert_leg(c, o, u.account, "transfer_out", g)
        _insert_leg(c, o, t["wallet"], "transfer_in", g)
    with pytest.raises(psycopg.errors.CheckViolation):  # two outs are not a transfer
        with db.connect() as c, c.transaction():
            g = uuid.uuid4()
            _insert_leg(c, o, u.account, "transfer_out", g)
            _insert_leg(c, o, t["wallet"], "transfer_out", g)


def test_r1b_moving_legs_between_groups_checks_old_and_new_group(client, db):
    u, t = _two_accounts_with_transfer(client, db)
    with pytest.raises(psycopg.errors.CheckViolation):  # old group left with one leg, new group with one leg
        with db.connect() as c, c.transaction():
            c.execute("update txn set transfer_group_id=%s where id=%s", (uuid.uuid4(), t["in"]["id"]))
    with pytest.raises(psycopg.errors.CheckViolation):  # detaching one leg: only the OLD group shows the problem
        with db.connect() as c, c.transaction():
            c.execute("update txn set transfer_group_id=null where id=%s", (t["in"]["id"],))
    with db.connect() as c, c.transaction():  # moving both legs together keeps both groups valid
        c.execute("update txn set transfer_group_id=%s where id = any(%s)", (uuid.uuid4(), [t["out"]["id"], t["in"]["id"]]))


# ---------------- #2 approval vs concurrent ledger change ----------------

def _plan_and_proposal(u: User) -> dict:
    u.approve_plan()
    plan = u.req("GET", "/plan").json()["plan"]
    r = u.req("POST", "/proposals", json={"kind": "reallocate", "payload": {
        "plan_id": plan["id"], "from_pocket": u.pockets["Food"], "to_pocket": u.pockets["Shopping"], "amount_satang": 100_000}})
    assert r.status_code == 201, r.text
    return r.json()


def _approve_in_thread(app, u: User, v: dict, out: list) -> threading.Thread:
    def go():
        with TestClient(app) as c:
            r = c.post(f"/v1/proposals/{v['proposal_id']}/approve", json={"payload_hash": v["payload_hash"], "card_hash": v["card_hash"]},
                       headers={**u.h, "Idempotency-Key": str(uuid.uuid4())})
            out.append(r)
    th = threading.Thread(target=go)
    th.start()
    return th


def _food(u: User) -> int:
    return next(p["allocation_satang"] for p in u.req("GET", "/plan").json()["pockets"] if p["name"] == "Food")


@pytest.mark.parametrize("writer", ["manual_expense", "bill"])
def test_r2_uncommitted_ledger_change_blocks_approval_then_makes_it_stale(client, app, db, writer):
    """Writer has changed the ledger but not committed → approval must wait, then see the change (stale)."""
    u = User(client).onboard()
    v = _plan_and_proposal(u)
    o = _owner(db, u)
    food = _food(u)
    out: list = []
    with db.connect() as w:
        tx = w.transaction()
        tx.__enter__()
        if writer == "manual_expense":
            core.create_manual_txn(w, o, {"kind": "expense", "amount_satang": 300_000, "occurred_date": date(2026, 10, 15),
                                          "occurred_at": None, "payee": "late", "category": "food", "confirm_distinct": True})
        else:
            core.create_bill(w, o, {"biller": "Late bill", "amount_due_satang": 300_000, "due_date": "2026-10-20"})
        th = _approve_in_thread(app, u, v, out)
        time.sleep(1.0)
        assert th.is_alive(), "approval did not wait for the uncommitted ledger change"
        tx.__exit__(None, None, None)  # commit
    th.join(10)
    r = out[0]
    assert r.status_code == 409 and r.json()["error"]["code"] == "PROPOSAL_STALE", r.text
    assert _food(u) == food  # nothing applied on the old card


def test_r2_ledger_change_waits_for_an_approval_in_progress(client, app, db, monkeypatch):
    """Approval is between its checks and _apply → a writer cannot commit until the approval has committed."""
    u = User(client).onboard()
    v = _plan_and_proposal(u)
    o = _owner(db, u)
    food = _food(u)
    in_apply, release = threading.Event(), threading.Event()
    real_apply = budget._apply

    def slow_apply(conn, owner_id, kind, p):
        in_apply.set()
        assert release.wait(10)
        return real_apply(conn, owner_id, kind, p)

    monkeypatch.setattr(budget, "_apply", slow_apply)
    out: list = []
    th = _approve_in_thread(app, u, v, out)
    assert in_apply.wait(10)
    done = threading.Event()

    def writer():
        with db.connect() as w, w.transaction():
            core.create_manual_txn(w, o, {"kind": "expense", "amount_satang": 300_000, "occurred_date": date(2026, 10, 15),
                                          "occurred_at": None, "payee": "late", "category": "food", "confirm_distinct": True})
        done.set()

    wt = threading.Thread(target=writer)
    wt.start()
    time.sleep(1.0)
    assert not done.is_set(), "ledger change committed while an approval was between its checks and apply"
    release.set()
    th.join(10)
    wt.join(10)
    assert out[0].status_code == 200, out[0].text
    assert done.is_set() and _food(u) == food - 100_000
    with db.connect() as c:
        wm = c.execute("select value from owner_watermark where owner_id=%s", (o,)).fetchone()["value"]
        applied = c.execute("select base_data_watermark from proposal where id=%s", (v["proposal_id"],)).fetchone()["base_data_watermark"]
    assert wm == applied + 2  # approval bump, then the writer's bump: serial order approve → expense


# ---------------- #3 worker logs ----------------

_SECRET = "payee ร้านป้าสมาน memo ส่งเงินค่าห้อง victim@example.test ref DS01812026101599887766"


class _BoomDB:
    """Raises with data in the message, as a DB/driver error carrying row values would. (Stack frames show source
    lines, so the data must not be a literal on the raising line — in production it never is.)"""

    def connect(self):
        raise RuntimeError(_SECRET)


def test_r3_worker_step_logs_type_and_frames_but_not_the_message():
    from finassist.worker import run_step

    stream = io.StringIO()
    h = logging.StreamHandler(stream)
    lg = logging.getLogger("finassist.worker")
    lg.addHandler(h)
    old = lg.level
    lg.setLevel(logging.INFO)
    try:
        assert run_step(_BoomDB(), None, None) is None  # the loop survives
    finally:
        lg.removeHandler(h)
        lg.setLevel(old)
    out = stream.getvalue()
    assert "worker_step_error" in out and "exc=RuntimeError" in out and "test_cp2_review_fixes.py" in out
    for leaked in ("ร้านป้าสมาน", "ส่งเงินค่าห้อง", "victim@example.test", "DS01812026101599887766"):
        assert leaked not in out, leaked


def test_r3_embedded_worker_uses_the_safe_step():
    import inspect

    from finassist.api import app as app_mod

    src = inspect.getsource(app_mod._start_embedded_worker)
    assert "run_step(" in src and "exc_info" not in src
