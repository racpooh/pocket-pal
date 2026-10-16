"""Deterministic validation of model-extracted slip fields (docs/design/04 §2). Pure.

The model output is untrusted data. This module decides which fields are usable;
critical fields (amount, direction, payment status, occurred date) gate totals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .money import MoneyParseError, parse_thb

DOC_TYPES = ("transfer_out", "transfer_in", "receipt", "bill", "not_financial")
CRITICAL = ("amount", "direction", "payment_status", "occurred")

_THAI_MONTHS = {
    "ม.ค.": 1, "ก.พ.": 2, "มี.ค.": 3, "เม.ย.": 4, "พ.ค.": 5, "มิ.ย.": 6,
    "ก.ค.": 7, "ส.ค.": 8, "ก.ย.": 9, "ต.ค.": 10, "พ.ย.": 11, "ธ.ค.": 12,
    "มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4, "พฤษภาคม": 5, "มิถุนายน": 6,
    "กรกฎาคม": 7, "สิงหาคม": 8, "กันยายน": 9, "ตุลาคม": 10, "พฤศจิกายน": 11, "ธันวาคม": 12,
}
# English month names as printed by bank apps in English mode ("16 Oct 2026", "Oct 16, 2026"). Added after the
# real-slip r1 pilot (16 Oct 2026): 4/5 dates were read correctly by the model but this parser had no English months.
_EN_MONTHS = {m: i for i, names in enumerate(
    [("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",), ("jun", "june"),
     ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"),
     ("dec", "december")], start=1) for m in names}
_EN_MONTH_FIRST = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{2,4})\b")
_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
_THAI_DATE = re.compile(r"(\d{1,2})\s*(\S+?)\s*(\d{2,4})")
_NUMERIC_DATE = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b")
_TIME = re.compile(r"(\d{1,2})[:.](\d{2})(?::(\d{2}))?")


def _year(y: int) -> int:
    """Two/four-digit year in CE or Buddhist Era → CE."""
    if y < 100:
        y += 2500 if y >= 40 else 2000  # '69' → 2569 BE (Thai slips print BE short years)
    if y > 2400:
        y -= 543
    return y


def parse_thai_date(text: str) -> date:
    s = text.translate(_THAI_DIGITS).strip()
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        pass
    n = _NUMERIC_DATE.search(s)
    if n:
        d, mo, y = (int(g) for g in n.groups())
        return date(_year(y), mo, d)
    m = _THAI_DATE.search(s)
    mf = _EN_MONTH_FIRST.search(s)
    day_first_month = m and (m.group(2) in _THAI_MONTHS or m.group(2).rstrip(".,").lower() in _EN_MONTHS
                             or any(k.rstrip(".") == m.group(2).rstrip(".") for k in _THAI_MONTHS))
    if not day_first_month and mf and mf.group(1).lower() in _EN_MONTHS:  # "Oct 16, 2026" only if day-first fails
        mon, d, y = mf.groups()
        return date(_year(int(y)), _EN_MONTHS[mon.lower()], int(d))
    if not m:
        raise ValueError(f"unrecognised date {text!r}")
    d, mon, y = m.groups()
    month = _THAI_MONTHS.get(mon)
    if month is None:
        mon_clean = mon.rstrip(".")
        month = next((v for k, v in _THAI_MONTHS.items() if k.rstrip(".") == mon_clean), None)
    if month is None:
        month = _EN_MONTHS.get(mon.rstrip(".,").lower())
    if month is None and mon.isdigit():
        month = int(mon)
    if month is None:
        raise ValueError(f"unrecognised month {mon!r}")
    return date(_year(int(y)), month, int(d))


def parse_time(text: str | None) -> time | None:
    if not text:
        return None
    m = _TIME.search(text.translate(_THAI_DIGITS))
    if not m:
        return None
    h, mi, se = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    if h > 23 or mi > 59 or se > 59:
        return None
    return time(h, mi, se)


@dataclass
class Validated:
    doc_type: str | None
    kind: str | None  # expense | income (for slips/receipts); None for bills
    amount_satang: int | None
    occurred_date: date | None
    occurred_at: datetime | None
    payment_status: str | None  # completed | pending | failed | None
    payee_display: str | None
    bank_ref: str | None
    due_date: date | None
    field_states: dict[str, str] = field(default_factory=dict)  # ok | missing | conflicting | invalid
    problems: list[str] = field(default_factory=list)

    @property
    def critical_ok(self) -> bool:
        needed = ("amount", "occurred") if self.doc_type == "bill" else CRITICAL
        if self.field_states.get("readability") == "poor":
            return False  # model reported a poor image: never auto-import, ask the user to confirm
        return all(self.field_states.get(f) == "ok" for f in needed)


_STATUS_MAP = {"success": "completed", "completed": "completed", "pending": "pending", "failed": "failed",
               "scheduled": "pending", "unknown": None}


MAX_AGE = timedelta(days=400)  # older documents are allowed, but only after the user confirms the date


def validate(raw: dict, *, captured_at: datetime | None, scan_from: date | None, scan_to: date | None,
             tz: str = "Asia/Bangkok", max_future: timedelta = timedelta(hours=1),
             reference_at: datetime | None = None) -> Validated:
    """`reference_at` is "now" for plausibility checks (defaults to captured_at). A date more than MAX_AGE
    before it, or after it, is marked conflicting → review. Added after the 15 Oct real-model eval, where the
    model misread a Thai-digit year (๒๐๒๖ read as ๒๕๖๖ → 2023) and the record would otherwise auto-import."""
    """`raw` is the model's structured output (already JSON-schema shaped, still untrusted)."""
    fs: dict[str, str] = {}
    problems: list[str] = []

    doc_type = raw.get("doc_type")
    if doc_type not in DOC_TYPES:
        doc_type = None
        problems.append("doc_type")

    # amount (+ consistency if the model reports a second printed copy)
    amount = None
    amt_text = raw.get("amount_text")
    if not amt_text:
        fs["amount"] = "missing"
    else:
        try:
            amount = parse_thb(str(amt_text))
            fs["amount"] = "ok"
            second = raw.get("amount_text_second")
            if second:
                try:
                    if parse_thb(str(second)) != amount:
                        fs["amount"], amount = "conflicting", None
                except MoneyParseError:
                    fs["amount"], amount = "conflicting", None
        except MoneyParseError:
            fs["amount"] = "invalid"

    # direction
    kind = {"transfer_out": "expense", "receipt": "expense", "transfer_in": "income"}.get(doc_type or "")
    if doc_type == "bill":
        fs["direction"] = "ok"
    elif kind:
        fs["direction"] = "ok"
    else:
        fs["direction"] = "missing"

    # status
    status = None
    if doc_type in ("transfer_out", "transfer_in"):
        status = _STATUS_MAP.get(str(raw.get("status") or "unknown").lower())
        fs["payment_status"] = "ok" if status else "missing"
    elif doc_type == "receipt":
        status = "completed"  # a store receipt documents a completed sale; settlement unproven (R7.6)
        fs["payment_status"] = "ok"
    elif doc_type == "bill":
        fs["payment_status"] = "ok"

    # date/time
    occ_date = occ_at = None
    if raw.get("date_text"):
        try:
            occ_date = parse_thai_date(str(raw["date_text"]))
            t = parse_time(raw.get("time_text"))
            if t:
                occ_at = datetime.combine(occ_date, t, tzinfo=ZoneInfo(tz))
            fs["occurred"] = "ok"
        except ValueError:
            fs["occurred"] = "invalid"
    else:
        fs["occurred"] = "missing"
    if fs.get("occurred") == "ok" and doc_type != "bill":
        ref_at = reference_at or captured_at
        if ref_at and occ_date and not ((ref_at - MAX_AGE).date() <= occ_date <= (ref_at + max_future).date()):
            fs["occurred"] = "conflicting"
            problems.append("implausible_date")
        if captured_at and occ_at and occ_at > captured_at + max_future:
            fs["occurred"] = "conflicting"
            problems.append("occurred_after_capture")
        if (scan_from and occ_date < scan_from) or (scan_to and occ_date > scan_to):
            fs["occurred"] = "conflicting"
            problems.append("outside_scan_range")

    due = None
    if doc_type == "bill":
        try:
            due = parse_thai_date(str(raw["due_date_text"])) if raw.get("due_date_text") else None
        except ValueError:
            due = None
        fs["due_date"] = "ok" if due else "missing"
        if due is None:
            problems.append("due_date")

    payee = (raw.get("payee") or "").strip() or None
    fs["payee"] = "ok" if payee else "missing"
    ref = (raw.get("bank_ref") or "").strip() or None
    fs["bank_ref"] = "ok" if ref else "missing"
    readability = raw.get("readability")
    if readability == "poor":
        fs["readability"] = "poor"
        problems.append("poor_readability")
        if ref:
            # A misread reference could wrongly merge two payments; do not use it for dedup until confirmed.
            fs["bank_ref"] = "uncertain"
            ref = None
    qr_ref = raw.get("qr_ref")
    if qr_ref and ref and "".join(filter(str.isalnum, qr_ref.upper())) != "".join(filter(str.isalnum, ref.upper())):
        fs["bank_ref"] = "conflicting"
        problems.append("qr_ref_mismatch")
        ref = None

    return Validated(doc_type, kind, amount if fs["amount"] == "ok" else None, occ_date, occ_at, status,
                     payee, ref, due, fs, problems)
