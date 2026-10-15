"""Snapshot → cash-flow plan, pockets, goals, proposals and approvals (SI-3, SI-4, FI-16..FI-27)."""

from __future__ import annotations

import calendar
from dataclasses import asdict
from datetime import date, timedelta

from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, ValidationError, field_validator

from finassist.api.errors import ApiError
from finassist.domain import cashflow as cf
from finassist.domain import goals as goals_d
from finassist.domain.allocation import Share, allocate_bps, reallocate
from finassist.domain.ledger import BalanceObservation, Txn, projected_balance, spending
from finassist.infra import audit, bump_watermark, canonical_json, current_watermark, lock_owner_for_approval, sha256
from finassist.services.core import _nf, now_utc, today_for, user_tz

PROPOSAL_TTL = timedelta(minutes=30)


# ---------------- snapshot ----------------

def _to_domain(r: dict) -> Txn:
    return Txn(str(r["id"]), str(r["account_id"]), r["kind"], r["amount_satang"], r["occurred_date"], r["occurred_at"],
               r["payment_status"], r["amount_state"], r["direction_state"], r["category_code"], r["category_state"],
               str(r["refund_of"]) if r["refund_of"] else None, str(r["transfer_group_id"]) if r["transfer_group_id"] else None,
               r["payee_key"])


def load_txns(conn, owner_id, start: date | None = None) -> list[Txn]:
    q = """select id,account_id,kind,amount_satang,occurred_date,occurred_at,payment_status,amount_state,direction_state,
                  category_code,category_state,refund_of,transfer_group_id,payee_key
           from txn where owner_id=%s and deleted_at is null"""
    args: list = [owner_id]
    if start:
        q += " and occurred_date >= %s"; args.append(start)
    return [_to_domain(r) for r in conn.execute(q, args).fetchall()]


def available_balance(conn, owner_id, txns: list[Txn]) -> tuple[int, list[dict]]:
    accts = conn.execute("select id from account where owner_id=%s and kind='spending' and tracked", (owner_id,)).fetchall()
    tz = user_tz(conn, owner_id)
    total, per = 0, []
    for a in accts:
        obs = conn.execute("""select amount_satang,as_of from balance_observation where owner_id=%s and account_id=%s
                              order by as_of desc, created_at desc limit 1""", (owner_id, a["id"])).fetchone()
        if not obs:
            continue
        bal = projected_balance(BalanceObservation(str(a["id"]), obs["amount_satang"], obs["as_of"]), txns, tz)
        per.append({"account_id": str(a["id"]), "observed_satang": obs["amount_satang"], "as_of": obs["as_of"], "projected_satang": bal})
        total += bal
    if not per:
        raise ApiError(422, "BALANCE_REQUIRED", "Tell me your current balance first.", details={"ask": "current_balance"})
    return total, per


def _next_due(today: date, due_day: int | None) -> date:
    day = due_day or 1
    y, m = today.year, today.month
    d = date(y, m, min(day, calendar.monthrange(y, m)[1]))
    if d < today:
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        d = date(y, m, min(day, calendar.monthrange(y, m)[1]))
    return d


def current_plan(conn, owner_id, today: date):
    return conn.execute("""select id,period_start,period_end,buffer_satang,version from budget_plan
                           where owner_id=%s and period_start<=%s and period_end>%s""", (owner_id, today, today)).fetchone()


def cashflow_inputs(conn, owner_id, *, txns: list[Txn] | None = None) -> tuple[cf.CashflowInputs, dict]:
    tz = user_tz(conn, owner_id)
    today = today_for(tz)
    inc = conn.execute("select amount_satang,frequency,next_income_date from income_schedule where owner_id=%s", (owner_id,)).fetchone()
    if not inc:
        raise ApiError(422, "PROFILE_REQUIRED", "Tell me your income and next pay date first.", details={"ask": "income"})
    txns = txns if txns is not None else load_txns(conn, owner_id)
    avail, per = available_balance(conn, owner_id, txns)
    bills = conn.execute("select id,amount_due_satang,due_date,essential_expense_id from bill where owner_id=%s and status='unpaid'", (owner_id,)).fetchall()
    ess = conn.execute("select id,amount_satang,due_day from essential_expense where owner_id=%s", (owner_id,)).fetchall()
    gl = conn.execute("select id,contribution_satang_per_period from goal where owner_id=%s and status='active' and contribution_satang_per_period>0", (owner_id,)).fetchall()
    plan = current_plan(conn, owner_id, today)
    inp = cf.CashflowInputs(
        today=today, next_income_date=inc["next_income_date"], next_income_satang=inc["amount_satang"],
        available_balance_satang=avail,
        unpaid_bills=tuple(cf.UnpaidBill(str(b["id"]), b["amount_due_satang"], b["due_date"],
                                         str(b["essential_expense_id"]) if b["essential_expense_id"] else None) for b in bills),
        essentials=tuple(cf.Essential(str(e["id"]), e["amount_satang"], _next_due(today, e["due_day"])) for e in ess),
        savings=tuple(cf.SavingsCommitment(f"goal:{g['id']}", g["contribution_satang_per_period"]) for g in gl),
        buffer=cf.Buffer(amount_satang=plan["buffer_satang"] if plan else 0),
    )
    return inp, {"accounts": per, "income": inc, "plan": plan, "today": today}


