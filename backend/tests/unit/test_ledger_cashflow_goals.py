"""CALC-* tests. Every expected number is computed by hand in the comments."""

from datetime import date, datetime, timezone

import pytest

from finassist.domain.cashflow import (
    Buffer, CashflowInputs, Essential, SavingsCommitment, UnpaidBill, affordability, compute, tradeoff_increase,
)
from finassist.domain.goals import feasibility, income_dates
from finassist.domain.ledger import (
    BalanceObservation, Txn, check_refunds, check_transfer_groups, projected_balance, spending,
)
from finassist.domain.periods import NextIncomeDatePassed

UTC = timezone.utc
AS_OF = datetime(2026, 10, 15, 6, 0, tzinfo=UTC)  # 13:00 ICT
D15, D16 = date(2026, 10, 15), date(2026, 10, 16)


def _ledger():
    return [
        Txn("t1", "A", "expense", 10_000, D15, datetime(2026, 10, 15, 5, 0, tzinfo=UTC), category_code="food", category_state="confirmed"),
        Txn("t2", "A", "expense", 12_000, D15, datetime(2026, 10, 15, 7, 0, tzinfo=UTC), category_code="shopping", category_state="predicted"),
        Txn("t3", "A", "income", 500_000, D16),
        Txn("t4", "A", "expense", 20_000, D15),  # date-only, same day as anchor → reflected (D6)
        Txn("t5", "A", "expense", 30_000, D16, payment_status="pending"),
        Txn("t6", "A", "transfer_out", 100_000, D16, transfer_group_id="g1"),
        Txn("t7", "B", "transfer_in", 100_000, D16, transfer_group_id="g1"),
        Txn("t8", "A", "refund", 2_000, D16, refund_of="t2"),
    ]


def test_projected_balance_anchor_rules():
    # 1,000,000 − t2 12,000 + t3 500,000 − t6 100,000 + t8 2,000 = 1,390,000
    # t1 (before anchor) and t4 (same-day date-only) are already reflected; t5 pending excluded; t7 other account.
    obs = BalanceObservation("A", 1_000_000, AS_OF)
    assert projected_balance(obs, _ledger()) == 1_390_000


def test_old_slips_do_not_reduce_balance_again():
    obs = BalanceObservation("A", 1_000_000, AS_OF)
    old = [Txn(f"o{i}", "A", "expense", 5_000, date(2026, 9, i + 1)) for i in range(20)]
    assert projected_balance(obs, old) == 1_000_000


def test_spending_attribution_and_exclusions():
    s = spending(_ledger(), date(2026, 10, 1), date(2026, 11, 1))
    # expenses 10,000 + 12,000 + 20,000, minus refund 2,000 on t2 → 40,000. Transfers not spending.
    assert s.total_satang == 40_000
    assert s.by_category == {"food": {"confirmed": 10_000, "predicted": 0}, "shopping": {"confirmed": 0, "predicted": 10_000}}
    assert s.unassigned_satang == 20_000
    assert s.excluded_count == 1  # t5 pending
    assert s.unlinked_refunds_satang == 0


def test_transfers_conserve_and_one_legged_group_is_flagged():
    assert check_transfer_groups(_ledger()) == []
    bad = _ledger() + [Txn("t9", "A", "transfer_out", 5_000, D16, transfer_group_id="g2")]
    assert check_transfer_groups(bad) == ["g2"]


def test_refund_cannot_exceed_source():
    over = _ledger() + [Txn("t10", "A", "refund", 10_001, D16, refund_of="t2")]  # 2,000 + 10,001 > 12,000
    assert check_refunds(over) == ["t2"]
    assert check_refunds(_ledger()) == []


def test_txn_rejects_float_and_zero():
    with pytest.raises(ValueError):
        Txn("x", "A", "expense", 0, D15)
    with pytest.raises(ValueError):
        Txn("x", "A", "expense", 10.5, D15)  # type: ignore[arg-type]


def _cf(**kw):
    base = dict(
        today=D15, next_income_date=date(2026, 11, 1), next_income_satang=2_000_000,
        available_balance_satang=1_500_000,
        unpaid_bills=(UnpaidBill("b_elec", 120_000, date(2026, 10, 25), essential_id="e_elec"),
                      UnpaidBill("b_net", 59_900, date(2026, 11, 5))),
        essentials=(Essential("e_elec", 120_000, date(2026, 10, 25)), Essential("e_rent", 500_000, date(2026, 10, 30)),
                    Essential("e_phone", 29_900, date(2026, 11, 2))),
        savings=(SavingsCommitment("goal_g1", 100_000),),
        buffer=Buffer(amount_satang=50_000),
    )
    base.update(kw)
    return CashflowInputs(**base)


