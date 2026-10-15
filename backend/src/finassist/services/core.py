"""Auth, profile, accounts, balance, transactions, bills, consent. All SQL is owner-scoped."""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

import psycopg
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, ValidationError

from finassist.api.errors import ApiError
from finassist.domain.classify import is_intermediary, normalize_payee
from finassist.domain.dedup import Candidate, decide, normalize_ref
from finassist.domain.periods import end_of_local_day, local_date
from finassist.infra import audit, bump_watermark, hash_password, lock_owner_ledger, new_token, set_owner, sha256, verify_password

SESSION_TTL = timedelta(days=7)
CONSENT_SCOPES = ("photo_processing", "auto_import", "chat_history_retention")


def now_utc() -> datetime:
    fixed = os.environ.get("FINASSIST_FIXED_NOW")  # deterministic demos/tests only
    return datetime.fromisoformat(fixed) if fixed else datetime.now(timezone.utc)


def today_for(tz: str) -> date:
    return local_date(now_utc(), tz)


def user_tz(conn, owner_id) -> str:
    return conn.execute("select timezone from app_user where id=%s", (owner_id,)).fetchone()["timezone"]


def _nf() -> ApiError:
    return ApiError(404, "NOT_FOUND", "Not found.")


# ---------------- auth ----------------

def signup(conn, email: str, password: str) -> dict:
    if len(password) < 10:
        raise ApiError(400, "VALIDATION_FAILED", "Password must be at least 10 characters.", fields=[{"path": "password", "issue": "too_short"}])
    with conn.transaction():
        exists = conn.execute("select 1 from app_user where lower(email)=lower(%s) and deleted_at is null", (email,)).fetchone()
        if exists:
            # Same response shape as success would leak existence; prototype returns a generic conflict.
            raise ApiError(409, "SIGNUP_FAILED", "Could not create the account.")
        uid = conn.execute("insert into app_user(email,password_hash) values (%s,%s) returning id",
                           (email, hash_password(password))).fetchone()["id"]
        set_owner(conn, uid)
        conn.execute("insert into account(owner_id,name,kind) values (%s,'Main','spending')", (uid,))
        audit(conn, uid, "user", "signup", "user", uid)
    return {"user_id": str(uid)}


def login(conn, email: str, password: str) -> dict:
    row = conn.execute("select id,password_hash from app_user where lower(email)=lower(%s) and deleted_at is null", (email,)).fetchone()
    if not row or not verify_password(row["password_hash"], password):
        raise ApiError(401, "UNAUTHENTICATED", "Email or password is incorrect.")
    token = new_token()
    set_owner(conn, row["id"])
    with conn.transaction():
        conn.execute("insert into user_session(token_sha256,owner_id,expires_at) values (%s,%s,%s)",
                     (sha256(token), row["id"], now_utc() + SESSION_TTL))
        audit(conn, row["id"], "user", "login", "user", row["id"])
    return {"token": token, "expires_in_s": int(SESSION_TTL.total_seconds())}


def owner_from_token(conn, token: str | None):
    if not token:
        raise ApiError(401, "UNAUTHENTICATED", "Sign in required.")
    row = conn.execute(
        """select owner_id from user_session where token_sha256=%s and revoked_at is null and expires_at > %s""",
        (sha256(token), now_utc()),
    ).fetchone()
    if not row:
        raise ApiError(401, "SESSION_EXPIRED", "Session expired or invalid.")
    set_owner(conn, row["owner_id"])
    return row["owner_id"]


def logout(conn, token: str) -> None:
    with conn.transaction():
        conn.execute("update user_session set revoked_at=%s where token_sha256=%s", (now_utc(), sha256(token)))


# ---------------- profile & essentials ----------------

def put_profile(conn, owner_id, p: dict) -> dict:
    with conn.transaction():
        conn.execute("update app_user set timezone=%s where id=%s", (p.get("timezone") or "Asia/Bangkok", owner_id))
        conn.execute("delete from income_schedule where owner_id=%s", (owner_id,))
        conn.execute("""insert into income_schedule(owner_id,amount_satang,frequency,next_income_date) values (%s,%s,%s,%s)""",
                     (owner_id, p["income_satang"], p["income_frequency"], p["next_income_date"]))
        conn.execute("delete from essential_expense where owner_id=%s and id not in (select essential_expense_id from bill where owner_id=%s and essential_expense_id is not null)", (owner_id, owner_id))
        for e in p.get("essentials", []):
            conn.execute("""insert into essential_expense(owner_id,name,amount_satang,frequency,due_day) values (%s,%s,%s,'monthly',%s)""",
                         (owner_id, e["name"], e["amount_satang"], e["due_day"]))
        bump_watermark(conn, owner_id)
        audit(conn, owner_id, "user", "profile_update", "user", owner_id)
    return get_profile(conn, owner_id)