def get_plan(conn, owner_id) -> dict:
    txns = load_txns(conn, owner_id)
    inp, ctx = cashflow_inputs(conn, owner_id, txns=txns)
    try:
        res = cf.compute(inp)
    except Exception as e:  # NextIncomeDatePassed
        if e.__class__.__name__ == "NextIncomeDatePassed":
            raise ApiError(422, "NEXT_INCOME_DATE_PASSED", "Your next pay date has passed; please update it.", details={"ask": "next_income_date"}) from None
        raise
    out = {"cashflow": asdict(res), "accounts": ctx["accounts"], "today": ctx["today"], "plan": None, "pockets": [],
           "data_watermark": current_watermark(conn, owner_id)}
    if ctx["plan"]:
        out["plan"] = ctx["plan"]
        out["pockets"] = pocket_status(conn, owner_id, ctx["plan"], txns)
    return out


def pocket_status(conn, owner_id, plan: dict, txns: list[Txn]) -> list[dict]:
    pockets = conn.execute("""select p.id,p.name,coalesce(a.allocation_satang,0) alloc from pocket p
                              left join pocket_allocation a on a.pocket_id=p.id and a.plan_id=%s
                              where p.owner_id=%s and p.archived_at is null order by p.sort_key,p.name""", (plan["id"], owner_id)).fetchall()
    cmap = {r["category_code"]: str(r["pocket_id"]) for r in conn.execute("select category_code,pocket_id from pocket_category_map where owner_id=%s", (owner_id,)).fetchall()}
    s = spending(txns, plan["period_start"], plan["period_end"])
    out = []
    for p in pockets:
        pid = str(p["id"])
        conf = sum(v["confirmed"] for c, v in s.by_category.items() if cmap.get(c) == pid)
        pred = sum(v["predicted"] for c, v in s.by_category.items() if cmap.get(c) == pid)
        out.append({"pocket_id": pid, "name": p["name"], "allocation_satang": p["alloc"], "spent_confirmed_satang": conf,
                    "spent_predicted_satang": pred, "remaining_satang": p["alloc"] - conf - pred,
                    "overspent": conf + pred > p["alloc"]})
    unmapped = sum(v["confirmed"] + v["predicted"] for c, v in s.by_category.items() if c not in cmap)
    out.append({"pocket_id": None, "name": "(unassigned)", "allocation_satang": None, "spent_confirmed_satang": None,
                "spent_predicted_satang": None, "unassigned_satang": s.unassigned_satang + unmapped,
                "excluded_unresolved_count": s.excluded_count, "remaining_satang": None, "overspent": False})
    return out


def affordability(conn, owner_id, amount_satang: int) -> dict:
    inp, _ = cashflow_inputs(conn, owner_id)
    a = cf.affordability(inp, amount_satang)
    return {"amount_satang": amount_satang, "affordable": a.affordable, "shortage_after_satang": a.shortage_after_satang,
            "daily_allowance_before_satang": a.before.daily_allowance_satang,
            "daily_allowance_after_satang": a.after.daily_allowance_satang,
            "bills_reserved_satang": sum(ln.amount_satang for ln in a.before.lines if ln.kind == "bill"),
            "recorded": False, "calculation": cf.CALC_VERSION}


# ---------------- pockets ----------------

def create_pocket(conn, owner_id, name: str, categories: list[str]) -> dict:
    with conn.transaction():
        p = conn.execute("insert into pocket(owner_id,name) values (%s,%s) returning id,name", (owner_id, name)).fetchone()
        for c in categories:
            conn.execute("""insert into pocket_category_map(owner_id,category_code,pocket_id) values (%s,%s,%s)
                            on conflict (owner_id,category_code) do update set pocket_id=excluded.pocket_id""", (owner_id, c, p["id"]))
        bump_watermark(conn, owner_id)
        audit(conn, owner_id, "user", "pocket_create", "pocket", p["id"])
    return p


# ---------------- proposals ----------------

class BudgetPlanPayload(BaseModel):
    model_config = {"extra": "forbid"}
    period_start: date
    period_end: date
    buffer_satang: int = Field(ge=0)
    allocations: dict[str, int]  # pocket_id -> satang

    @field_validator("allocations")
    @classmethod
    def _nonneg(cls, v):
        if any((not isinstance(x, int)) or x < 0 for x in v.values()):
            raise ValueError("allocations must be non-negative integers")
        return v


