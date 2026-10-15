from datetime import date

from finassist.domain.insights import bill_changes, monthly_history, pace_alerts, recommendations, recurring_charges
from finassist.domain.ledger import Txn


def _e(i, d, amt, cat="food", payee=None, state="confirmed", **kw):
    return Txn(f"t{i}", "A", "expense", amt, d, category_code=cat if state != "unclassified" else None,
               category_state=state, payee_key=payee, **kw)


TODAY = date(2026, 10, 15)


def test_monthly_history_and_recommendation():
    tx = [_e(1, date(2026, 8, 5), 300_000), _e(2, date(2026, 9, 5), 420_000),  # food: Aug 3,000 → Sep 4,200
          _e(3, date(2026, 8, 6), 100_000, "shopping"), _e(4, date(2026, 9, 6), 105_000, "shopping"),
          _e(5, date(2026, 10, 2), 50_000), _e(6, date(2026, 9, 9), 9_999, state="unclassified"),
          _e(7, date(2026, 9, 10), 77_777, payment_status="pending")]
    h = monthly_history(tx, TODAY, months=3)
    assert h["months"] == ["2026-08", "2026-09", "2026-10"] and h["complete_months"] == ["2026-08", "2026-09"]
    assert h["by_month"]["2026-09"] == {"food": 420_000, "shopping": 105_000, "unassigned": 9_999}  # pending excluded
    assert h["avg_complete_month"]["food"] == 360_000
    recs = recommendations(h)
    assert len(recs) == 1  # shopping +5 % is below the 15 % threshold
    r = recs[0]
    assert (r.category, r.last_month_satang, r.average_satang, r.estimated_savings_per_month_satang) == ("food", 420_000, 300_000, 120_000)


def test_no_recommendation_without_two_complete_months():
    h = monthly_history([_e(1, date(2026, 9, 5), 420_000)], TODAY, months=2)
    assert recommendations(h) == []


def test_recurring_monthly_with_change():
    tx = [_e(i, d, a, "bills", "demo stream") for i, (d, a) in enumerate(
        [(date(2026, 6, 1), 41_900), (date(2026, 7, 1), 41_900), (date(2026, 8, 1), 41_900), (date(2026, 9, 1), 49_900)])]
    r = recurring_charges(tx)
    assert len(r) == 1
    rc = r[0]
    assert (rc.occurrences, rc.typical_amount_satang, rc.cadence_days, rc.next_expected) == (4, 41_900, 31, date(2026, 10, 2))
    assert rc.changed and rc.change_bps == 1_909  # (49,900 − 41,900) / 41,900 = 19.09 %


def test_irregular_payee_is_not_recurring():
    tx = [_e(i, d, 1_000, payee="ร้านป้าสมาน") for i, d in enumerate([date(2026, 9, 1), date(2026, 9, 3), date(2026, 9, 20), date(2026, 10, 1)])]
    assert recurring_charges(tx) == []
    assert recurring_charges(tx[:2]) == []  # too few occurrences


def test_bill_changes():
    ch = bill_changes([("Demo Power", date(2026, 9, 25), 100_000), ("Demo Power", date(2026, 10, 25), 125_000),
                       ("Demo Water", date(2026, 9, 25), 20_000), ("Demo Water", date(2026, 10, 25), 21_000)])
    assert len(ch) == 1 and ch[0].change_bps == 2_500


def test_pace_alerts():
    pockets = [
        {"pocket_id": "f", "name": "Food", "allocation_satang": 100_000, "spent_confirmed_satang": 70_000, "spent_predicted_satang": 10_000},
        {"pocket_id": "s", "name": "Shopping", "allocation_satang": 100_000, "spent_confirmed_satang": 110_000, "spent_predicted_satang": 0},
        {"pocket_id": "t", "name": "Transport", "allocation_satang": 100_000, "spent_confirmed_satang": 30_000, "spent_predicted_satang": 0},
        {"pocket_id": None, "name": "(unassigned)", "allocation_satang": None},
    ]
    # period 1–31 Oct, today 15 Oct → elapsed 15/30 = 50 %
    a = pace_alerts(pockets, date(2026, 10, 1), date(2026, 10, 31), date(2026, 10, 15))
    assert [(x.pocket, x.status) for x in a] == [("Food", "on_pace_to_exceed"), ("Shopping", "over")]
    assert a[0].predicted_part_satang == 10_000