def get_profile(conn, owner_id) -> dict:
    inc = conn.execute("select amount_satang,frequency,next_income_date from income_schedule where owner_id=%s", (owner_id,)).fetchone()
    ess = conn.execute("select id,name,amount_satang,due_day from essential_expense where owner_id=%s order by name", (owner_id,)).fetchall()
    tz = user_tz(conn, owner_id)
    return {"timezone": tz, "income": inc, "essentials": ess}


def main_account(conn, owner_id):
    row = conn.execute("select id from account where owner_id=%s and kind='spending' order by name limit 1", (owner_id,)).fetchone()
    if not row:
        raise _nf()
    return row["id"]


def list_accounts(conn, owner_id) -> list[dict]:
    return conn.execute("select id,name,kind,tracked from account where owner_id=%s order by name", (owner_id,)).fetchall()


def add_balance_observation(conn, owner_id, account_id, amount_satang: int, as_of: datetime | None, as_of_date: date | None) -> dict:
    tz = user_tz(conn, owner_id)
    if as_of is None and as_of_date is None:
        as_of = now_utc()
    date_only = as_of is None
    ts = end_of_local_day(as_of_date, tz) if date_only else as_of
    if ts.tzinfo is None:
        raise ApiError(400, "VALIDATION_FAILED", "as_of must include a timezone offset.")
    with conn.transaction():
        if not conn.execute("select 1 from account where owner_id=%s and id=%s", (owner_id, account_id)).fetchone():
            raise _nf()
        row = conn.execute(
            """insert into balance_observation(owner_id,account_id,amount_satang,as_of,as_of_is_date_only)
               values (%s,%s,%s,%s,%s) returning id,amount_satang,as_of,as_of_is_date_only""",
            (owner_id, account_id, amount_satang, ts, date_only)).fetchone()
        bump_watermark(conn, owner_id)
        audit(conn, owner_id, "user", "balance_observation", "account", account_id)
    return row


# ---------------- transactions ----------------

TXN_COLS = """id,account_id,kind,amount_satang,occurred_at,occurred_date,payment_status,amount_state,direction_state,
payee_display,payee_key,bank_ref_norm,category_code,category_state,category_source,source,upload_id,transfer_group_id,
refund_of,description,version,created_at"""


def list_txns(conn, owner_id, start: date | None = None, end: date | None = None, category: str | None = None,
              state: str | None = None, limit: int = 200) -> list[dict]:
    q = f"select {TXN_COLS} from txn where owner_id=%s and deleted_at is null"
    args: list = [owner_id]
    if start:
        q += " and occurred_date >= %s"; args.append(start)
    if end:
        q += " and occurred_date < %s"; args.append(end)
    if category:
        q += " and category_code = %s"; args.append(category)
    if state:
        q += " and category_state = %s"; args.append(state)
    q += " order by occurred_date desc, created_at desc limit %s"; args.append(min(limit, 500))
    return conn.execute(q, args).fetchall()


def get_txn(conn, owner_id, txn_id) -> dict:
    row = conn.execute(f"select {TXN_COLS} from txn where owner_id=%s and id=%s and deleted_at is null", (owner_id, txn_id)).fetchone()
    if not row:
        raise _nf()
    return row


def _candidates(conn, owner_id, occurred_date: date, amount: int) -> list[Candidate]:
    rows = conn.execute(
        """select t.id, t.amount_satang, t.occurred_at, t.occurred_date, t.payee_key, t.bank_ref_norm, t.source
           from txn t where t.owner_id=%s and t.deleted_at is null and t.kind in ('expense','income')
           and t.occurred_date between %s and %s""",
        (owner_id, occurred_date - timedelta(days=1), occurred_date + timedelta(days=1))).fetchall()
    return [Candidate(str(r["id"]), "manual" if r["source"] == "manual" else "transfer_out", r["amount_satang"], r["occurred_at"],
                      r["occurred_date"].isoformat(), r["payee_key"], r["bank_ref_norm"]) for r in rows]


