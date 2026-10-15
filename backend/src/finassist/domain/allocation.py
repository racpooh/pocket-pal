"""Percentage allocation in basis points with largest-remainder rounding (FI-4).

Pure: stdlib only. Every percentage carries the label of what it is a
percentage *of*, so the UI can state the base (R5.3).
"""

from __future__ import annotations

from dataclasses import dataclass

BPS_TOTAL = 10_000  # 100.00 %


@dataclass(frozen=True)
class Share:
    key: str  # pocket id/name; order of the input list is the tie-break order
    bps: int  # basis points, 0..10000


@dataclass(frozen=True)
class AllocationResult:
    base_label: str
    base_satang: int
    amounts: dict[str, int]
    unallocated_satang: int  # base - sum(amounts); > 0 only if bps sum < 10000


def allocate_bps(base_satang: int, shares: list[Share], base_label: str) -> AllocationResult:
    """Allocate `base_satang` by basis points; parts + unallocated == base exactly.

    - Sum of bps must be <= 10000. If it is < 10000 the rest is `unallocated`.
    - Each share is floor(base * bps / 10000); leftover satang (from flooring)
      are distributed one by one to the shares with the largest fractional
      remainders, ties broken by input order (deterministic).
    """
    if not base_label:
        raise ValueError("base_label is required (what is this a percentage of?)")
    if base_satang < 0:
        raise ValueError("base must be >= 0; a shortage is not allocatable")
    keys = [s.key for s in shares]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate share keys")
    for s in shares:
        if not (0 <= s.bps <= BPS_TOTAL):
            raise ValueError(f"bps out of range for {s.key}")
    total_bps = sum(s.bps for s in shares)
    if total_bps > BPS_TOTAL:
        raise ValueError("shares exceed 100%")

    allocated_target = base_satang * total_bps // BPS_TOTAL  # what the shares jointly get
    floors: list[int] = []
    remainders: list[tuple[int, int]] = []  # (-remainder numerator, index) for sorting
    for i, s in enumerate(shares):
        numerator = base_satang * s.bps
        floors.append(numerator // BPS_TOTAL)
        remainders.append((-(numerator % BPS_TOTAL), i))

    leftover = allocated_target - sum(floors)
    assert 0 <= leftover <= len(shares)
    for _, i in sorted(remainders)[:leftover]:
        floors[i] += 1

    amounts = {s.key: floors[i] for i, s in enumerate(shares)}
    unallocated = base_satang - sum(amounts.values())
    return AllocationResult(base_label, base_satang, amounts, unallocated)


def reallocate(allocations: dict[str, int], source: str, target: str, amount_satang: int) -> dict[str, int]:
    """Move an allocation between pockets (FI-17). Conserves the total; creates no transaction."""
    if source == target:
        raise ValueError("source and target must differ")
    if source not in allocations or target not in allocations:
        raise KeyError("unknown pocket")
    if amount_satang <= 0:
        raise ValueError("amount must be positive")
    if allocations[source] < amount_satang:
        raise ValueError("allocation cannot go below zero")
    result = dict(allocations)
    result[source] -= amount_satang
    result[target] += amount_satang
    assert sum(result.values()) == sum(allocations.values())
    return result
