"""Synthetic characterization and desired safety regressions for multi-reference slips.

Strict xfails are OPEN production gaps, not passing security controls. No private
slips, model outputs or calls are used. See docs/design/14-reference-contract.md.
"""
from datetime import datetime, timedelta, timezone

import pytest

from finassist.domain.dedup import Candidate, decide, normalize_ref

T = datetime(2026, 10, 16, 5, 0, tzinfo=timezone.utc)


def candidate(ref, *, id="new", amount=12000, at=T):
    return Candidate(id, "transfer_out", amount, at, at.date().isoformat(), "synthetic shop", ref)


def test_current_same_payment_with_alternate_printed_field_is_treated_as_new():
    # Same synthetic payment: Transaction No. vs Transaction ID. The current
    # contract cannot tell that these are two fields from the same document.
    assert decide(candidate("CHANNEL987654321"), [candidate("BANK123456789", id="old")]).action == "new"


@pytest.mark.xfail(strict=True, reason="REF-GAP-1: single untyped reference cannot detect alternate fields of one payment")
def test_same_payment_alternate_field_must_not_silently_create_second_payment():
    decision = decide(candidate("CHANNEL987654321"), [candidate("BANK123456789", id="old")])
    assert decision.action in {"possible_duplicate", "same_payment"}


def test_current_equal_untyped_value_and_amount_merges_even_for_different_payments():
    # Same merchant/order identifier reused on distinct payments. The legacy
    # API has discarded the printed label, so this is treated as transaction ID.
    old = candidate("ORDER123456789", id="old")
    new = candidate("ORDER123456789", at=T + timedelta(minutes=10))
    assert decide(new, [old]).action == "same_payment"


@pytest.mark.xfail(strict=True, reason="REF-GAP-2: field type/issuer scope absent; non-unique identifier can auto-merge")
def test_reused_nontransaction_identifier_must_not_automatically_merge_payments():
    old = candidate("ORDER123456789", id="old")
    new = candidate("ORDER123456789", at=T + timedelta(minutes=10))
    assert decide(new, [old]).action != "same_payment"


@pytest.mark.parametrize("left,right", [
    ("BANK12O456789", "BANK120456789"),
    ("BANK12I456789", "BANK121456789"),
    ("BANK123456789", "BANK12345678"),
])
def test_ocr_confusables_and_missing_character_request_review_not_merge(left, right):
    assert normalize_ref(left) != normalize_ref(right)
    assert decide(candidate(left), [candidate(right, id="old")]).action == "possible_duplicate"


def test_near_reference_with_different_amount_does_not_merge():
    assert decide(candidate("BANK120456789", amount=12100), [candidate("BANK12O456789", id="old")]).action == "new"


def test_two_actual_payments_same_amount_with_distinct_refs_stay_distinct():
    assert decide(candidate("CHANNEL987654321", at=T + timedelta(minutes=10)),
                  [candidate("BANK123456789", id="old")]).action == "new"


def test_repeated_exact_reference_and_amount_retains_legacy_behavior():
    assert decide(candidate("BANK123456789"), [candidate("BANK123456789", id="old")]).action == "same_payment"