def create_manual_txn(conn, owner_id, body: dict) -> tuple[int, dict]:
    """R3.1/R3.3. Runs inside the caller's transaction (idempotency wrapper)."""
    lock_owner_ledger(conn, owner_id)
    account_id = body.get("account_id") or main_account(conn, owner_id)
    if not conn.execute("select 1 from account where owner_id=%s and id=%s", (owner_id, account_id)).fetchone():
        raise _nf()
    payee_key = normalize_payee(body.get("payee"))
    if body["kind"] in ("expense", "income") and not body.get("confirm_distinct"):
        cand = Candidate("new", "manual", body["amount_satang"], body.get("occurred_at"), body["occurred_date"].isoformat(), payee_key, None)
        d = decide(cand, _candidates(conn, owner_id, body["occurred_date"], body["amount_satang"]))
        if d.action != "new":
            return 409, {"error": {"code": "POSSIBLE_DUPLICATE", "message": "This looks like a record you already have.",
                                   "fields": [], "retryable": False, "request_id": None,
                                   "details": {"candidates": [d.match_id], "reason": d.reason}}}
    if body.get("refund_of"):
        src = conn.execute("select amount_satang,kind from txn where owner_id=%s and id=%s and deleted_at is null", (owner_id, body["refund_of"])).fetchone()
        if not src or src["kind"] != "expense":
            raise _nf()
        refunded = conn.execute("select coalesce(sum(amount_satang),0) s from txn where owner_id=%s and refund_of=%s and deleted_at is null", (owner_id, body["refund_of"])).fetchone()["s"]
        if refunded + body["amount_satang"] > src["amount_satang"]:
            raise ApiError(400, "VALIDATION_FAILED", "Refunds would exceed the original amount.", fields=[{"path": "amount_satang", "issue": "refund_exceeds_source"}])
    cat = body.get("category")
    row = conn.execute(
        f"""insert into txn(owner_id,account_id,kind,amount_satang,occurred_at,occurred_date,payment_status,amount_state,
            direction_state,payee_display,payee_key,category_code,category_state,category_source,source,refund_of,description,transfer_group_id)
            values (%s,%s,%s,%s,%s,%s,'completed','confirmed','confirmed',%s,%s,%s,%s,%s,'manual',%s,%s,%s) returning {TXN_COLS}""",
        (owner_id, account_id, body["kind"], body["amount_satang"], body.get("occurred_at"), body["occurred_date"],
         body.get("payee"), payee_key, cat, "confirmed" if cat else "unclassified", "user" if cat else None,
         body.get("refund_of"), body.get("description"), body.get("transfer_group_id"))).fetchone()
    bump_watermark(conn, owner_id)
    audit(conn, owner_id, "user", "txn_create", "txn", row["id"], details={"source": "manual", "kind": body["kind"]})
    return 201, row


class _TxnChangesModel(BaseModel):
    model_config = {"extra": "forbid"}
    amount_satang: int | None = Field(default=None, gt=0, le=10**12)
    occurred_date: date | None = None
    occurred_at: datetime | None = None
    kind: Literal["expense", "income"] | None = None
    payment_status: Literal["completed", "pending", "failed"] | None = None
    payee_display: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=40)


def parse_txn_changes(changes: dict) -> dict:
    """Typed, closed set of user corrections (R3.2). Values are validated here, not by DB errors."""
    if not changes:
        raise ApiError(400, "VALIDATION_FAILED", "No changes given.")
    try:
        m = _TxnChangesModel.model_validate(changes)
    except ValidationError as e:
        raise ApiError(400, "VALIDATION_FAILED", "Some changes are invalid.",
                       fields=[{"path": ".".join(map(str, x["loc"])), "issue": x["type"]} for x in e.errors()]) from None
    out = {k: getattr(m, k) for k in changes}
    for k in ("amount_satang", "occurred_date", "kind", "payment_status", "category"):
        if k in out and out[k] is None:
            raise ApiError(400, "VALIDATION_FAILED", "This field cannot be cleared.", fields=[{"path": k, "issue": "required"}])
    if out.get("occurred_at") is not None and out["occurred_at"].tzinfo is None:
        raise ApiError(400, "VALIDATION_FAILED", "occurred_at must include a timezone offset.", fields=[{"path": "occurred_at", "issue": "naive"}])
    return out