class ReallocatePayload(BaseModel):
    model_config = {"extra": "forbid"}
    plan_id: str
    from_pocket: str
    to_pocket: str
    amount_satang: int = Field(gt=0)


class GoalCreatePayload(BaseModel):
    model_config = {"extra": "forbid"}
    name: str = Field(min_length=1, max_length=80)
    target_satang: int = Field(gt=0)
    saved_satang: int = Field(ge=0, default=0)
    deadline: date
    contribution_satang_per_period: int = Field(ge=0)


class GoalUpdatePayload(BaseModel):
    model_config = {"extra": "forbid"}
    goal_id: str
    target_satang: int | None = Field(default=None, gt=0)
    deadline: date | None = None
    contribution_satang_per_period: int | None = Field(default=None, ge=0)


PAYLOADS = {"budget_plan": BudgetPlanPayload, "reallocate": ReallocatePayload, "goal_create": GoalCreatePayload, "goal_update": GoalUpdatePayload}


def _hash(kind: str, payload: dict) -> bytes:
    return sha256(kind + "\n" + canonical_json(payload))


def _validate_payload(kind: str, payload: dict) -> dict:
    model = PAYLOADS.get(kind)
    if not model:
        raise ApiError(400, "VALIDATION_FAILED", "Unknown proposal kind.")
    try:
        return model.model_validate(payload).model_dump(mode="json")
    except ValidationError as e:
        raise ApiError(400, "VALIDATION_FAILED", "Invalid proposal.", fields=[{"path": ".".join(map(str, x["loc"])), "issue": x["type"]} for x in e.errors()]) from None


def unspent_allocations(conn, owner_id, period_start: date, period_end: date, allocations: dict[str, int]) -> int:
    """Σ over pockets of max(0, allocation − spending already attributed to that pocket in the period)."""
    cmap = {r["category_code"]: str(r["pocket_id"]) for r in conn.execute(
        "select category_code, pocket_id from pocket_category_map where owner_id=%s", (owner_id,)).fetchall()}
    s = spending(load_txns(conn, owner_id), period_start, period_end)
    spent: dict[str, int] = {}
    for code, v in s.by_category.items():
        pid = cmap.get(code)
        if pid:
            spent[pid] = spent.get(pid, 0) + v["confirmed"] + v["predicted"]
    return sum(max(0, amt - spent.get(str(pid), 0)) for pid, amt in allocations.items())


def _enforce_unspent_fits(conn, owner_id, period_start: date, period_end: date, buffer_satang: int,
                          old_alloc: dict[str, int], new_alloc: dict[str, int], *,
                          old_buffer_satang: int | None = None, old_period: tuple[date, date] | None = None) -> None:
    """BP-1 (Codex CP1 review, finding #1): the budget still available to spend across all pockets must fit the
    money actually available now. Σ max(0, allocation_i − spent_i) ≤ max(0, discretionary_now).
    A change that does not increase the unspent total is allowed without the money check ONLY if it also does not
    raise the buffer and keeps the same period (Codex re-review #1: raising the buffer alone used to slip through)."""
    from dataclasses import replace

    new_unspent = unspent_allocations(conn, owner_id, period_start, period_end, new_alloc)
    old_unspent = unspent_allocations(conn, owner_id, period_start, period_end, old_alloc) if old_alloc else 0
    same_period = old_period is not None and tuple(map(str, old_period)) == (str(period_start), str(period_end))
    buffer_not_raised = old_buffer_satang is not None and buffer_satang <= old_buffer_satang
    if old_alloc and new_unspent <= old_unspent and same_period and buffer_not_raised:
        return
    inp, _ = cashflow_inputs(conn, owner_id)
    disc = cf.compute(replace(inp, buffer=cf.Buffer(amount_satang=buffer_satang))).discretionary_satang
    if new_unspent > max(0, disc):
        raise ApiError(400, "ALLOCATION_EXCEEDS_AVAILABLE", "Pocket budgets would exceed the money available until next income.",
                       details={"unspent_after_satang": new_unspent, "available_satang": max(0, disc), "unspent_before_satang": old_unspent})


