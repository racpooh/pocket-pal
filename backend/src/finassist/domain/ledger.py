"""Ledger semantics: what counts, balance projection, spending (FI-7..FI-18). Pure."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

from .periods import is_reflected_in_balance

KINDS = ("expense", "income", "refund", "transfer_out", "transfer_in")
_SIGN = {"expense": -1, "income": +1, "refund": +1, "transfer_out": -1, "transfer_in": +1}


@dataclass(frozen=True)
class Txn:
    id: str
    account_id: str
    kind: str
    amount_satang: int
    occurred_date: date
    occurred_at: datetime | None = None
    payment_status: str = "completed"  # completed | pending | failed | unknown
    amount_state: str = "confirmed"  # confirmed | uncertain
    direction_state: str = "confirmed"
    category_code: str | None = None
    category_state: str = "unclassified"  # unclassified | predicted | confirmed
    refund_of: str | None = None
    transfer_group_id: str | None = None
    payee_key: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown kind {self.kind}")
        if not isinstance(self.amount_satang, int) or self.amount_satang <= 0:
            raise ValueError("amount_satang must be a positive int")
        if self.refund_of is not None and self.kind != "refund":
            raise ValueError("refund_of only valid on refunds")
        if self.transfer_group_id is not None and self.kind not in ("transfer_out", "transfer_in"):
            raise ValueError("transfer_group_id only valid on transfers")


def counts_for_totals(t: Txn) -> bool:
    """FI-11: only fully resolved, completed rows affect balances and totals."""
    return (
        t.payment_status == "completed"
        and t.amount_state == "confirmed"
        and t.direction_state == "confirmed"
    )


def signed_effect(t: Txn) -> int:
    return _SIGN[t.kind] * t.amount_satang


@dataclass(frozen=True)
class BalanceObservation:
    account_id: str
    amount_satang: int
    as_of: datetime


def projected_balance(obs: BalanceObservation, txns: list[Txn], tz: str = "Asia/Bangkok") -> int:
    """FI-7/FI-8/FI-9: observation + effects of counted rows on that account after the anchor."""
    total = obs.amount_satang
    for t in txns:
        if t.account_id != obs.account_id or not counts_for_totals(t):
            continue
        if is_reflected_in_balance(t.occurred_at, None if t.occurred_at else t.occurred_date, obs.as_of, tz):
            continue
        total += signed_effect(t)
    return total


def check_transfer_groups(txns: list[Txn]) -> list[str]:
    """FI-13: each group with two tracked legs nets to zero. Returns problem group ids."""
    groups: dict[str, list[Txn]] = defaultdict(list)
    for t in txns:
        if t.transfer_group_id:
            groups[t.transfer_group_id].append(t)
    bad = []
    for gid, legs in groups.items():
        kinds = sorted(leg.kind for leg in legs)
        if kinds != ["transfer_in", "transfer_out"] or sum(signed_effect(leg) for leg in legs) != 0:
            bad.append(gid)
    return bad


def check_refunds(txns: list[Txn]) -> list[str]:
    """FI-14: sum of refunds per source <= source amount; refunds must point at an expense."""
    by_id = {t.id: t for t in txns}
    refunded: dict[str, int] = defaultdict(int)
    bad = []
    for t in txns:
        if t.kind == "refund" and t.refund_of:
            src = by_id.get(t.refund_of)
            if src is None or src.kind != "expense":
                bad.append(t.id)
                continue
            refunded[src.id] += t.amount_satang
    for sid, amt in refunded.items():
        if amt > by_id[sid].amount_satang:
            bad.append(sid)
    return bad


@dataclass
class SpendingSummary:
    """Net spending in a date range (FI-12, FI-18). Refunds net against their source's category."""

    total_satang: int = 0
    by_category: dict[str, dict[str, int]] = field(default_factory=dict)  # code -> {confirmed, predicted}
    unassigned_satang: int = 0
    excluded_count: int = 0  # unresolved rows, visible but not counted
    unlinked_refunds_satang: int = 0


def spending(txns: list[Txn], start: date, end_exclusive: date) -> SpendingSummary:
    by_id = {t.id: t for t in txns}
    s = SpendingSummary()

    def bucket(t: Txn, amount: int) -> None:
        s.total_satang += amount
        if t.category_state == "unclassified" or t.category_code is None:
            s.unassigned_satang += amount
            return
        b = s.by_category.setdefault(t.category_code, {"confirmed": 0, "predicted": 0})
        b["confirmed" if t.category_state == "confirmed" else "predicted"] += amount

    for t in txns:
        if not (start <= t.occurred_date < end_exclusive):
            continue
        if not counts_for_totals(t):
            if t.kind in ("expense", "refund"):
                s.excluded_count += 1
            continue
        if t.kind == "expense":
            bucket(t, t.amount_satang)
        elif t.kind == "refund":
            src = by_id.get(t.refund_of) if t.refund_of else None
            if src is not None and src.kind == "expense":
                bucket(src, -t.amount_satang)  # attributed to the source's category
            else:
                s.unlinked_refunds_satang += t.amount_satang  # flagged; not netted silently
    return s


def spending_by_payee(txns: list[Txn], start: date, end_exclusive: date) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for t in txns:
        if t.kind == "expense" and counts_for_totals(t) and start <= t.occurred_date < end_exclusive:
            out[t.payee_key or "(unknown)"] += t.amount_satang
    return dict(out)
