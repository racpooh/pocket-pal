"""DB-level invariants in db/migrations/0001_core.sql.

Requires TEST_DATABASE_URL pointing at a DISPOSABLE database whose name ends with
'_test'. The public schema is dropped and recreated. Skipped if unset.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg import errors  # noqa: E402

pytestmark = pytest.mark.db

URL = os.environ.get("TEST_DATABASE_URL")
MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"


@pytest.fixture(scope="module")
def conn():
    if not URL:
        pytest.skip("TEST_DATABASE_URL not set")
    c = psycopg.connect(URL, autocommit=True)
    dbname = c.execute("select current_database()").fetchone()[0]
    if not dbname.endswith("_test"):
        c.close()
        pytest.fail(f"refusing to reset non-test database {dbname!r}")
    c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    for f in sorted(MIGRATIONS.glob("*.sql")):
        c.execute(f.read_text(encoding="utf-8"))
    yield c
    c.close()


def _user(c) -> uuid.UUID:
    uid = uuid.uuid4()
    c.execute("insert into app_user(id,email,password_hash) values (%s,%s,'x')", (uid, f"{uid}@example.test"))
    return uid


def _account(c, owner) -> uuid.UUID:
    aid = uuid.uuid4()
    c.execute("insert into account(id,owner_id,name,kind) values (%s,%s,'main','spending')", (aid, owner))
    return aid


def _txn(c, owner, account, *, amount=1000, ref=None, kind="expense") -> uuid.UUID:
    tid = uuid.uuid4()
    c.execute(
        """insert into txn(id,owner_id,account_id,kind,amount_satang,occurred_date,payment_status,
                           amount_state,direction_state,source,bank_ref_norm)
           values (%s,%s,%s,%s,%s,'2026-10-15','completed','confirmed','confirmed','manual',%s)""",
        (tid, owner, account, kind, amount, ref),
    )
    return tid


def test_amount_must_be_positive(conn):
    u = _user(conn)
    a = _account(conn, u)
    for bad in (0, -100):
        with pytest.raises(errors.CheckViolation):
            _txn(conn, u, a, amount=bad)


def test_bank_ref_unique_per_owner_only(conn):
    u1, u2 = _user(conn), _user(conn)
    a1, a2 = _account(conn, u1), _account(conn, u2)
    _txn(conn, u1, a1, ref="KB-REF-001")
    with pytest.raises(errors.UniqueViolation):
        _txn(conn, u1, a1, ref="KB-REF-001")
    _txn(conn, u2, a2, ref="KB-REF-001")  # different owner: allowed


def test_same_amount_same_day_without_ref_is_allowed(conn):
    # FI-28: two 10-baht waters on the same day are two transactions
    u = _user(conn)
    a = _account(conn, u)
    _txn(conn, u, a, amount=1000)
    _txn(conn, u, a, amount=1000)
    n = conn.execute("select count(*) from txn where owner_id=%s", (u,)).fetchone()[0]
    assert n == 2


def test_cannot_reference_other_owners_account(conn):
    u1, u2 = _user(conn), _user(conn)
    a1 = _account(conn, u1)
    with pytest.raises(errors.ForeignKeyViolation):
        _txn(conn, u2, a1)


def test_bill_paid_once_and_payment_settles_one_bill(conn):
    u = _user(conn)
    a = _account(conn, u)
    t1, t2 = _txn(conn, u, a, amount=50000), _txn(conn, u, a, amount=50000)
    b1, b2 = uuid.uuid4(), uuid.uuid4()
    for b in (b1, b2):
        conn.execute(
            "insert into bill(id,owner_id,biller,amount_due_satang,due_date,status) values (%s,%s,'MEA',50000,'2026-10-25','unpaid')",
            (b, u),
        )
    conn.execute("insert into bill_payment_link(owner_id,bill_id,txn_id) values (%s,%s,%s)", (u, b1, t1))
    with pytest.raises(errors.UniqueViolation):
        conn.execute("insert into bill_payment_link(owner_id,bill_id,txn_id) values (%s,%s,%s)", (u, b1, t2))
    with pytest.raises(errors.UniqueViolation):
        conn.execute("insert into bill_payment_link(owner_id,bill_id,txn_id) values (%s,%s,%s)", (u, b2, t1))


def test_bill_link_cannot_cross_owners(conn):
    u1, u2 = _user(conn), _user(conn)
    a2 = _account(conn, u2)
    t2 = _txn(conn, u2, a2)
    b1 = uuid.uuid4()
    conn.execute(
        "insert into bill(id,owner_id,biller,amount_due_satang,due_date,status) values (%s,%s,'True',1000,'2026-10-25','unpaid')",
        (b1, u1),
    )
    with pytest.raises(errors.ForeignKeyViolation):
        conn.execute("insert into bill_payment_link(owner_id,bill_id,txn_id) values (%s,%s,%s)", (u1, b1, t2))


def test_one_active_consent_per_scope(conn):
    u = _user(conn)
    conn.execute("insert into consent_grant(owner_id,scope,version) values (%s,'auto_import','v1')", (u,))
    with pytest.raises(errors.UniqueViolation):
        conn.execute("insert into consent_grant(owner_id,scope,version) values (%s,'auto_import','v1')", (u,))
    conn.execute("update consent_grant set revoked_at=now() where owner_id=%s and scope='auto_import'", (u,))
    conn.execute("insert into consent_grant(owner_id,scope,version) values (%s,'auto_import','v2')", (u,))


def test_category_state_consistency(conn):
    u = _user(conn)
    a = _account(conn, u)
    base = """insert into txn(owner_id,account_id,kind,amount_satang,occurred_date,payment_status,amount_state,
               direction_state,source,category_code,category_state,category_source)
               values (%s,%s,'expense',1000,'2026-10-15','completed','confirmed','confirmed','manual',%s,%s,%s)"""
    with pytest.raises(errors.CheckViolation):  # predicted without a category
        conn.execute(base, (u, a, None, "predicted", "history"))
    with pytest.raises(errors.CheckViolation):  # confirmed must come from the user
        conn.execute(base, (u, a, "food", "confirmed", "history"))
    conn.execute(base, (u, a, "food", "predicted", "history"))
    conn.execute(base, (u, a, "food", "confirmed", "user"))
    conn.execute(base, (u, a, None, "unclassified", None))


def test_upload_sha_unique_per_owner(conn):
    u = _user(conn)
    g = uuid.uuid4()
    conn.execute("insert into consent_grant(id,owner_id,scope,version) values (%s,%s,'photo_processing','v1')", (g, u))
    sha = hashlib.sha256(b"synthetic image bytes").digest()
    ins = "insert into upload(owner_id,consent_grant_id,sha256,mime,bytes,status) values (%s,%s,%s,'image/png',10,%s)"
    conn.execute(ins, (u, g, sha, "received"))
    with pytest.raises(errors.UniqueViolation):
        conn.execute(ins, (u, g, sha, "received"))
    conn.execute("update upload set status='deleted' where owner_id=%s", (u,))
    conn.execute(ins, (u, g, sha, "received"))  # re-upload after deletion is allowed


def test_allocation_cannot_be_negative(conn):
    u = _user(conn)
    p, plan = uuid.uuid4(), uuid.uuid4()
    conn.execute("insert into pocket(id,owner_id,name) values (%s,%s,'Food')", (p, u))
    conn.execute("insert into budget_plan(id,owner_id,period_start,period_end) values (%s,%s,'2026-10-01','2026-11-01')", (plan, u))
    with pytest.raises(errors.CheckViolation):
        conn.execute("insert into pocket_allocation(owner_id,plan_id,pocket_id,allocation_satang) values (%s,%s,%s,-1)", (u, plan, p))


def test_transfer_group_only_on_transfers(conn):
    u = _user(conn)
    a = _account(conn, u)
    with pytest.raises(errors.CheckViolation):
        conn.execute(
            """insert into txn(owner_id,account_id,kind,amount_satang,occurred_date,payment_status,amount_state,
               direction_state,source,transfer_group_id) values (%s,%s,'expense',1,'2026-10-15','completed',
               'confirmed','confirmed','manual',gen_random_uuid())""", (u, a))