def _check_applicable(conn, owner_id, kind: str, p: dict, *, lock: bool) -> dict:
    """Validates the payload against current state. Returns base versions. Raises ApiError if impossible."""
    fu = " for update" if lock else ""
    base = {"base_plan_id": None, "base_plan_version": None, "base_goal_version": None}
    if kind == "reallocate":
        plan = conn.execute(f"select id,version from budget_plan where owner_id=%s and id=%s{fu}", (owner_id, p["plan_id"])).fetchone()
        if not plan:
            raise _nf()
        rows = conn.execute("select pocket_id,allocation_satang from pocket_allocation where owner_id=%s and plan_id=%s", (owner_id, plan["id"])).fetchall()
        alloc = {str(r["pocket_id"]): r["allocation_satang"] for r in rows}
        try:
            new_alloc = reallocate(alloc, p["from_pocket"], p["to_pocket"], p["amount_satang"])
        except KeyError:
            raise _nf() from None
        except ValueError as e:
            raise ApiError(400, "VALIDATION_FAILED", str(e)) from None
        pr = conn.execute("select period_start, period_end, buffer_satang from budget_plan where id=%s", (plan["id"],)).fetchone()
        _enforce_unspent_fits(conn, owner_id, pr["period_start"], pr["period_end"], pr["buffer_satang"], alloc, new_alloc,
                              old_buffer_satang=pr["buffer_satang"], old_period=(pr["period_start"], pr["period_end"]))
        base.update(base_plan_id=plan["id"], base_plan_version=plan["version"])
    elif kind == "budget_plan":
        if p["period_start"] >= p["period_end"]:
            raise ApiError(400, "VALIDATION_FAILED", "period_start must be before period_end.")
        owned = {str(r["id"]) for r in conn.execute("select id from pocket where owner_id=%s and archived_at is null", (owner_id,)).fetchall()}
        if not set(p["allocations"]) <= owned:
            raise _nf()
        existing = conn.execute(f"select id,version,period_start,period_end,buffer_satang from budget_plan where owner_id=%s and period_start=%s{fu}",
                                (owner_id, p["period_start"])).fetchone()
        old_alloc = {}
        if existing:
            old_alloc = {str(r["pocket_id"]): r["allocation_satang"] for r in conn.execute(
                "select pocket_id, allocation_satang from pocket_allocation where owner_id=%s and plan_id=%s", (owner_id, existing["id"])).fetchall()}
        _enforce_unspent_fits(conn, owner_id, date.fromisoformat(str(p["period_start"])), date.fromisoformat(str(p["period_end"])),
                              p["buffer_satang"], old_alloc, p["allocations"],
                              old_buffer_satang=existing["buffer_satang"] if existing else None,
                              old_period=(existing["period_start"], existing["period_end"]) if existing else None)
        if existing:
            base.update(base_plan_id=existing["id"], base_plan_version=existing["version"])
    elif kind == "goal_update":
        g = conn.execute(f"select id,version,status,target_satang,deadline,contribution_satang_per_period from goal where owner_id=%s and id=%s{fu}",
                         (owner_id, p["goal_id"])).fetchone()
        if not g:
            raise _nf()
        if g["status"] != "active":
            raise ApiError(409, "GOAL_NOT_ACTIVE", "Only an active goal can be changed.")
        if all(p.get(k) is None or str(p[k]) == str(g[k]) for k in ("target_satang", "deadline", "contribution_satang_per_period")):
            raise ApiError(400, "NO_CHANGE", "The proposal does not change the goal.")
        _deadline_in_future(conn, owner_id, p.get("deadline"))
        base.update(base_goal_version=g["version"])
    elif kind == "goal_create":
        _deadline_in_future(conn, owner_id, p["deadline"])
    return base


def _deadline_in_future(conn, owner_id, deadline) -> None:
    if deadline is not None and date.fromisoformat(str(deadline)) <= today_for(user_tz(conn, owner_id)):
        raise ApiError(400, "VALIDATION_FAILED", "The goal deadline must be after today.", fields=[{"path": "deadline", "issue": "not_in_future"}])


def _insert_proposal(conn, owner_id, kind: str, p: dict, base: dict, created_by: str, assumptions: list[dict], *,
                     edited_from=None, extra: dict | None = None) -> dict:
    """Insert a pending proposal with its approval card. The watermark is read BEFORE the card is computed, so a
    ledger change committed in between makes the proposal stale at approval instead of approving an outdated card."""
    from finassist.services import cards

    wm = current_watermark(conn, owner_id)
    ph = _hash(kind, p)
    now = now_utc()
    card = cards.build_card(conn, owner_id, kind, p, payload_hash_hex=ph.hex(), created_by=created_by, assumptions=assumptions,
                            computed_at=now, edited_from=str(edited_from) if edited_from else None, extra=extra)
    row = conn.execute(
        """insert into proposal(owner_id,kind,payload,payload_hash,base_plan_id,base_plan_version,base_goal_version,
                                base_data_watermark,created_by,status,expires_at,card,card_hash,edited_from)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s,%s,%s,%s) returning *""",
        (owner_id, kind, Jsonb(p), ph, base["base_plan_id"], base["base_plan_version"], base["base_goal_version"],
         wm, created_by, now + PROPOSAL_TTL, Jsonb(card), cards.card_hash(card), edited_from)).fetchone()
    audit(conn, owner_id, created_by, "proposal_create", "proposal", row["id"],
          details={"kind": kind, "edited_from": str(edited_from) if edited_from else None,
                   "warnings": [w["code"] for w in card["warnings"]]})
    return row