def patch_txn(conn, owner_id, txn_id, version: int, changes: dict) -> dict:
    """R3.2 corrections. Keeps the ledger invariants: refunds never exceed their source (FI-14), transfer legs stay
    equal and keep their kind (FI-13), a bill-linked payment keeps the amount/kind/status that settled the bill
    (FI-20/21), occurred_date stays the local date of occurred_at (FI-5). Any change bumps the data watermark, so
    pending proposals become stale (SI-3)."""
    ch = parse_txn_changes(changes)
    tz = user_tz(conn, owner_id)
    with conn.transaction():
        lock_owner_ledger(conn, owner_id)
        cur = conn.execute("""select id,version,kind,amount_satang,occurred_at,occurred_date,refund_of,transfer_group_id,payment_status
                              from txn where owner_id=%s and id=%s and deleted_at is null for update""", (owner_id, txn_id)).fetchone()
        if not cur:
            raise _nf()
        if cur["version"] != version:
            raise ApiError(409, "VERSION_CONFLICT", "This record changed; reload it.")
        linked_bill = conn.execute("select bill_id from bill_payment_link where owner_id=%s and txn_id=%s", (owner_id, txn_id)).fetchone()
        has_refunds = conn.execute("select coalesce(sum(amount_satang),0) s from txn where owner_id=%s and refund_of=%s and deleted_at is null",
                                   (owner_id, txn_id)).fetchone()["s"]
        if cur["transfer_group_id"] and ({"amount_satang", "kind"} & set(ch)):
            raise ApiError(409, "TXN_LINKED", "This is one leg of a transfer; edit the transfer as a whole.", details={"link": "transfer"})
        if "kind" in ch and ch["kind"] != cur["kind"]:
            if cur["kind"] not in ("expense", "income") or has_refunds or linked_bill:
                raise ApiError(409, "TXN_LINKED", "This record's type cannot change while it is linked.",
                               details={"link": "bill" if linked_bill else ("refund" if has_refunds else cur["kind"])})
        if linked_bill and (("amount_satang" in ch and ch["amount_satang"] != cur["amount_satang"])
                            or ch.get("payment_status", "completed") != "completed"):
            raise ApiError(409, "TXN_LINKED_TO_BILL", "This payment settles a bill; its amount and status must stay as they are.",
                           details={"bill_id": str(linked_bill["bill_id"])})
        if "amount_satang" in ch:
            if has_refunds > ch["amount_satang"]:
                raise ApiError(400, "VALIDATION_FAILED", "Refunds already recorded exceed the new amount.",
                               fields=[{"path": "amount_satang", "issue": "below_refunded"}])
            if cur["refund_of"]:
                src = conn.execute("select amount_satang from txn where owner_id=%s and id=%s", (owner_id, cur["refund_of"])).fetchone()
                others = conn.execute("""select coalesce(sum(amount_satang),0) s from txn where owner_id=%s and refund_of=%s
                                         and id<>%s and deleted_at is null""", (owner_id, cur["refund_of"], txn_id)).fetchone()["s"]
                if others + ch["amount_satang"] > src["amount_satang"]:
                    raise ApiError(400, "VALIDATION_FAILED", "Refunds would exceed the original amount.",
                                   fields=[{"path": "amount_satang", "issue": "refund_exceeds_source"}])
        if "occurred_at" in ch and ch["occurred_at"] is not None:
            d = local_date(ch["occurred_at"], tz)
            if "occurred_date" in ch and ch["occurred_date"] != d:
                raise ApiError(400, "VALIDATION_FAILED", "occurred_date must be the local date of occurred_at.",
                               fields=[{"path": "occurred_date", "issue": "inconsistent"}])
            ch["occurred_date"] = d
        elif "occurred_date" in ch and "occurred_at" not in ch and cur["occurred_at"] is not None \
                and local_date(cur["occurred_at"], tz) != ch["occurred_date"]:
            raise ApiError(400, "VALIDATION_FAILED", "Change the time too (or clear it) when moving a timed record to another day.",
                           fields=[{"path": "occurred_at", "issue": "inconsistent"}])
        cols: dict = {}
        for k, v in ch.items():
            if k == "category":
                if not conn.execute("select 1 from category where code=%s", (v,)).fetchone():
                    raise ApiError(400, "VALIDATION_FAILED", "Unknown category.", fields=[{"path": "category", "issue": "unknown"}])
                cols.update(category_code=v, category_state="confirmed", category_source="user")
            elif k == "payee_display":
                cols.update(payee_display=v, payee_key=normalize_payee(v))
            else:
                cols[k] = v
        if "amount_satang" in ch:
            cols["amount_state"] = "confirmed"
        if "kind" in ch:
            cols["direction_state"] = "confirmed"
        sets = ", ".join(f"{k}=%s" for k in cols)
        conn.execute(f"update txn set {sets}, version=version+1 where owner_id=%s and id=%s", (*cols.values(), owner_id, txn_id))
        bump_watermark(conn, owner_id)
        audit(conn, owner_id, "user", "txn_correct", "txn", txn_id, details={"fields": sorted(ch)})
    return get_txn(conn, owner_id, txn_id)


