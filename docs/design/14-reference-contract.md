# 14 — Multiple printed references: contract and regression checkpoint

Status: design proposal + executable legacy characterization. No provider, HTTP, database, Android or production dedup change in this checkpoint. Claude owns Android UI integration. Codex owns this contract and its synthetic regressions. Existing R1/R2 freezes and private labels remain untouched.

## Problem and evidence boundary

The owner reports that R2-03 used Transaction No. versus Transaction ID, and R2-05 used a reference code versus a transaction number. These observations establish field-selection ambiguity; they do not establish interchangeability, uniqueness or bank-wide semantics. The R2 exact-match baseline stays unchanged. A revised adjudication must record printed label AND value, not retrospectively count every value as correct.

The production Candidate only has bank_ref. The worker queries owner-scoped rows whose reference matches exactly OR whose date is within one day. Consequently:

- Different fields from one payment can become `new` if both references exist and differ by more than two edits (REF-GAP-1).
- Equal values from different namespaces, or reused order/merchant identifiers, can auto-merge at equal amounts (REF-GAP-2). Schema ambiguity makes this possible even if OCR transcribed every character correctly.
- Similar-reference review requires equal amounts, references at least eight characters long, edit distance at most two, and candidate retrieval. It is not a general guarantee against duplicates.

Tests use invented identifiers only. Strict xfails encode desired behavior the current contract cannot provide. They are open findings, not accepted controls or a green release gate. Passing characterization tests prove the limitation exists; they do not approve it.

## Proposed extraction contract (not active)

Add optional `references` in a NEW schema/prompt version after review:

```json
{
  "references": [
    {"label_text": "Transaction No.", "value_text": "SYNTHETIC-A123"},
    {"label_text": "Transaction ID", "value_text": "SYNTHETIC-B456"}
  ]
}
```

Copy all legible transaction/reference fields, preserving printed labels, case and punctuation. Do not infer equivalence. Do not collect account numbers, card numbers, merchant IDs or biller IDs as transaction references. Uncertain values are null; an absent/unknown printed label is null. Proposed bounds: eight entries, label <=128 characters, value <=256 characters, no extra properties. Text from images remains untrusted data.

The model must NOT decide which ID is authoritative, unique, verified, or safe to merge. A deterministic versioned mapping, backed by bank/template documentation or adjudicated examples, may assign a namespace and role. A bank logo alone is not verified provenance. No bank-specific mapping is claimed by this proposal.

## Storage and matching proposal

Store per-upload reference evidence with owner_id, upload_id, printed label/value, source (`model`, `user_transcription`, or `verified_provider`), and mapping version. Derive namespace/role only from an approved mapping; otherwise `unknown`. Preserve raw value separately from any comparison key. Human transcription is not provider verification. Retain tenant isolation, deletion behavior, and audit provenance for every new row.

- Unknown namespace/role: no reference-only automatic merge. Matching amount/payee/time may nominate a review candidate, never prove identity.
- Same approved transaction namespace and matching value: may nominate a strong candidate, but amount/direction/status conflicts must go to review. Automatic merge policy requires separately reviewed uniqueness evidence; not enabled here.
- Multiple references that link to different transactions: review conflict, never pick the first match.
- Nontransaction identifiers (merchant, account, order) cannot independently identify a payment.
- O/0 and I/1 similarity is a review signal only. Do not canonicalize these characters into equality. Case/punctuation normalization also needs namespace-specific policy; the legacy uppercase/alphanumeric rule is not universal proof.
- Do not replace the existing rule with amount+date equality: two real same-value purchases must remain possible. Missing timestamps, repeated purchases and broad date windows need explicit ambiguity handling.

The future worker query must retrieve candidates using same-namespace references and appropriate temporal context. Its bounds and false-positive cost must be tested in the DB pipeline; domain tests alone cannot prove candidate retrieval or ledger safety.

## Backwards-compatible integration plan

1. Keep the existing `bank_ref` response and endpoints during UI slice 1. Do not present it as verified identity. No Android work is required for this checkpoint.
2. Review schema/mapping/merge policy before activating extraction changes. A new prompt version invalidates future freeze configurations; never overwrite previous runs.
3. Persist reference arrays in a new migration and carry them through validation, review, correction and deletion. Legacy references remain unknown-type; do not silently backfill a namespace.
4. Add server-derived review details additively. Resolve must retain owner checks, candidate validation and idempotency semantics. Multi-reference UI can follow slice 1.
5. Add pipeline tests: alternate-field re-upload, same-value distinct payments, cross-namespace collision, contradictory multi-reference matches, unreadable fields, tenant isolation, delete/revoke, and candidate-window boundaries. Record both false negatives and review burden.

## Evaluation

Keep separate measures for value transcription under the correct printed label, field selection/coverage, namespace mapping, and end-to-end ledger outcomes. Preserve exact matching as baseline. Confusable-character diagnostics are supplementary, not corrected accuracy. Owner-adjudicated label revisions must have provenance and must not be represented as blind holdouts. No new paid model calls are needed to test these synthetic cases.

## Checkpoint acceptance

This checkpoint completes the contract proposal and reproducible regression coverage, NOT production remediation. REF-GAP-1 and REF-GAP-2 remain open until a reviewed implementation makes their tests pass without xfail and pipeline tests prove ledger outcomes. UI integration may proceed independently, but do not claim general duplicate safety or perfect OCR from the five-image pilot.

## Recorded verification

Evidence: `evidence/runs/20261016T122231Z-reference-contract-regressions/`. Focused tests: **57 passed, 2 strict xfailed** (open findings). With `--runxfail`, the new suite reports **2 failed, 8 passed**, demonstrating both gaps in the current implementation. The original failing output is retained. No DB, provider, Android build or paid API call was run. Read-only secondary review confirmed the single-reference and candidate-window limitations; it also noted the worker maps all nonmanual candidates to transfer_out, which must be addressed when typed matching is implemented.