def create_proposal(conn, owner_id, kind: str, payload: dict, created_by: str, assumptions: list[dict] | None = None,
                    extra: dict | None = None) -> dict:
    """T2: writes a pending proposal (with its card) only. Never mutates plans or goals."""
    p = _validate_payload(kind, payload)
    with conn.transaction():
        base = _check_applicable(conn, owner_id, kind, p, lock=False)
        row = _insert_proposal(conn, owner_id, kind, p, base, created_by, assumptions or [], extra=extra)
    return proposal_view(row)


def proposal_view(row: dict) -> dict:
    """What the client renders and later sends back. Everything here is read from the stored row, so a reload
    returns the same card; only `status`/`actions` reflect the current time."""
    status = row["status"]
    if status == "pending" and row["expires_at"] <= now_utc():
        status = "expired"
    pid = str(row["id"])
    actions = []
    if status == "pending" and row["card"] is not None:
        actions = [
            {"action": "approve", "method": "POST", "path": f"/v1/proposals/{pid}/approve",
             "body": {"payload_hash": "sha256:" + bytes(row["payload_hash"]).hex(), "card_hash": "sha256:" + bytes(row["card_hash"]).hex()},
             "requires_header": "Idempotency-Key"},
            {"action": "edit", "method": "POST", "path": f"/v1/proposals/{pid}/edit",
             "note": "creates a new proposal with a new card; this one becomes superseded and cannot be approved"},
            {"action": "cancel", "method": "POST", "path": f"/v1/proposals/{pid}/cancel"},
        ]
    return {"type": "proposal", "proposal_id": pid, "kind": row["kind"], "status": status, "created_by": row["created_by"],
            "created_at": row["created_at"], "expires_at": row["expires_at"], "decided_at": row["decided_at"],
            "payload": row["payload"], "payload_hash": "sha256:" + bytes(row["payload_hash"]).hex(),
            "card_hash": ("sha256:" + bytes(row["card_hash"]).hex()) if row["card_hash"] is not None else None,
            "card": row["card"], "superseded_by": str(row["superseded_by"]) if row["superseded_by"] else None,
            "edited_from": str(row["edited_from"]) if row["edited_from"] else None, "actions": actions}


def get_proposal(conn, owner_id, pid) -> dict:
    row = conn.execute("select * from proposal where owner_id=%s and id=%s", (owner_id, pid)).fetchone()
    if not row:
        raise _nf()
    return proposal_view(row)


def list_proposals(conn, owner_id, status: str | None = None, limit: int = 20) -> list[dict]:
    q = "select * from proposal where owner_id=%s"
    args: list = [owner_id]
    if status == "pending":
        q += " and status='pending' and expires_at > %s"; args.append(now_utc())
    elif status:
        q += " and status=%s"; args.append(status)
    q += " order by created_at desc, id limit %s"; args.append(min(limit, 100))
    return [proposal_view(r) for r in conn.execute(q, args).fetchall()]


def edit_proposal(conn, owner_id, pid, payload_hash: str, new_payload: dict) -> tuple[int, dict]:
    """Edit = new proposal, new card, new hashes; the old one is superseded in the same transaction, so no approval
    request for the old id or old hashes can apply the edited content (FI-33)."""
    with conn.transaction():
        old = conn.execute("select * from proposal where owner_id=%s and id=%s for update", (owner_id, pid)).fetchone()
        if not old:
            raise _nf()
        if old["status"] != "pending":
            return 409, _err("PROPOSAL_NOT_PENDING", f"This proposal is {old['status']}.",
                             {"status": old["status"], "superseded_by": str(old["superseded_by"]) if old["superseded_by"] else None})
        if old["expires_at"] <= now_utc():
            conn.execute("update proposal set status='expired', decided_at=%s where id=%s", (now_utc(), pid))
            return 410, _err("PROPOSAL_EXPIRED", "This proposal expired; ask again for a fresh one.", {})
        if payload_hash.removeprefix("sha256:") != bytes(old["payload_hash"]).hex():
            return 409, _err("PROPOSAL_MISMATCH", "The proposal you edited differs from this one.", {})
        p = _validate_payload(old["kind"], new_payload)
        if canonical_json(p) == canonical_json(old["payload"]):
            raise ApiError(400, "NO_CHANGE", "The edited proposal is the same as the original.")
        base = _check_applicable(conn, owner_id, old["kind"], p, lock=False)
        row = _insert_proposal(conn, owner_id, old["kind"], p, base, "user",
                               [{"kind": "edited_by_user", "text": "You edited an earlier proposal; amounts were recalculated."}],
                               edited_from=old["id"])
        conn.execute("update proposal set status='superseded', superseded_by=%s, decided_at=%s where id=%s", (row["id"], now_utc(), pid))
        audit(conn, owner_id, "user", "proposal_edit", "proposal", pid, details={"new_proposal_id": str(row["id"])})
    return 201, proposal_view(row)


