"""Money in integer satang (FI-1..FI-3). Pure: stdlib only.

1 THB = 100 satang. Amounts are positive ints; sign is carried by the
transaction kind, never by the amount.
"""

from __future__ import annotations

import re

SATANG_PER_BAHT = 100

# Upper bound for a single amount to catch extraction garbage (100M THB).
MAX_AMOUNT_SATANG = 100_000_000 * SATANG_PER_BAHT


class MoneyParseError(ValueError):
    """Raised when a string cannot be parsed as a THB amount."""


_CURRENCY_TOKENS = ("฿", "THB", "บาท", "Baht", "baht", "BAHT")
# Thai digits ๐-๙ are mapped to ASCII; any other non-ASCII digit is rejected.
_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
# ASCII digits with optional correctly-placed thousands separators, optional 1–2 decimals.
_AMOUNT_RE = re.compile(r"^(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.([0-9]{1,2}))?$")


def parse_thb(text: str) -> int:
    """Parse a THB amount string into satang.

    Accepts e.g. "1,234.5", "1234.50", "฿1,234.50", "1,234.50 บาท", "10".
    Rejects negatives, >2 decimals, misplaced separators, exponents, empty,
    zero, and values above MAX_AMOUNT_SATANG. Never uses float.
    """
    if not isinstance(text, str):
        raise MoneyParseError("amount must be a string")
    s = text.strip()
    for token in _CURRENCY_TOKENS:
        s = s.replace(token, "")
    s = s.replace(" ", "").replace(" ", "").translate(_THAI_DIGITS)
    if not s:
        raise MoneyParseError("empty amount")
    if s.startswith(("-", "+")) or s.startswith("("):
        raise MoneyParseError("signed amounts are not accepted; use the transaction kind")
    m = _AMOUNT_RE.match(s)
    if not m:
        raise MoneyParseError(f"not a valid THB amount: {text!r}")
    whole_str, _, frac_str = s.partition(".")
    whole = int(whole_str.replace(",", ""))
    frac = int(frac_str.ljust(2, "0")) if frac_str else 0
    satang = whole * SATANG_PER_BAHT + frac
    if satang <= 0:
        raise MoneyParseError("amount must be greater than zero")
    if satang > MAX_AMOUNT_SATANG:
        raise MoneyParseError("amount exceeds the configured maximum")
    return satang


def format_thb(satang: int) -> str:
    """Format satang as '1,234.50' (no currency symbol). Accepts negatives for display."""
    if not isinstance(satang, int) or isinstance(satang, bool):
        raise TypeError("satang must be int")
    sign = "-" if satang < 0 else ""
    whole, frac = divmod(abs(satang), SATANG_PER_BAHT)
    return f"{sign}{whole:,}.{frac:02d}"


def split_evenly(total_satang: int, parts: int) -> tuple[int, int]:
    """Floor-divide a total into `parts` equal shares (FI-3).

    Returns (share, remainder) with share * parts + remainder == total.
    Used e.g. for a daily allowance: the remainder is reported, not lost.
    """
    if parts <= 0:
        raise ValueError("parts must be positive")
    if total_satang < 0:
        # A shortage has no allowance; callers must handle negatives explicitly.
        raise ValueError("cannot split a negative amount")
    share, remainder = divmod(total_satang, parts)
    return share, remainder