def delete_txn(conn, owner_id, txn_id) -> None:
    with conn.transaction():
        r = conn.execute("update txn set deleted_at=%s, bank_ref_norm=null where owner_id=%s and id=%s and deleted_at is null returning id",
                         (now_utc(), owner_id, txn_id)).fetchone()
        if not r:
            raise _nf()
        conn.execute("delete from bill_payment_link where owner_id=%s and txn_id=%s", (owner_id, txn_id))
        conn.execute("update bill set status='unpaid' where owner_id=%s and status='paid' and id not in (select bill_id from bill_payment_link where owner_id=%s)", (owner_id, owner_id))
        bump_watermark(conn, owner_id)
        audit(conn, owner_id, "user", "txn_delete", "txn", txn_id)


def set_category(conn, owner_id, txn_id, category: str, set_payee_default: bool) -> dict:
    with conn.transaction():
        if not conn.execute("select 1 from category where code=%s", (category,)).fetchone():
            raise ApiError(400, "VALIDATION_FAILED", "Unknown category.", fields=[{"path": "category", "issue": "unknown"}])
        r = conn.execute("""update txn set category_code=%s, category_state='confirmed', category_source='user', version=version+1
                            where owner_id=%s and id=%s and deleted_at is null returning payee_key""", (category, owner_id, txn_id)).fetchone()
        if not r:
            raise _nf()
        if set_payee_default and r["payee_key"]:
            conn.execute("""insert into payee_default(owner_id,payee_key,category_code) values (%s,%s,%s)
                            on conflict (owner_id,payee_key) do update set category_code=excluded.category_code, set_at=now()""",
                         (owner_id, r["payee_key"], category))
        bump_watermark(conn, owner_id)
        audit(conn, owner_id, "user", "category_confirm", "txn", txn_id, details={"category": category, "set_default": set_payee_default})
    return get_txn(conn, owner_id, txn_id)


# ---------------- bills ----------------

def create_bill(conn, owner_id, body: dict, upload_id=None) -> dict:
    row = conn.execute(
        """insert into bill(owner_id,biller,amount_due_satang,due_date,status,essential_expense_id,upload_id)
           values (%s,%s,%s,%s,'unpaid',%s,%s) returning *""",
        (owner_id, body["biller"], body["amount_due_satang"], body["due_date"], body.get("essential_expense_id"), upload_id)).fetchone()
    bump_watermark(conn, owner_id)
    audit(conn, owner_id, "user" if upload_id is None else "worker", "bill_create", "bill", row["id"])
    return row


def list_bills(conn, owner_id, status: str | None = None) -> list[dict]:
    q = "select b.*, l.txn_id as paid_by_txn_id from bill b left join bill_payment_link l on l.bill_id=b.id where b.owner_id=%s"
    args = [owner_id]
    if status:
        q += " and b.status=%s"; args.append(status)
    return conn.execute(q + " order by due_date", args).fetchall()


