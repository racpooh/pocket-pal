"""Payee normalisation and category suggestion (docs/design/04 §1 Q4/Q5, §3). Pure.

No model here: the LLM hint is handled outside and never becomes `predicted`.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

# Thresholds are placeholders until tuned on the dev split (docs/design/06 §4).
N_MIN = 2
P_MIN_BPS = 8_000  # 80 %

# Prefixes removed only at the start of the name; suffixes only as whole tokens.
_TH_PREFIXES = ("นางสาว", "น.ส.", "นาย", "นาง", "ด.ช.", "ด.ญ.", "บจก.", "หจก.", "บริษัท")
_LATIN_PREFIX = re.compile(r"^(?:mr|mrs|ms|miss|mister)\.?\s+")
_SUFFIXES = re.compile(r"(?:\bco\.?\s*,?\s*ltd\.?|\bltd\.?|\bplc\.?|จำกัด\s*\(มหาชน\)|จำกัด)\s*$")
# Thai account display format xxx-x-xxxxx-x with masking (x, *, •) and some visible digits
_MASKED_ACCOUNT = re.compile(r"(?<![0-9a-z])[x\*•\d]{3}-[x\*•\d]-[x\*•\d]{4,5}-[x\*•\d](?![0-9a-z])", re.I)
_NON_WORD = re.compile(r"[^0-9a-z฀-๿]+")

# Invented-safe generic patterns for payment intermediaries; curate with real samples later.
INTERMEDIARY_PATTERNS = [
    re.compile(p) for p in (r"\bpay\b", r"payment", r"wallet", r"merchant", r"gateway", r"qr\s*shop", r"kshop", r"ksher", r"2c2p", r"omise", r"gb\s*prime")
]


def normalize_payee(display: str | None) -> str | None:
    if not display:
        return None
    s = unicodedata.normalize("NFC", display).casefold()
    s = _MASKED_ACCOUNT.sub(" ", s)
    s = s.strip()
    for pre in _TH_PREFIXES:
        # Dotted abbreviations are unambiguous; bare words (นาย/นาง/บริษัท) need a following space,
        # otherwise "นางฟ้า คาเฟ่" would lose "นาง".
        if s.startswith(pre) and (pre.endswith(".") or s[len(pre):len(pre) + 1].isspace()):
            s = s[len(pre):].lstrip()
            break
    s = _LATIN_PREFIX.sub("", s)
    s = _SUFFIXES.sub("", s.strip())
    s = _NON_WORD.sub(" ", s)
    s = " ".join(s.split())
    return s or None


def is_intermediary(display: str | None) -> bool:
    if not display:
        return False
    s = display.casefold()
    return any(p.search(s) for p in INTERMEDIARY_PATTERNS)


@dataclass(frozen=True)
class Suggestion:
    category_code: str | None
    state: str  # predicted | unclassified
    source: str | None  # user_default | history | seed | None
    reason: str


def suggest(
    payee_key: str | None,
    *,
    user_default: str | None,
    confirmed_history: list[str],
    seed: dict[str, str],
    intermediary: bool,
) -> Suggestion:
    """Evidence order: user default > confirmed history > seed dictionary > unclassified."""
    if user_default:
        return Suggestion(user_default, "predicted", "user_default", "you set a default for this payee")
    if intermediary:
        # Purchases through an aggregator vary; only an explicit user default applies.
        return Suggestion(None, "unclassified", None, "payment intermediary: purpose unknown")
    if payee_key and len(confirmed_history) >= N_MIN:
        code, count = Counter(confirmed_history).most_common(1)[0]
        if count * 10_000 >= P_MIN_BPS * len(confirmed_history):
            return Suggestion(code, "predicted", "history", f"{count} of {len(confirmed_history)} past confirmations")
    if payee_key and payee_key in seed:
        return Suggestion(seed[payee_key], "predicted", "seed", "known merchant")
    return Suggestion(None, "unclassified", None, "not enough evidence")