def approve(conn, owner_id, pid, payload_hash: str, card_hash: str) -> tuple[int, dict]:
    """T3, user only. Must run inside the idempotency wrapper's transaction. The ledger lock + watermark row lock
    are taken first and held until commit, so no ledger change can commit between the checks below and _apply."""
    wm = lock_owner_for_approval(conn, owner_id)
    pr = conn.execute("select * from proposal where owner_id=%s and id=%s for update", (owner_id, pid)).fetchone()
    if not pr:
        raise _nf()
    if pr["status"] == "applied":
        return 409, _err("PROPOSAL_ALREADY_APPLIED", "This change was already applied.", {"proposal_id": str(pid)})
    if pr["status"] != "pending":
        return 409, _err("PROPOSAL_NOT_PENDING", f"This proposal is {pr['status']}.", {"status": pr["status"]})
    if pr["expires_at"] <= now_utc():
        conn.execute("update proposal set status='expired', decided_at=%s where id=%s", (now_utc(), pid))
        audit(conn, owner_id, "user", "proposal_approve", "proposal", pid, result="rejected", details={"why": "expired"})
        return 410, _err("PROPOSAL_EXPIRED", "This proposal expired; ask again for a fresh one.", {})
    if payload_hash.removeprefix("sha256:") != bytes(pr["payload_hash"]).hex():
        audit(conn, owner_id, "user", "proposal_approve", "proposal", pid, result="rejected", details={"why": "hash_mismatch"})
        return 409, _err("PROPOSAL_MISMATCH", "What you approved differs from this proposal.", {})
    if pr["card_hash"] is not None and card_hash.removeprefix("sha256:") != bytes(pr["card_hash"]).hex():
        audit(conn, owner_id, "user", "proposal_approve", "proposal", pid, result="rejected", details={"why": "card_mismatch"})
        return 409, _err("PROPOSAL_MISMATCH", "The card you approved differs from this proposal's card. Reload it.", {})
    p = pr["payload"]
    try:
        base = _check_applicable(conn, owner_id, pr["kind"], p, lock=True)
    except ApiError as e:
        conn.execute("update proposal set status='stale', decided_at=%s where id=%s", (now_utc(), pid))
        audit(conn, owner_id, "user", "proposal_approve", "proposal", pid, result="rejected", details={"why": e.code})
        return 409, _err("PROPOSAL_STALE", "This proposal no longer fits your current budget.", {"reason": e.code})
    stale = (str(base["base_plan_id"]) != str(pr["base_plan_id"]) if (base["base_plan_id"] or pr["base_plan_id"]) else False) \
        or base["base_plan_version"] != pr["base_plan_version"] or base["base_goal_version"] != pr["base_goal_version"] \
        or wm != pr["base_data_watermark"] or pr["card"] is None
    if stale:
        conn.execute("update proposal set status='stale', decided_at=%s where id=%s", (now_utc(), pid))
        assumptions = (pr["card"] or {}).get("assumptions", [])
        repl = _insert_proposal(conn, owner_id, pr["kind"], p, base, pr["created_by"], assumptions)
        conn.execute("update proposal set superseded_by=%s where id=%s", (repl["id"], pid))
        audit(conn, owner_id, "user", "proposal_approve", "proposal", pid, result="rejected", details={"why": "stale"})
        return 409, _err("PROPOSAL_STALE", "Your data changed since this proposal was made. Review the refreshed one.",
                         {"replacement_proposal_id": str(repl["id"]), "replacement": proposal_view(repl)})
    result = _apply(conn, owner_id, pr["kind"], p)
    conn.execute("update proposal set status='applied', decided_at=%s where id=%s", (now_utc(), pid))
    bump_watermark(conn, owner_id)
    audit(conn, owner_id, "user", "proposal_approve", "proposal", pid, details={"kind": pr["kind"]})
    return 200, {"proposal_id": str(pid), "status": "applied", "result": result}


