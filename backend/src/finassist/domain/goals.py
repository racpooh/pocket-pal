"""Goal feasibility and alternatives (R6.*). Pure.

Contributions happen once per income date (one contribution per income event)
from the per-period surplus capacity supplied by the caller (derived from the
cash-flow engine), so goals and budgets share one model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .money import split_evenly


def income_dates(next_income: date, frequency: str, until_inclusive: date) -> list[date]:
    """Income dates from next_income up to and including `until`."""
    out: list[date] = []
    d = next_income
    while d <= until_inclusive:
        out.append(d)
        if frequency == "monthly":
            y, m = (d.year + (d.month // 12), d.month % 12 + 1)
            day = min(next_income.day, _days_in_month(y, m))
            d = date(y, m, day)
        elif frequency == "biweekly":
            d += timedelta(days=14)
        elif frequency == "weekly":
            d += timedelta(days=7)
        else:  # irregular: only the known next date counts
            break
    return out


# Deterministic period rule: 12 calendar months = 52 weeks = 26 two-week periods. Results are floored (conservative).
_EVENTS_PER_YEAR = {"monthly": 12, "biweekly": 26, "weekly": 52}


def monthly_to_per_event(amount_per_month_satang: int, frequency: str) -> int | None:
    """Convert a per-month amount to a per-income-event amount, or None when the frequency has no fixed rate
    (irregular income): callers must then say the conversion is unavailable instead of guessing."""
    per_year = _EVENTS_PER_YEAR.get(frequency)
    if per_year is None:
        return None
    return amount_per_month_satang * 12 // per_year


def _days_in_month(y: int, m: int) -> int:
    nxt = date(y + (m // 12), m % 12 + 1, 1)
    return (nxt - timedelta(days=1)).day


@dataclass(frozen=True)
class GoalFeasibility:
    remaining_satang: int
    contribution_events: int
    required_per_event_satang: int  # ceil
    capacity_per_event_satang: int
    feasible: bool
    progress_bps: int
    # alternatives (None when feasible)
    later_deadline: date | None
    smaller_target_satang: int | None
    extra_saving_needed_per_event_satang: int | None


def ceil_div(a: int, b: int) -> int:
    return -(-a // b)


def feasibility(
    target_satang: int,
    saved_satang: int,
    deadline: date,
    next_income: date,
    frequency: str,
    capacity_per_event_satang: int,
) -> GoalFeasibility:
    if target_satang <= 0 or saved_satang < 0 or capacity_per_event_satang < 0:
        raise ValueError("invalid goal inputs")
    remaining = max(0, target_satang - saved_satang)
    progress = min(10_000, saved_satang * 10_000 // target_satang)
    events = income_dates(next_income, frequency, deadline)
    n = len(events)
    if remaining == 0:
        return GoalFeasibility(0, n, 0, capacity_per_event_satang, True, progress, None, None, None)
    required = ceil_div(remaining, n) if n else remaining
    feasible = n > 0 and required <= capacity_per_event_satang
    later = smaller = extra = None
    if not feasible:
        if capacity_per_event_satang > 0:
            needed_events = ceil_div(remaining, capacity_per_event_satang)
            horizon = income_dates(next_income, frequency, next_income + timedelta(days=3660))
            later = horizon[needed_events - 1] if len(horizon) >= needed_events else None
        smaller = saved_satang + capacity_per_event_satang * n
        extra = (required - capacity_per_event_satang) if n else None
    return GoalFeasibility(remaining, n, required, capacity_per_event_satang, feasible, progress, later, smaller, extra)


def daily_amount_to_recover(over_satang: int, today: date, until_exclusive: date) -> tuple[int, int]:
    """Gamification-style 'save X per day until date' (R11 idea): ceil per day."""
    days = (until_exclusive - today).days
    if days <= 0:
        raise ValueError("date must be in the future")
    share, rem = split_evenly(over_satang, days)
    return (share + (1 if rem else 0)), days