def test_waterfall_reconciles_without_double_reservation():
    r = compute(_cf())
    # reserved: b_elec 120,000 (e_elec covered, not again) + e_rent 500,000 + savings 100,000 + buffer 50,000 = 770,000
    # b_net and e_phone fall after next income → not reserved
    assert r.reserved_satang == 770_000
    assert r.discretionary_satang == 730_000
    assert r.days == 17
    assert (r.daily_allowance_satang, r.daily_remainder_satang) == (42_941, 3)  # 42,941 × 17 = 729,997
    assert r.weekly_allowance_satang == 300_587
    assert sorted((ln.kind, ln.source_id) for ln in r.lines) == [
        ("bill", "b_elec"), ("buffer", "buffer"), ("essential", "e_rent"), ("savings", "goal_g1")]
    assert sum(ln.amount_satang for ln in r.lines) + r.discretionary_satang == r.available_balance_satang


def test_buffer_percentage_has_labelled_base():
    r = compute(_cf(buffer=Buffer(bps_of_income=500)))  # 5% of 2,000,000 = 100,000
    buf = [ln for ln in r.lines if ln.kind == "buffer"][0]
    assert buf.amount_satang == 100_000
    assert "of next income" in buf.label


def test_same_savings_source_twice_is_rejected():
    with pytest.raises(ValueError):
        compute(_cf(savings=(SavingsCommitment("goal_g1", 1), SavingsCommitment("goal_g1", 1))))


def test_shortage_and_affordability_have_no_side_effects():
    inp = _cf()
    a = affordability(inp, 800_000)
    assert not a.affordable
    assert a.shortage_after_satang == 70_000  # 730,000 − 800,000
    assert a.daily_allowance_delta_satang == -42_941
    assert inp.hypothetical_expenses_satang == ()  # input untouched
    assert compute(inp) == a.before
    assert affordability(inp, 730_000).affordable


def test_next_income_passed():
    with pytest.raises(NextIncomeDatePassed):
        compute(_cf(next_income_date=D15))


def test_tradeoff_takes_from_unspent_room_proportionally():
    alloc = {"food": 300_000, "shopping": 100_000, "transport": 100_000}
    spent = {"food": 100_000, "transport": 80_000}
    # room food 200,000, transport 20,000 (total 220,000); take 50,000:
    # food 45,454.5 → 45,454 (+1 largest remainder) = 45,455; transport 4,545
    new = tradeoff_increase(alloc, spent, "shopping", 50_000)
    assert new == {"food": 254_545, "shopping": 150_000, "transport": 95_455}
    with pytest.raises(ValueError):
        tradeoff_increase(alloc, spent, "shopping", 220_001)


def test_income_dates_month_end_clamp():
    assert income_dates(date(2027, 1, 31), "monthly", date(2027, 4, 30)) == [
        date(2027, 1, 31), date(2027, 2, 28), date(2027, 3, 31), date(2027, 4, 30)]
    assert income_dates(date(2026, 12, 25), "monthly", date(2027, 1, 25)) == [date(2026, 12, 25), date(2027, 1, 25)]


def test_goal_infeasible_alternatives():
    # remaining 2,500,000 over 5 monthly events (Nov–Mar) → 500,000 each; capacity 400,000
    f = feasibility(3_000_000, 500_000, date(2027, 3, 31), date(2026, 11, 1), "monthly", 400_000)
    assert (f.contribution_events, f.required_per_event_satang, f.feasible) == (5, 500_000, False)
    assert f.later_deadline == date(2027, 5, 1)  # ceil(2.5M / 400k) = 7 events
    assert f.smaller_target_satang == 2_500_000  # 500,000 + 5 × 400,000
    assert f.extra_saving_needed_per_event_satang == 100_000
    assert f.progress_bps == 1_666


def test_goal_feasible_and_done():
    assert feasibility(3_000_000, 500_000, date(2027, 3, 31), date(2026, 11, 1), "monthly", 500_000).feasible
    done = feasibility(100, 150, date(2027, 1, 1), date(2026, 11, 1), "monthly", 0)
    assert done.feasible and done.progress_bps == 10_000
