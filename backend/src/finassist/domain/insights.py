"""Spending insights: history by month, recurring charges, bill changes, pace alerts, recommendations.
Pure. Every output says what evidence it used; nothing is inferred without at least the stated minimum data."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median

from .ledger import Txn, counts_for_totals

RECURRING_MIN_OCCURRENCES = 3
AMOUNT_TOLERANCE_BPS = 1_000  # ±10 %
CHANGE_THRESHOLD_BPS = 1_000  # flag a change of ≥10 %


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def months_back(today: date, n: int) -> list[str]:
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return out[::-1]


def monthly_history(txns: list[Txn], today: date, months: int = 3) -> dict:
    """Net spending per calendar month (current month included, partial) per category key."""
    keys = months_back(today, months)
    by_id = {t.id: t for t in txns}
    table: dict[str, dict[str, int]] = {k: defaultdict(int) for k in keys}
    for t in txns:
        if not counts_for_totals(t):
            continue
        mk = month_key(t.occurred_date)
        if mk not in table:
            continue
        if t.kind == "expense":
            table[mk][_cat(t)] += t.amount_satang
        elif t.kind == "refund" and t.refund_of and t.refund_of in by_id:
            table[mk][_cat(by_id[t.refund_of])] -= t.amount_satang
    complete = [k for k in keys if k != month_key(today)]
    cats = sorted({c for k in keys for c in table[k]})
    avg = {c: (sum(table[k].get(c, 0) for k in complete) // len(complete)) if complete else None for c in cats}
    return {"months": keys, "complete_months": complete, "by_month": {k: dict(v) for k, v in table.items()},
            "avg_complete_month": avg, "note": "Only detected/entered transactions; photos may not capture all spending."}


def _cat(t: Txn) -> str:
    return t.category_code if t.category_state != "unclassified" and t.category_code else "unassigned"


@dataclass(frozen=True)
class Recurring:
    payee_key: str
    occurrences: int
    typical_amount_satang: int
    cadence_days: int
    last_date: date
    next_expected: date
    last_amount_satang: int
    changed: bool
    change_bps: int


def _within(a: int, b: int, tol_bps: int) -> bool:
    return abs(a - b) * 10_000 <= tol_bps * max(a, b)


def recurring_charges(txns: list[Txn]) -> list[Recurring]:
    groups: dict[str, list[Txn]] = defaultdict(list)
    for t in txns:
        if t.kind == "expense" and counts_for_totals(t) and t.payee_key:
            groups[t.payee_key].append(t)
    out = []
    for pk, ts in groups.items():
        ts.sort(key=lambda t: t.occurred_date)
        if len(ts) < RECURRING_MIN_OCCURRENCES:
            continue
        gaps = [(b.occurred_date - a.occurred_date).days for a, b in zip(ts, ts[1:])]
        cadence = int(median(gaps))
        if not (6 <= cadence <= 8 or 26 <= cadence <= 35):
            continue
        if any(abs(g - cadence) > max(3, cadence // 5) for g in gaps):
            continue
        prev = [t.amount_satang for t in ts[:-1]]
        typical = int(median(prev))
        if sum(1 for a in prev if _within(a, typical, AMOUNT_TOLERANCE_BPS)) < len(prev) - 1:
            continue  # amounts too irregular to call it a recurring charge
        last = ts[-1]
        change = (last.amount_satang - typical) * 10_000 // typical
        out.append(Recurring(pk, len(ts), typical, cadence, last.occurred_date, last.occurred_date + timedelta(days=cadence),
                             last.amount_satang, abs(change) >= CHANGE_THRESHOLD_BPS, change))
    return sorted(out, key=lambda r: -r.typical_amount_satang)


@dataclass(frozen=True)
class BillChange:
    biller: str
    previous_satang: int
    latest_satang: int
    change_bps: int


def bill_changes(bills: list[tuple[str, date, int]]) -> list[BillChange]:
    """bills: (biller, due_date, amount). Compares the latest bill with the one before for the same biller."""
    by: dict[str, list[tuple[date, int]]] = defaultdict(list)
    for biller, due, amt in bills:
        by[biller.casefold().strip()].append((due, amt))
    out = []
    for b, rows in by.items():
        if len(rows) < 2:
            continue
        rows.sort()
        prev, last = rows[-2][1], rows[-1][1]
        ch = (last - prev) * 10_000 // prev
        if abs(ch) >= CHANGE_THRESHOLD_BPS:
            out.append(BillChange(b, prev, last, ch))
    return out


@dataclass(frozen=True)
class PaceAlert:
    pocket: str
    allocation_satang: int
    spent_satang: int
    elapsed_bps: int
    spent_bps: int
    status: str  # over | on_pace_to_exceed
    predicted_part_satang: int


def pace_alerts(pockets: list[dict], period_start: date, period_end: date, today: date) -> list[PaceAlert]:
    total_days = (period_end - period_start).days
    elapsed = min(total_days, max(1, (today - period_start).days + 1))
    elapsed_bps = elapsed * 10_000 // total_days
    out = []
    for p in pockets:
        if not p.get("pocket_id") or not p.get("allocation_satang"):
            continue
        spent = p["spent_confirmed_satang"] + p["spent_predicted_satang"]
        spent_bps = spent * 10_000 // p["allocation_satang"]
        if spent > p["allocation_satang"]:
            status = "over"
        elif spent_bps > elapsed_bps + 2_000 and spent_bps >= 5_000:
            status = "on_pace_to_exceed"
        else:
            continue
        out.append(PaceAlert(p["name"], p["allocation_satang"], spent, elapsed_bps, spent_bps, status, p["spent_predicted_satang"]))
    return out


@dataclass(frozen=True)
class Recommendation:
    category: str
    last_month_satang: int
    average_satang: int
    suggested_monthly_cut_satang: int
    estimated_savings_per_month_satang: int
    basis: str


def recommendations(history: dict, min_increase_bps: int = 1_500, min_amount_satang: int = 20_000) -> list[Recommendation]:
    """Suggest returning a category to its earlier average when the last complete month rose ≥15 %.
    Requires ≥2 complete months (one to compare, one+ for the average)."""
    comp = history["complete_months"]
    if len(comp) < 2:
        return []
    last, earlier = comp[-1], comp[:-1]
    out = []
    for cat in history["avg_complete_month"]:
        if cat in ("bills", "unassigned"):
            continue
        last_v = history["by_month"][last].get(cat, 0)
        avg_e = sum(history["by_month"][k].get(cat, 0) for k in earlier) // len(earlier)
        if avg_e <= 0 or last_v - avg_e < min_amount_satang:
            continue
        if (last_v - avg_e) * 10_000 < min_increase_bps * avg_e:
            continue
        cut = last_v - avg_e
        out.append(Recommendation(cat, last_v, avg_e, cut, cut, f"{last} vs average of {', '.join(earlier)}"))
    return sorted(out, key=lambda r: -r.estimated_savings_per_month_satang)