def _apply(conn, owner_id, kind: str, p: dict) -> dict:
    if kind == "reallocate":
        for pocket, delta in ((p["from_pocket"], -p["amount_satang"]), (p["to_pocket"], p["amount_satang"])):
            conn.execute("""update pocket_allocation set allocation_satang=allocation_satang+%s
                            where owner_id=%s and plan_id=%s and pocket_id=%s""", (delta, owner_id, p["plan_id"], pocket))
        conn.execute("update budget_plan set version=version+1 where owner_id=%s and id=%s", (owner_id, p["plan_id"]))
        return {"plan_id": p["plan_id"]}
    if kind == "budget_plan":
        plan = conn.execute("""insert into budget_plan(owner_id,period_start,period_end,buffer_satang) values (%s,%s,%s,%s)
                               on conflict (owner_id,period_start) do update set period_end=excluded.period_end,
                               buffer_satang=excluded.buffer_satang, version=budget_plan.version+1 returning id""",
                            (owner_id, p["period_start"], p["period_end"], p["buffer_satang"])).fetchone()
        conn.execute("delete from pocket_allocation where owner_id=%s and plan_id=%s", (owner_id, plan["id"]))
        for pocket, amt in p["allocations"].items():
            conn.execute("insert into pocket_allocation(owner_id,plan_id,pocket_id,allocation_satang) values (%s,%s,%s,%s)",
                         (owner_id, plan["id"], pocket, amt))
        return {"plan_id": str(plan["id"])}
    if kind == "goal_create":
        g = conn.execute("""insert into goal(owner_id,name,target_satang,saved_satang,deadline,contribution_satang_per_period,status)
                            values (%s,%s,%s,%s,%s,%s,'active') returning id""",
                         (owner_id, p["name"], p["target_satang"], p["saved_satang"], p["deadline"], p["contribution_satang_per_period"])).fetchone()
        return {"goal_id": str(g["id"])}
    if kind == "goal_update":
        sets = {k: v for k, v in p.items() if k != "goal_id" and v is not None}
        if sets:
            conn.execute(f"update goal set {', '.join(f'{k}=%s' for k in sets)}, version=version+1 where owner_id=%s and id=%s",
                         (*sets.values(), owner_id, p["goal_id"]))
        return {"goal_id": p["goal_id"]}
    raise ApiError(400, "VALIDATION_FAILED", "Unknown kind.")


def cancel(conn, owner_id, pid) -> dict:
    with conn.transaction():
        r = conn.execute("update proposal set status='cancelled', decided_at=%s where owner_id=%s and id=%s and status='pending' returning id",
                         (now_utc(), owner_id, pid)).fetchone()
        if not r:
            raise _nf()
        audit(conn, owner_id, "user", "proposal_cancel", "proposal", pid)
    return {"proposal_id": str(pid), "status": "cancelled"}


def _err(code: str, msg: str, details: dict) -> dict:
    return {"error": {"code": code, "message": msg, "fields": [], "retryable": False, "request_id": None, "details": details}}


# ---------------- suggestions (T1/T2 helpers used by API and agent) ----------------

DEFAULT_SHARES_BPS = {"Food": 4000, "Transport": 1500, "Shopping": 1500, "Entertainment": 1000, "Other": 2000}


