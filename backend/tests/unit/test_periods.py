"""FI-5, FI-6, FI-8, FI-9. Asia/Bangkok is UTC+7 with no DST."""

from datetime import date, datetime, timezone

import pytest

from finassist.domain.periods import (
    NextIncomeDatePassed,
    Period,
    days_until_income,
    end_of_local_day,
    is_reflected_in_balance,
    local_date,
    local_days_period,
)

UTC = timezone.utc


def test_local_date_crosses_midnight():
    # 17:30Z = 00:30 ICT next day
    assert local_date(datetime(2026, 10, 15, 17, 30, tzinfo=UTC)) == date(2026, 10, 16)
    assert local_date(datetime(2026, 10, 15, 16, 59, tzinfo=UTC)) == date(2026, 10, 15)


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        local_date(datetime(2026, 10, 15, 12, 0))


def test_end_of_local_day():
    assert end_of_local_day(date(2026, 10, 15)) == datetime(2026, 10, 15, 16, 59, 59, 999_999, tzinfo=UTC)


def test_period_half_open():
    p = local_days_period(date(2026, 10, 1), date(2026, 11, 1))
    assert p.start == datetime(2026, 9, 30, 17, 0, tzinfo=UTC)
    assert p.end == datetime(2026, 10, 31, 17, 0, tzinfo=UTC)
    assert p.contains(p.start)
    assert not p.contains(p.end)


def test_period_rejects_empty():
    t = datetime(2026, 10, 1, tzinfo=UTC)
    with pytest.raises(ValueError):
        Period(t, t)


def test_days_until_income():
    assert days_until_income(date(2026, 10, 15), date(2026, 11, 1)) == 17
    assert days_until_income(date(2026, 10, 31), date(2026, 11, 1)) == 1
    with pytest.raises(NextIncomeDatePassed):
        days_until_income(date(2026, 11, 1), date(2026, 11, 1))


AS_OF = datetime(2026, 10, 15, 6, 0, tzinfo=UTC)  # 13:00 ICT


@pytest.mark.parametrize(
    "occurred_at, occurred_date, expected",
    [
        (datetime(2026, 10, 15, 5, 59, tzinfo=UTC), None, True),   # before anchor: already in balance
        (AS_OF, None, True),                                       # boundary is inclusive
        (datetime(2026, 10, 15, 6, 1, tzinfo=UTC), None, False),   # after anchor: affects balance
        (None, date(2026, 10, 15), True),                          # same-day date-only: assumed reflected (D6)
        (None, date(2026, 10, 14), True),
        (None, date(2026, 10, 16), False),
    ],
)
def test_is_reflected_in_balance(occurred_at, occurred_date, expected):
    assert is_reflected_in_balance(occurred_at, occurred_date, AS_OF) is expected


def test_reflected_requires_some_time():
    with pytest.raises(ValueError):
        is_reflected_in_balance(None, None, AS_OF)
