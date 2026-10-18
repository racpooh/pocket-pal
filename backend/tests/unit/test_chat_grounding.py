"""Chat grounding helpers (pure): named reporting periods, ranked category totals, monthly→per-income-event rule."""

from datetime import date

from finassist.domain.goals import monthly_to_per_event
from finassist.domain.ledger import SpendingSummary, ranked_categories
from finassist.domain.periods import reporting_periods


def test_periods_mid_month():
    p = reporting_periods(date(2026, 10, 15))
    assert p["today"] == (date(2026, 10, 15), date(2026, 10, 16))
    assert p["this_month_to_date"] == (date(2026, 10, 1), date(2026, 10, 16))
    assert p["last_month"] == (date(2026, 9, 1), date(2026, 10, 1))
    assert p["last_7_days"] == (date(2026, 10, 9), date(2026, 10, 16))
    assert p["last_30_days"] == (date(2026, 9, 16), date(2026, 10, 16))
    assert (p["last_30_days"][1] - p["last_30_days"][0]).days == 30


def test_periods_on_first_day_of_year_and_month_boundaries():
    p = reporting_periods(date(2027, 1, 1))
    assert p["this_month_to_date"] == (date(2027, 1, 1), date(2027, 1, 2))
    assert p["last_month"] == (date(2026, 12, 1), date(2027, 1, 1))
    p = reporting_periods(date(2028, 3, 1))  # leap year: last month is Feb with 29 days
    assert p["last_month"] == (date(2028, 2, 1), date(2028, 3, 1))
    assert p["last_30_days"][0] == date(2028, 2, 1)
    p = reporting_periods(date(2026, 12, 31))
    assert p["this_month_to_date"] == (date(2026, 12, 1), date(2027, 1, 1))
    assert p["last_month"] == (date(2026, 11, 1), date(2026, 12, 1))


def test_ranked_categories_keep_split_and_order_with_refund_and_ties():
    s = SpendingSummary(total_satang=0, by_category={
        "food": {"confirmed": 30_000, "predicted": 5_000},
        "shopping": {"confirmed": 0, "predicted": 35_000},   # tie with food at 350.00 → order by code
        "transport": {"confirmed": 12_000, "predicted": 0},
        "entertainment": {"confirmed": -2_000, "predicted": 0},  # linked refund larger than its expenses
    }, unassigned_satang=99_999, unlinked_refunds_satang=7_000)
    r = ranked_categories(s)
    assert [x["category"] for x in r] == ["food", "shopping", "transport", "entertainment"]
    assert r[0] == {"category": "food", "total_satang": 35_000, "confirmed_satang": 30_000, "predicted_satang": 5_000}
    assert r[1]["predicted_satang"] == 35_000 and r[1]["confirmed_satang"] == 0
    assert r[-1]["total_satang"] == -2_000
    assert all(x["category"] != "unassigned" for x in r)  # unassigned stays a separate field
    assert all(isinstance(x["total_satang"], int) for x in r)


def test_ranked_categories_empty():
    assert ranked_categories(SpendingSummary()) == []


def test_monthly_to_per_event_rule():
    assert monthly_to_per_event(100_000, "monthly") == 100_000
    assert monthly_to_per_event(100_000, "biweekly") == 46_153   # 100000*12/26 = 46153.8 → floor
    assert monthly_to_per_event(100_000, "weekly") == 23_076     # 100000*12/52 = 23076.9 → floor
    assert monthly_to_per_event(100_000, "irregular") is None
    assert monthly_to_per_event(0, "weekly") == 0
