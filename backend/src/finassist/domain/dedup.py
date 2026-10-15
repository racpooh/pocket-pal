"""Duplicate decisions (FI-28..FI-30, docs/design/02 §7). Pure: callers supply candidates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

RECEIPT_SLIP_WINDOW = timedelta(minutes=30)
PHASH_MAX_DISTANCE = 6  # placeholder; tune on dev set


@dataclass(frozen=True)
class Candidate:
    id: str
    doc_type: str  # transfer_out | transfer_in | receipt | manual
    amount_satang: int
    occurred_at: datetime | None
    occurred_date_iso: str
    payee_key: str | None
    bank_ref: str | None


@dataclass(frozen=True)
class Decision:
    action: str  # new | same_payment | possible_duplicate | receipt_evidence
    match_id: str | None
    reason: str


def normalize_ref(ref: str | None) -> str | None:
    if not ref:
        return None
    s = "".join(ch for ch in ref.upper() if ch.isalnum())
    return s or None


def hamming64(a: int, b: int) -> int:
    return bin((a ^ b) & ((1 << 64) - 1)).count("1")


def _payee_similar(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return a == b or a in b or b in a


def decide(new: Candidate, existing: list[Candidate], *, near_image_match_id: str | None = None) -> Decision:
    ref = normalize_ref(new.bank_ref)
    # 1. Same bank reference = same payment.
    if ref:
        for e in existing:
            if normalize_ref(e.bank_ref) == ref:
                return Decision("same_payment", e.id, "same bank reference")
    # 2. Different references are never duplicates (two 10-baht waters are two purchases).
    # 3. Receipt (no ref) vs slip with equal amount, similar payee, close in time.
    if new.doc_type == "receipt" or not ref:
        for e in existing:
            if e.amount_satang != new.amount_satang:
                continue
            pair = {new.doc_type, e.doc_type}
            if "receipt" in pair and pair & {"transfer_out"} and _close(new, e) and _payee_similar(new.payee_key, e.payee_key):
                return Decision("receipt_evidence", e.id, "receipt and slip look like one purchase")
    # 4. Near-identical image without readable ref → ask.
    if near_image_match_id and not ref:
        return Decision("possible_duplicate", near_image_match_id, "very similar image")
    # 5. When at least one side has no bank reference (manual entry, receipt-less slip),
    #    same amount + same day + compatible payee → ask (client resends with confirm_distinct).
    for e in existing:
        both_have_refs = ref is not None and normalize_ref(e.bank_ref) is not None
        if both_have_refs:
            continue  # handled by rule 1/2
        if (
            e.amount_satang == new.amount_satang
            and e.occurred_date_iso == new.occurred_date_iso
            and (_payee_similar(new.payee_key, e.payee_key) or new.payee_key is None or e.payee_key is None)
        ):
            return Decision("possible_duplicate", e.id, "same amount and day as an existing record without a shared reference")
    return Decision("new", None, "no matching record")


def _close(a: Candidate, b: Candidate) -> bool:
    if a.occurred_at and b.occurred_at:
        return abs(a.occurred_at - b.occurred_at) <= RECEIPT_SLIP_WINDOW
    return a.occurred_date_iso == b.occurred_date_iso