def suggest_budget_plan(conn, owner_id, buffer_satang: int = 0) -> dict:
    """Propose allocations of discretionary money across the user's pockets (R5.2). Returns a proposal card."""
    inp, ctx = cashflow_inputs(conn, owner_id)
    from dataclasses import replace
    res = cf.compute(replace(inp, buffer=cf.Buffer(amount_satang=buffer_satang)))
    pockets = conn.execute("select id,name from pocket where owner_id=%s and archived_at is null order by sort_key,name", (owner_id,)).fetchall()
    if not pockets:
        raise ApiError(422, "POCKETS_REQUIRED", "Create pockets first.")
    raw = [DEFAULT_SHARES_BPS.get(p["name"], 1000) for p in pockets]
    total = sum(raw)
    shares = [Share(str(p["id"]), r * 10_000 // total) for p, r in zip(pockets, raw)]
    base = max(0, res.discretionary_satang)
    alloc = allocate_bps(base, shares, "discretionary_until_next_income")
    allocations = dict(alloc.amounts)
    if alloc.unallocated_satang:  # bps flooring leftovers go to the first pocket so totals reconcile
        first = shares[0].key
        allocations[first] += alloc.unallocated_satang
    payload = {"period_start": ctx["today"].isoformat(), "period_end": inp.next_income_date.isoformat(),
               "buffer_satang": buffer_satang, "allocations": allocations}
    calc = {"function": "allocate_bps", "version": cf.CALC_VERSION, "discretionary_satang": res.discretionary_satang,
            "lines": [asdict(ln) for ln in res.lines]}
    return create_proposal(conn, owner_id, "budget_plan", payload, "agent",
                           assumptions=[{"kind": "percentage_base", "text": "Percentages are of money left after bills, essentials, savings and buffer until your next income."}],
                           extra={"calculation": calc})


def goal_feasibility(conn, owner_id, target_satang: int, saved_satang: int, deadline: date, capacity_per_event_satang: int | None = None) -> dict:
    inp, ctx = cashflow_inputs(conn, owner_id)
    res = cf.compute(inp)
    if capacity_per_event_satang is None:
        # Conservative capacity: this period's discretionary money, never negative. Stated as an assumption.
        capacity_per_event_satang = max(0, res.discretionary_satang)
    f = goals_d.feasibility(target_satang, saved_satang, deadline, inp.next_income_date, ctx["income"]["frequency"], capacity_per_event_satang)
    return {**asdict(f), "assumption": "capacity per income event = money left after commitments this period"}


# ---------------- insights, trade-offs, spending (R5.1, R5.4, R5.5, R7.3–R7.5) ----------------

def insights(conn, owner_id) -> dict:
    from finassist.domain import insights as ins

    txns = load_txns(conn, owner_id)
    tz = user_tz(conn, owner_id)
    today = today_for(tz)
    hist = ins.monthly_history(txns, today, 3)
    out: dict = {"history": hist, "recurring": [asdict(r) for r in ins.recurring_charges(txns)]}
    bills = conn.execute("select biller,due_date,amount_due_satang from bill where owner_id=%s and status<>'cancelled'", (owner_id,)).fetchall()
    out["bill_changes"] = [asdict(b) for b in ins.bill_changes([(b["biller"], b["due_date"], b["amount_due_satang"]) for b in bills])]
    try:
        plan = get_plan(conn, owner_id)
        out["shortage_satang"] = plan["cashflow"]["shortage_satang"]
        out["money_left_satang"] = plan["cashflow"]["discretionary_satang"]
        if plan["plan"]:
            out["pace_alerts"] = [asdict(a) for a in ins.pace_alerts(plan["pockets"], plan["plan"]["period_start"], plan["plan"]["period_end"], today)]
            out["unassigned_satang"] = next(p["unassigned_satang"] for p in plan["pockets"] if p["pocket_id"] is None)
    except ApiError as e:
        out["plan_unavailable"] = e.code
    recs = []
    goals = conn.execute("select id,name,target_satang,saved_satang,deadline from goal where owner_id=%s and status='active'", (owner_id,)).fetchall()
    inc = conn.execute("select frequency,next_income_date from income_schedule where owner_id=%s", (owner_id,)).fetchone()
    cap = max(0, out.get("money_left_satang") or 0)
    for r in ins.recommendations(hist):
        item = asdict(r)
        impacts = []
        if inc:
            for g in goals:
                before = goals_d.feasibility(g["target_satang"], g["saved_satang"], g["deadline"], inc["next_income_date"], inc["frequency"], cap)
                after = goals_d.feasibility(g["target_satang"], g["saved_satang"], g["deadline"], inc["next_income_date"], inc["frequency"],
                                            cap + r.estimated_savings_per_month_satang)
                impacts.append({"goal": g["name"], "feasible_before": before.feasible, "feasible_after": after.feasible,
                                "later_deadline_before": before.later_deadline, "later_deadline_after": after.later_deadline})
        item["goal_impact"] = impacts
        recs.append(item)
    out["recommendations"] = recs
    out["evidence_note"] = "Based on detected/entered transactions only; categories marked predicted are guesses until confirmed."
    return out


def propose_tradeoff(conn, owner_id, pocket_id: str, increase_satang: int) -> dict:
    """R5.4: raise one pocket and take the amount from the others' unspent allocation. Returns a T2 proposal."""
    today = today_for(user_tz(conn, owner_id))
    plan = current_plan(conn, owner_id, today)
    if not plan:
        raise ApiError(422, "PLAN_REQUIRED", "Create a budget plan first.")
    txns = load_txns(conn, owner_id)
    st = {p["pocket_id"]: p for p in pocket_status(conn, owner_id, plan, txns) if p["pocket_id"]}
    if pocket_id not in st:
        raise _nf()
    alloc = {k: v["allocation_satang"] for k, v in st.items()}
    spent = {k: v["spent_confirmed_satang"] + v["spent_predicted_satang"] for k, v in st.items()}
    try:
        new = cf.tradeoff_increase(alloc, spent, pocket_id, increase_satang)
    except ValueError as e:
        raise ApiError(400, "TRADEOFF_NOT_POSSIBLE", str(e)) from None
    payload = {"period_start": plan["period_start"].isoformat(), "period_end": plan["period_end"].isoformat(),
               "buffer_satang": plan["buffer_satang"], "allocations": new}
    assumptions = [{"kind": "tradeoff", "text": "Taken from other pockets in proportion to what is still unspent in each."}]
    return create_proposal(conn, owner_id, "budget_plan", payload, "agent", assumptions)


def spending_report(conn, owner_id, start: date, end: date) -> dict:
    from finassist.domain.ledger import spending_by_payee

    txns = load_txns(conn, owner_id)
    s = spending(txns, start, end)
    payees = sorted(spending_by_payee(txns, start, end).items(), key=lambda kv: -kv[1])[:10]
    return {"from": start, "to_exclusive": end, "total_satang": s.total_satang, "by_category": s.by_category,
            "unassigned_satang": s.unassigned_satang, "excluded_unresolved_count": s.excluded_count,
            "unlinked_refunds_satang": s.unlinked_refunds_satang, "top_payees": [{"payee_key": k, "total_satang": v} for k, v in payees],
            "note": "Detected/entered transactions only; not proof of completeness or settlement."}
