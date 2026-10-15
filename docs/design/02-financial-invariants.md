# 02 — Financial semantics and invariants

Status: **Proposed**. Each invariant has an ID (FI-n) used by tests and the traceability matrix.
"Implemented" in this file means code + a test that ran; see `06` for current status.

## 1. Money, rounding, time

- **FI-1** Amounts are `int` satang (1 THB = 100 satang), `> 0`. Sign is never encoded in the amount; `kind`/`direction` carries it. DB: `bigint CHECK (amount_satang > 0)`.
- **FI-2** Parsing: accept `"1,234.5"`, `"1234.50"`, `"฿1,234.50"`, `"1,234.50 บาท"`; reject more than two decimals, negatives, empty, scientific notation, thousand separators in wrong positions. Never use `float`. Implemented in `domain/money.py::parse_thb`.
- **FI-3** Rounding of derived amounts (e.g., daily allowance, percentage shares) **floors** to the satang; the remainder is reported explicitly (`remainder_satang`) and goes to a named line (buffer by default), so parts always sum to the whole.
- **FI-4** Percentages are integer basis points (10000 = 100 %) and always carry a `base` label (e.g., `discretionary_for_period`). Allocation across pockets uses the largest-remainder method with deterministic tie-break (pocket order, then id). Implemented in `domain/allocation.py`.
- **FI-5** Timestamps stored as UTC `timestamptz`. Business dates (which day/period a transaction belongs to) are computed in the user's timezone (default `Asia/Bangkok`). Periods are half-open `[start, end)`. Implemented in `domain/periods.py`.
- **FI-6** Days remaining for allowances = number of local calendar days from today (inclusive) to the next income date (exclusive). If next income date ≤ today → allowance not computed; the API returns `NEXT_INCOME_DATE_PASSED` and asks for an update.

## 2. Balance and history

- **FI-7** A `balance_observation(account_id, amount_satang, as_of)` is the anchor. Projected balance at time t ≥ as_of = observation + Σ effects of **settled** transactions with `as_of < occurred_at ≤ t`.
- **FI-8** Transactions with `occurred_at ≤ as_of` are history only: they feed spending analysis and classification but never change the projected balance. Importing old slips therefore cannot subtract spending already reflected in the balance.
- **FI-9** Date-only transactions (no time on the slip) on the observation's local date are treated as `≤ as_of` (already reflected) by default, and the card shows "assumed already in your balance" (D6). A date-only observation is `as_of = end of that local day`.
- **FI-10** A new balance observation supersedes older ones for projection; older ones remain for audit. Divergence between the projection and a new observation is shown as "untracked difference", not booked as a transaction.

## 3. Transaction kinds and their effects

| kind | Balance effect (tracked account) | Counts as spending | Counts as income |
|---|---|---|---|
| `expense` | −amount | yes | no |
| `income` | +amount | no | yes |
| `refund` | +amount | reduces spending of the linked category/period (net), never income | no |
| `transfer_out` (to own account; with `transfer_group_id` when the destination is tracked) | −amount on source | no | no |
| `transfer_in` (from own account; same group id as its `transfer_out` leg) | +amount on destination | no | no |

Implementation note (CP1): the earlier draft names `transfer_internal` / `transfer_out_own` / `transfer_in_own` were replaced by two leg kinds, because one row cannot carry a sign for both accounts. A transfer to an untracked own account is a single `transfer_out` leg (leaves spendable cash, not spending).

- **FI-11** Only rows with `amount_state = confirmed`, `direction_state = confirmed`, `payment_status = completed` affect balances and totals. Pending/failed/unknown rows are visible but excluded (R2.6).
- **FI-12** `category_state` (`unclassified | predicted | confirmed`) never affects inclusion in total spending; it only affects attribution to pockets/categories (see `04 §6`).
- **FI-13** Internal transfer legs are linked (`transfer_group_id`); a group must be exactly one `transfer_out` + one `transfer_in` of equal amount (net 0, `domain/ledger.check_transfer_groups`).
- **FI-14** A refund references its source transaction when known (`refund_of`). Σ refunds of a source ≤ source amount (enforced in service, tested). Unlinked refunds are allowed but flagged for review.
- **FI-15** Corrections never edit history silently: an edit writes an `audit_event` with before/after of changed fields; deletes are soft until purge.

## 4. Pockets

