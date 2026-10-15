"""Business dates, periods and days-until-income (FI-5, FI-6, FI-9). Pure: stdlib only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Asia/Bangkok"


def require_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("naive datetime: all timestamps must carry an offset")
    return dt


def local_date(dt: datetime, tz: str = DEFAULT_TZ) -> date:
    """The user's calendar date for an instant."""
    return require_aware(dt).astimezone(ZoneInfo(tz)).date()


def end_of_local_day(d: date, tz: str = DEFAULT_TZ) -> datetime:
    """Last instant of local day `d`, as a UTC datetime (used for date-only observations, FI-9).

    Represented as start of next local day minus 1 microsecond.
    """
    start_next = datetime.combine(d + timedelta(days=1), time.min, tzinfo=ZoneInfo(tz))
    return (start_next - timedelta(microseconds=1)).astimezone(timezone.utc)


@dataclass(frozen=True)
class Period:
    """Half-open interval [start, end) in UTC."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        require_aware(self.start)
        require_aware(self.end)
        if not self.start < self.end:
            raise ValueError("period start must be before end")

    def contains(self, dt: datetime) -> bool:
        return self.start <= require_aware(dt) < self.end


def local_days_period(first: date, end_exclusive: date, tz: str = DEFAULT_TZ) -> Period:
    """Period covering local days first..end_exclusive-1."""
    z = ZoneInfo(tz)
    return Period(
        datetime.combine(first, time.min, tzinfo=z).astimezone(timezone.utc),
        datetime.combine(end_exclusive, time.min, tzinfo=z).astimezone(timezone.utc),
    )


class NextIncomeDatePassed(ValueError):
    """FI-6: the stored next income date is today or earlier; ask the user to update it."""


def days_until_income(today: date, next_income: date) -> int:
    """Days from today (inclusive) to next income date (exclusive)."""
    if next_income <= today:
        raise NextIncomeDatePassed(f"next income date {next_income} is not after {today}")
    return (next_income - today).days


def is_reflected_in_balance(
    occurred_at: datetime | None,
    occurred_date: date | None,
    balance_as_of: datetime,
    tz: str = DEFAULT_TZ,
) -> bool:
    """FI-8/FI-9: is a transaction already reflected in the balance observation?

    - With a timestamp: reflected iff occurred_at <= as_of.
    - Date only: reflected iff the local date <= the observation's local date
      (same-day date-only rows are assumed reflected; the UI must say so).
    """
    require_aware(balance_as_of)
    if occurred_at is not None:
        return require_aware(occurred_at) <= balance_as_of
    if occurred_date is None:
        raise ValueError("either occurred_at or occurred_date is required")
    return occurred_date <= local_date(balance_as_of, tz)