def link_bill_payment(conn, owner_id, bill_id, txn_id) -> dict:
    """FI-20/FI-21: exact amount, completed expense, one link each way (DB-enforced too)."""
    with conn.transaction():
        b = conn.execute("select amount_due_satang,status from bill where owner_id=%s and id=%s for update", (owner_id, bill_id)).fetchone()
        t = conn.execute("select amount_satang,kind,payment_status from txn where owner_id=%s and id=%s and deleted_at is null", (owner_id, txn_id)).fetchone()
        if not b or not t:
            raise _nf()
        if b["status"] != "unpaid":
            raise ApiError(409, "BILL_NOT_UNPAID", "This bill is already settled or cancelled.")
        if t["kind"] != "expense" or t["payment_status"] != "completed":
            raise ApiError(400, "VALIDATION_FAILED", "Only a completed expense can pay a bill.")
        if t["amount_satang"] != b["amount_due_satang"]:
            raise ApiError(400, "AMOUNT_MISMATCH", "Payment amount differs from the bill; partial payments are not supported yet.")
        try:
            with conn.transaction():
                conn.execute("insert into bill_payment_link(owner_id,bill_id,txn_id) values (%s,%s,%s)", (owner_id, bill_id, txn_id))
        except psycopg.errors.UniqueViolation:
            raise ApiError(409, "PAYMENT_ALREADY_LINKED", "This payment already settles another bill.") from None
        conn.execute("update bill set status='paid', version=version+1 where owner_id=%s and id=%s", (owner_id, bill_id))
        bump_watermark(conn, owner_id)
        audit(conn, owner_id, "user", "bill_link_payment", "bill", bill_id, details={"txn_id": str(txn_id)})
    return conn.execute("select * from bill where owner_id=%s and id=%s", (owner_id, bill_id)).fetchone()


# ---------------- consent ----------------

def list_consents(conn, owner_id) -> list[dict]:
    return conn.execute("select id,scope,version,params,granted_at,revoked_at from consent_grant where owner_id=%s order by granted_at desc", (owner_id,)).fetchall()


def active_consent(conn, owner_id, scope: str, *, lock: str | None = None):
    q = "select id,params from consent_grant where owner_id=%s and scope=%s and revoked_at is null"
    if lock:
        q += f" for {lock}"
    return conn.execute(q, (owner_id, scope)).fetchone()


def grant_consent(conn, owner_id, scope: str, version: str, params: dict) -> dict:
    if scope not in CONSENT_SCOPES:
        raise ApiError(400, "VALIDATION_FAILED", "Unknown consent scope.")
    with conn.transaction():
        if active_consent(conn, owner_id, scope, lock="update"):
            raise ApiError(409, "CONSENT_ALREADY_ACTIVE", "Revoke the current consent before granting a new version.")
        row = conn.execute("insert into consent_grant(owner_id,scope,version,params) values (%s,%s,%s,%s) returning id,scope,version,params,granted_at",
                           (owner_id, scope, version, Jsonb(params))).fetchone()
        audit(conn, owner_id, "user", "consent_grant", "consent", row["id"], details={"scope": scope, "version": version})
    return row


def revoke_consent(conn, owner_id, scope: str) -> dict:
    """SI-5: revoke and cancel queued work in one transaction. Workers persisting results lock the
    grant FOR SHARE, so this UPDATE serialises with any in-flight persist."""
    with conn.transaction():
        g = active_consent(conn, owner_id, scope, lock="update")
        if not g:
            raise _nf()
        conn.execute("update consent_grant set revoked_at=%s where id=%s", (now_utc(), g["id"]))
        cancelled = 0
        if scope == "photo_processing":
            cancelled = conn.execute("""update job set status='cancelled' where owner_id=%s and status in ('queued','running')
                                        and consent_grant_id=%s""", (owner_id, g["id"])).rowcount
            conn.execute("""update upload set status='cancelled_consent' where owner_id=%s and consent_grant_id=%s
                            and status in ('received','extracting')""", (owner_id, g["id"]))
        if scope == "chat_history_retention":
            conn.execute("delete from chat_message where owner_id=%s", (owner_id,))
        audit(conn, owner_id, "user", "consent_revoke", "consent", g["id"], details={"scope": scope, "jobs_cancelled": cancelled})
    return {"scope": scope, "revoked": True, "jobs_cancelled": cancelled}


def payee_info(display: str | None) -> tuple[str | None, bool]:
    return normalize_payee(display), is_intermediary(display)


def ref_norm(ref: str | None) -> str | None:
    return normalize_ref(ref)


def new_id() -> uuid.UUID:
    return uuid.uuid4()


def tzinfo(tz: str) -> ZoneInfo:
    return ZoneInfo(tz)
