# 04 — Import, extraction and classification

Status: **Proposed**, with explicit disagreements with Codex's initial hypotheses. Thresholds are placeholders until measured on a development split.

## 0. The problem, stated narrowly

A Thai transfer slip (e.g., MAKE by KBank, payee "ร้านป้าสมาน", ฿10) proves at most: an amount, a time, a payee display name, a bank reference, and that the app showed success. It does **not** state what was bought ("water" was the user's statement). "AWN SPECIAL SHOP ฿120 = game shop" is likewise user knowledge. So:

- *Extraction* can be evaluated against the image.
- *Purpose/category* can only be suggested from evidence outside the image (the user's past confirmations, known merchant brands, bill type) and must be labelled as such.

The goal is less manual work for the user **without** pretending to know the purpose.

## 1. Answers to the eight challenge questions

### Q1 Is the four-stage pipeline too complex for the time?
As four pipeline stages/services, yes. As four **fields** on the data model, no — they are cheap and prevent a later migration:

| Field | Source | Stored on |
|---|---|---|
| extracted fields (amount, time, payee, ref, doc type, status) | one VLM call + deterministic validation | `extraction` |
| `payee_key` (normalised payee identity) | deterministic normaliser (no ML) | `txn` |
| `category` + `category_state` + `category_source` | suggestion function | `txn` |
| pocket | derived from category mapping (D5) | view |

"Merchant type" as a separately predicted field is dropped for v1: it adds an inference with no user-visible use beyond category. Kept: an `is_intermediary` flag on known payment aggregators.

### Q2 Separate OCR + classifier vs a vision-language model with structured extraction?
Recommendation for the 2-day build: **one VLM call with a strict JSON schema, then deterministic validation**; no separate OCR engine.

| | OCR engine (Tesseract/PaddleOCR) + bank-specific parsers | VLM structured extraction |
|---|---|---|
| Build time | High: Thai OCR quality varies; one parser per bank layout | Low: one schema, one prompt |
| Privacy | Can run locally | Image goes to the provider → must be in the consent text (D2/D7) |
| Failure mode | Missed/garbled characters, visible | Plausible but wrong values (hallucination) → needs validation and cross-checks |
| Cost/latency | ~free, fast | per-image cost and seconds of latency (measure) |
| Evaluation | Field accuracy | Field accuracy (same harness) |

Mitigations for the VLM failure mode, all deterministic: amount must parse under FI-2; amount appears consistently if printed twice; date within scan range and ≤ capture time + tolerance; bank reference format check per bank when known; optional local QR decode (hypothesis H1 below) compared with the extracted reference; any conflict → field marked `conflicting` → review.

Hypothesis H1 (unverified): Thai bank slips carry a QR code used for slip verification that encodes a transaction reference but not the amount. If true on our samples, local QR decoding gives a deterministic dedup key and a cross-check without any model. Verify on redacted samples before relying on it. Settlement still cannot be proven without a bank verification API (out of scope); the record says "slip shows success", not "settled".

### Q3 Additional model, or rules + confirmed history + LLM?
No additional trained model now. Reasons: no labelled dataset beyond a few dozen slips; training adds evaluation and maintenance work; the strongest signal for small personal merchants is the user's own history, which is a lookup, not a model. Retrieval is an SQL query over `(owner_id, payee_key)`, not embeddings. Revisit a classifier only if evaluation shows the LLM hint step is the main error source **and** there is enough labelled data across users.

### Q4 Cold start and ambiguous payee names without asking a lot
Order of evidence, per transaction:
1. **User default for this payee** (explicitly set by the user) → `predicted`, source `user_default`.
2. **User history**: ≥ `N_MIN` confirmed transactions for this `payee_key` with one category reaching share ≥ `P_MIN` → `predicted`, source `history`. One confirmation never creates a rule; it only counts toward N.
3. **Seed merchant dictionary** (small, curated list of well-known brands/billers: convenience stores, transit, ride-hailing, telcos, utilities) → `predicted`, source `seed`. Not used when `is_intermediary`.
4. **LLM hint on the payee string only** (not the image) → stored as a hint, `category_state` stays `unclassified`; the review UI may pre-select it. Rationale: an LLM guessing "ร้านป้าสมาน" is a grocery is a guess and should not enter budget totals.
5. Otherwise `unclassified`.

Ambiguous / personal-name payees and intermediaries (QR aggregators, marketplace wallets) stay unclassified unless the user set a default. Reducing questions comes from **batching**, not guessing: "4 payments to ร้านป้าสมาน this month (฿45) — what are these usually?" with options: one category for all / set as default for this payee / leave unassigned.

### Q5 When to suggest automatically vs leave unclassified
Suggest (`predicted`) only from sources 1–3. Leave unclassified otherwise. Initial placeholders `N_MIN = 2`, `P_MIN = 0.8` — to be tuned on the development split only, then frozen before the test split is run.

### Q6 How uncertain categories affect pockets, insights and recommendations
Most of the cash-flow engine does not need categories at all: balance, shortage detection, daily allowance and goal feasibility depend on total settled spending, which includes unclassified rows (FI-12). Categories matter only for pocket/category attribution:

- Pocket view shows `spent_confirmed`, `spent_predicted`, and the account shows `unassigned_total`. "Remaining" uses confirmed + predicted; the UI shows the predicted part.
- Overspending alert for a pocket fires on confirmed + predicted. If unassigned spending could push a pocket over, the insight says "may be over" and offers a review of only those items.
- A proposal that changes allocations (T2) and depends on predicted/unassigned amounts lists them in the card ("based on ฿300 we guessed is Food — check?"). Approving the proposal does not confirm categories; they remain predicted unless the user confirms them.
- No allocation change, goal change or recommendation with estimated savings is applied from predicted categories without the user's approval (already required), and the card must say which inputs were predicted.
- Clarification is asked only when the answer could change the output the user is looking at: e.g., "Can I afford ฿800 of shopping?" does not depend on categories → no question; "Why is my Food pocket over?" does → ask about the unassigned items that could be Food, largest first, stop when the answer no longer changes.

### Q7 Innovation vs ordinary engineering
Ordinary good practice (do it, don't sell it as innovation): VLM extraction, integer satang, idempotency keys, RLS, audit logs, approval cards, deduplication by reference.

Potentially defensible innovation, **only if measured**:
- **Decision-relevant clarification**: the assistant asks a question only when the unknown can change the answer or proposal currently on screen, and chooses the item whose answer changes it most. Measurable: questions per decision and decision error vs "ask about everything" and "ask about nothing".
- **Uncertainty-aware budgeting**: pockets and alerts carry confirmed/predicted/unassigned parts; no silent guesses enter plans. Measurable: budget-attribution error and false overspend alerts vs a baseline that trusts every guess.
- **History-grounded personal merchant memory without training**: per-user, explicit, revisable defaults. Measurable: coverage and precision over time in a chronological replay.

### Q8 Evaluating accuracy against questions and corrections
See `06-acceptance-and-traceability.md §4` for protocol. Headline metrics reported together, never one alone: precision of auto-assigned categories, coverage, questions/100 txns, corrections/100 txns, pocket attribution error (satang), false overspend alerts, latency p50/p95, cost per image.

## 2. Validation rules (deterministic, after extraction)

| Field | Critical for totals? | Rule | Failure → |
|---|---|---|---|
| amount | yes | FI-2 parse; > 0; ≤ configurable cap | review (field `amount`) |
| direction | yes | from doc type: transfer-out slip → expense; incoming slip → income; receipt → expense; bill → bill | review (`direction`) |
| payment status | yes | success wording / bank success marker; "pending/failed/scheduled" → not completed | review (`status`) or record as not completed |
| occurred_at | yes for period/balance | parse Thai/BE dates (BE year − 543); within scan range; not in future beyond tolerance | review (`occurred_at`) |
| bank_ref | no (dedup only) | normalised, bank format check if known | stored as null |
| payee | no | normalised to `payee_key` | `payee_unknown` (still importable) |

A record missing a non-critical field is still imported. A record with any critical field missing/conflicting goes to review and is excluded from totals (R2.6).

## 3. Payee normalisation (deterministic)
Unicode NFC; casefold; strip bank decorations ("นาย", "นาง", "น.ส.", "MR", "MS", "บจก.", "CO.,LTD"), masked account fragments ("xxx-x-x1234-x"), punctuation and repeated spaces; keep Thai and Latin letters and digits. `payee_key = owner-independent normalised string`. Intermediary detection by a small list of patterns (to be curated with real samples). This is tested on synthetic strings only until redacted samples exist.

## 4. Two-day scope vs later

| Now (by 16–17 Oct) | Later (only with evidence it helps) |
|---|---|
| VLM extraction with schema + validation | Local OCR fallback for offline/privacy mode |
| sha256 dedup, bank-ref dedup, receipt+slip proposal | Perceptual-hash near-duplicate tuning |
| payee normaliser + history/default/seed suggestion | Shared anonymised merchant knowledge across users (needs consent design) |
| Batch review endpoint grouped by payee | Classifier trained on accumulated confirmations |
| Evaluation harness on synthetic + consented redacted data | Larger user study |
