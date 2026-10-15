"""FI-4, FI-16, FI-17. Expected values worked out by hand in the comments."""

import pytest

from finassist.domain.allocation import Share, allocate_bps, reallocate


def test_largest_remainder_exact_sum():
    # base 1,000.01 THB = 100001 satang; 33.33% / 33.33% / 33.34%
    # floors: 33330 (rem 3333), 33330 (rem 3333), 33340 (rem 3334); leftover 1 -> 'c'
    r = allocate_bps(100_001, [Share("a", 3333), Share("b", 3333), Share("c", 3334)], "discretionary_for_period")
    assert r.amounts == {"a": 33_330, "b": 33_330, "c": 33_341}
    assert r.unallocated_satang == 0
    assert sum(r.amounts.values()) + r.unallocated_satang == r.base_satang
    assert r.base_label == "discretionary_for_period"


def test_tie_break_is_input_order():
    r = allocate_bps(1, [Share("first", 5000), Share("second", 5000)], "x")
    assert r.amounts == {"first": 1, "second": 0}


def test_partial_percentages_leave_unallocated():
    r = allocate_bps(10_000, [Share("food", 5000)], "x")
    assert r.amounts == {"food": 5_000}
    assert r.unallocated_satang == 5_000


def test_zero_base():
    r = allocate_bps(0, [Share("a", 10_000)], "x")
    assert r.amounts == {"a": 0} and r.unallocated_satang == 0


@pytest.mark.parametrize(
    "base, shares, label",
    [
        (100, [Share("a", 6000), Share("b", 5000)], "x"),  # > 100%
        (100, [Share("a", -1)], "x"),
        (100, [Share("a", 10)], ""),  # missing base label
        (-1, [Share("a", 10)], "x"),
        (100, [Share("a", 10), Share("a", 20)], "x"),
    ],
)
def test_invalid_allocations(base, shares, label):
    with pytest.raises(ValueError):
        allocate_bps(base, shares, label)


def test_reallocate_conserves_total():
    before = {"food": 300_000, "shopping": 100_000, "transport": 50_000}
    after = reallocate(before, "food", "shopping", 50_000)
    assert after == {"food": 250_000, "shopping": 150_000, "transport": 50_000}
    assert sum(after.values()) == sum(before.values())
    assert before["food"] == 300_000  # input not mutated


@pytest.mark.parametrize(
    "src, dst, amt, exc",
    [("food", "food", 1, ValueError), ("food", "nope", 1, KeyError), ("food", "shopping", 0, ValueError),
     ("food", "shopping", 300_001, ValueError)],
)
def test_reallocate_rejects(src, dst, amt, exc):
    with pytest.raises(exc):
        reallocate({"food": 300_000, "shopping": 0}, src, dst, amt)
