"""Single cash-flow waterfall for budgets, allowance, affordability (FI-23..FI-27). Pure.

Period: [today, next_income_date) in the user's local dates.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

from .allocation import BPS_TOTAL
from .money import split_evenly
from .periods import days_until_income

CALC_VERSION = "cashflow@0.1.0"


@dataclass(frozen=True)
class UnpaidBill:
    id: str
    amount_satang: int
    due_date: date
    essential_id: str | None = None  # bill that instantiates an essential template


@dataclass(frozen=True)
class Essential:
    id: str
    amount_satang: int
    next_due_date: date


@dataclass(frozen=True)
class SavingsCommitment:
    source_id: str  # goal id, or "savings_preference"
    amount_satang: int


@dataclass(frozen=True)
class Buffer:
    amount_satang: int = 0
    bps_of_income: int = 0  # alternative: % of next income; label states the base


@dataclass(frozen=True)
class CashflowInputs:
    today: date
    next_income_date: date
    next_income_satang: int
    available_balance_satang: int  # projected balance of spending accounts now
    unpaid_bills: tuple[UnpaidBill, ...] = ()
    essentials: tuple[Essential, ...] = ()
    savings: tuple[SavingsCommitment, ...] = ()
    buffer: Buffer = Buffer()
    hypothetical_expenses_satang: tuple[int, ...] = ()  # affordability scenarios only


@dataclass(frozen=True)
class Line:
    kind: str  # bill | essential | savings | buffer | hypothetical
    source_id: str
    amount_satang: int
    label: str


@dataclass(frozen=True)
class CashflowResult:
    version: str
    days: int
    available_balance_satang: int
    lines: tuple[Line, ...]
    reserved_satang: int
    discretionary_satang: int  # may be negative
    shortage_satang: int  # max(0, -discretionary)
    daily_allowance_satang: int
    daily_remainder_satang: int
    weekly_allowance_satang: int
    notes: tuple[str, ...] = field(default_factory=tuple)


def compute(inp: CashflowInputs) -> CashflowResult:
    days = days_until_income(inp.today, inp.next_income_date)  # raises NextIncomeDatePassed
    lines: list[Line] = []
    notes: list[str] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, source_id: str, amount: int, label: str) -> None:
        if (kind, source_id) in seen:
            raise ValueError(f"source {kind}:{source_id} reserved twice")  # FI-23
        seen.add((kind, source_id))
        if amount < 0:
            raise ValueError("line amounts must be >= 0")
        lines.append(Line(kind, source_id, amount, label))

    # 1. Unpaid bills due before next income (overdue included: still owed).
    covered_essentials: set[str] = set()
    for b in inp.unpaid_bills:
        if b.due_date < inp.next_income_date:
            add("bill", b.id, b.amount_satang, f"bill due {b.due_date.isoformat()}")
            if b.essential_id:
                covered_essentials.add(b.essential_id)

    # 2. Essentials due in the period that are not already represented by a bill.
    for e in inp.essentials:
        if inp.today <= e.next_due_date < inp.next_income_date:
            if e.id in covered_essentials:
                notes.append(f"essential {e.id} covered by its bill; not reserved twice")
                continue
            add("essential", e.id, e.amount_satang, f"essential due {e.next_due_date.isoformat()}")

    # 3. Savings: goal contributions / preference. A 'Savings' pocket is a view of this, not extra.
    for sc in inp.savings:
        add("savings", sc.source_id, sc.amount_satang, "savings this period")

    # 4. Buffer.
    buf = inp.buffer.amount_satang + inp.next_income_satang * inp.buffer.bps_of_income // BPS_TOTAL
    if buf:
        label = "buffer"
        if inp.buffer.bps_of_income:
            label += f" ({inp.buffer.bps_of_income / 100:.2f}% of next income + fixed)"
        add("buffer", "buffer", buf, label)

    # 5. Hypothetical purchases (affordability only; never persisted).
    for i, amt in enumerate(inp.hypothetical_expenses_satang):
        add("hypothetical", f"h{i}", amt, "what-if purchase")

    reserved = sum(line.amount_satang for line in lines)
    discretionary = inp.available_balance_satang - reserved
    assert reserved + discretionary == inp.available_balance_satang  # FI-24
    if discretionary > 0:
        daily, rem = split_evenly(discretionary, days)
    else:
        daily, rem = 0, 0
    weekly = daily * min(7, days)
    return CashflowResult(
        version=CALC_VERSION,
        days=days,
        available_balance_satang=inp.available_balance_satang,
        lines=tuple(lines),
        reserved_satang=reserved,
        discretionary_satang=discretionary,
        shortage_satang=max(0, -discretionary),
        daily_allowance_satang=daily,
        daily_remainder_satang=rem,
        weekly_allowance_satang=weekly,
        notes=tuple(notes),
    )


@dataclass(frozen=True)
class Affordability:
    amount_satang: int
    affordable: bool
    before: CashflowResult
    after: CashflowResult
    daily_allowance_delta_satang: int
    shortage_after_satang: int


def affordability(inp: CashflowInputs, amount_satang: int) -> Affordability:
    """FI-26: what-if; pure, no side effects. Affordable = no shortage after the purchase."""
    if amount_satang <= 0:
        raise ValueError("amount must be positive")
    before = compute(inp)
    after = compute(replace(inp, hypothetical_expenses_satang=inp.hypothetical_expenses_satang + (amount_satang,)))
    return Affordability(
        amount_satang=amount_satang,
        affordable=after.discretionary_satang >= 0,
        before=before,
        after=after,
        daily_allowance_delta_satang=after.daily_allowance_satang - before.daily_allowance_satang,
        shortage_after_satang=after.shortage_satang,
    )


def tradeoff_increase(allocations: dict[str, int], spent: dict[str, int], target: str, increase_satang: int) -> dict[str, int]:
    """R5.4: raise `target` by `increase` and take it from other pockets' *unspent* allocation,
    proportionally to what is left in each (largest remainder, input order tie-break).
    Returns the new allocations; total is conserved. Raises if others lack room."""
    if target not in allocations or increase_satang <= 0:
        raise ValueError("bad target or amount")
    room = {k: max(0, allocations[k] - spent.get(k, 0)) for k in allocations if k != target}
    total_room = sum(room.values())
    if total_room < increase_satang:
        raise ValueError(f"other pockets only have {total_room} satang unspent")
    keys = list(room)
    floors, rems = {}, []
    for i, k in enumerate(keys):
        num = increase_satang * room[k]
        floors[k] = num // total_room
        rems.append((-(num % total_room), i))
    left = increase_satang - sum(floors.values())
    for _, i in sorted(rems)[:left]:
        floors[keys[i]] += 1
    new = dict(allocations)
    new[target] += increase_satang
    for k in keys:
        new[k] -= floors[k]
        assert new[k] >= 0
    assert sum(new.values()) == sum(allocations.values())
    return new