- **FI-16** A pocket is an allocation within a budget period, not money. `Σ pocket allocations + unallocated = discretionary budget` for the period (strict equality, tested).
- **FI-17** Reallocation changes two allocations by ±x in one transaction; Σ unchanged; no `txn` row is created. An allocation cannot go below 0; it may go below the amount already spent, which then shows as overspent.
- **FI-17a (BP-1, added after Codex CP1 review #1)** For the plan period, Σ over pockets of max(0, allocation − spending attributed to that pocket) must be ≤ max(0, money left now). Checked when a proposal is created and again under lock at approval, for budget plans, reallocations and trade-offs. A change that does not increase that unspent total is allowed without the money check only when it also keeps the same plan period and does not raise the buffer (Codex re-review: raising the buffer alone used to slip through); otherwise the full check applies. Consequence: budget already spent (including an overspent pocket's allocation) cannot be moved to another pocket.
- **FI-18** Pocket spending = Σ settled expenses − linked refunds in the period whose (confirmed or predicted) category maps to the pocket. Confirmed and predicted parts are reported separately.

## 5. Bills

- **FI-19** A `bill` is an obligation (`amount_due`, `due_date`, `status ∈ unpaid|paid|cancelled`). An unpaid bill reduces *available* money in the forecast; it never changes the balance.
- **FI-20** Paying a bill = linking it to exactly one completed `expense` transaction (`bill_payment_link`, unique on both bill and txn). Once linked, the bill drops out of commitments and the transaction is the only spending row. Unique constraints make a second link fail.
- **FI-21** Partial payment: v1 supports one payment per bill; an amount mismatch keeps the bill unpaid and sends it to review (no silent tolerance).
- **FI-22** A bill image (unpaid invoice) creates a `bill`, never a transaction. A slip creates a transaction. A slip whose payee/amount matches an unpaid bill is *proposed* as its payment (exact amount, due window); an auto-link happens only with an exact reference match.

## 6. Cash-flow waterfall (single source for budgets, allowance and goals)

For the period `[today, next_income_date)`:

```
projected_balance_now
− unpaid bills due before next_income_date          (each bill once, by id)
− essentials not already represented by a bill      (essential template minus bills linked to it)
− savings line = Σ goal contributions due this period (goal plan) or savings preference
− buffer (user setting, amount or bps of income, labelled)
= discretionary  (may be negative → shortage)
```

- **FI-23** Each reserved line has a `source` id; the same source cannot appear in two lines (enforced by the function, tested). A "Savings" pocket, if present, is a *view* of the savings line, not an additional reservation.
- **FI-24** `Σ lines + discretionary = projected_balance_now` exactly.
- **FI-25** Income not yet received is never counted as available before its date; feasibility for later periods uses the income schedule explicitly.
- **FI-26** "Can I afford X?" runs the waterfall with a hypothetical expense and returns deltas; it performs no write (verified by row counts and audit log before/after).
- **FI-27** Negative discretionary ⇒ `cash_shortage` insight with the earliest date balance would cross zero under the schedule.

## 7. Duplicate detection

Ordered checks; earlier strong evidence wins.

| Evidence | Action |
|---|---|
| Same image bytes (sha256, per owner) | Same upload; return existing (idempotent) |
| Same bank reference **and same amount** | Same payment; no second txn; image linked as evidence (the only automatic merge) |
| Same reference, different amount | Conflict → review |
| References within 2 edits (≥8 chars) and same amount | Possible misread → review (Codex CP1 #5; real case slip_021) |
| Clearly different references | Distinct, even with identical amount/time/payee (two ฿10 waters) |
| ~~Near-identical image (perceptual hash)~~ | **Removed as a signal (15 Oct):** on templated slips, distinct payments have dHash distance 0 (measured on the synthetic set), so it cannot separate purchases |
| Receipt (no bank ref) + slip with equal amount, same payee similarity, within ±30 min | Proposed "receipt is evidence of this slip" link; count once (the slip); confirm in batch review |
| Manual entry matching an existing txn (amount equal, same local day, payee similar) | API returns candidates; client must resend with `confirm_distinct=true` to create |

- **FI-28** Equal amount + equal date alone never deletes or merges a transaction.
- **FI-29** DB uniqueness: `(owner_id, sha256)` on uploads; `(owner_id, bank_ref_norm)` unique only for **confirmed** references (user-typed or confirmed in review; migration 0003). A model-read reference is stored with `bank_ref_confirmed=false` and is evidence, not identity. Concurrent imports of the same payment resolve via these constraints (one wins, the other gets the existing id).
- **FI-30** Manual entries usually have no bank reference, so a constraint cannot catch a manual/import race. Transaction creation therefore takes a per-owner transaction-scoped advisory lock (`pg_advisory_xact_lock`) around "find candidates → insert", so the second writer sees the first and goes to the candidate/review path. Throughput cost is irrelevant at one user's scale.
