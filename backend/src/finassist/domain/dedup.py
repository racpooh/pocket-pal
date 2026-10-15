"""Duplicate decisions (FI-28..FI-30, docs/design/02 §7). Pure: callers supply candidates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

RECEIPT_SLIP_WINDOW = timedelta(minutes=30)
PHASH_MAX_DISTANCE = 6  # not used for decisions (see decide() rule 4)


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


REF_MAX_EDIT_DISTANCE = 2  # a misread/missing digit or two


def ref_edit_distance(a: str, b: str) -> int:
    """Levenshtein distance (small strings only)."""
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def refs_similar(a: str | None, b: str | None) -> bool:
    if not a or not b or a == b or min(len(a), len(b)) < 8:
        return False  # short references carry too little signal for a "misread" judgement
    return abs(len(a) - len(b)) <= REF_MAX_EDIT_DISTANCE and ref_edit_distance(a, b) <= REF_MAX_EDIT_DISTANCE


def decide(new: Candidate, existing: list[Candidate], *, near_image_match_id: str | None = None) -> Decision:
    """Rules (revised after the CP1 review, finding #5):
    A reference read from an image is evidence, not identity. Only agreement merges automatically:
      1. same reference AND same amount            → same_payment (merge)
      2. same reference, different amount          → possible_duplicate (conflict → review)
      3. similar reference (≤2 edits, ≥8 chars) + same amount → possible_duplicate (likely a misread digit).
         Known false positive: two real payments with near-sequential refs and equal amounts → one review question.
      4. near-identical image                       → possible_duplicate, ONLY if the caller passes a match.
         The 64-bit dHash is NOT used by the import path: on templated bank slips, distinct payments hash to
         distance 0 (measured 15 Oct on the synthetic set), so image similarity cannot tell purchases apart.
      5. receipt + slip, same amount, close in time → receipt_evidence (confirm in review)
      6. a side without reference + same amount/day → possible_duplicate
      7. otherwise (e.g. clearly different refs)    → new  (two 10-baht waters stay two purchases)
    Nothing except rule 1 merges without the user.
    """
    ref = normalize_ref(new.bank_ref)
    if ref:
        for e in existing:
            if normalize_ref(e.bank_ref) == ref:
                if e.amount_satang == new.amount_satang:
                    return Decision("same_payment", e.id, "same bank reference and amount")
                return Decision("possible_duplicate", e.id, "same bank reference but a different amount")
        for e in existing:
            if e.amount_satang == new.amount_satang and refs_similar(ref, normalize_ref(e.bank_ref)):
                return Decision("possible_duplicate", e.id, "almost the same bank reference and the same amount (possible misread)")
    if near_image_match_id:
        return Decision("possible_duplicate", near_image_match_id, "very similar image")
    if new.doc_type == "receipt" or not ref:
        for e in existing:
            if e.amount_satang != new.amount_satang:
                continue
            pair = {new.doc_type, e.doc_type}
            if "receipt" in pair and pair & {"transfer_out"} and _close(new, e) and _payee_similar(new.payee_key, e.payee_key):
                return Decision("receipt_evidence", e.id, "receipt and slip look like one purchase")
    for e in existing:
        both_have_refs = ref is not None and normalize_ref(e.bank_ref) is not None
        if both_have_refs:
            continue  # handled above
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
