# 06 — Acceptance plan and submission traceability

Status: **Proposed**. "Status" columns reflect what has actually run (see `evidence/`). Never mark a row `pass` without an evidence file.

Status values: `not-started` · `designed` · `implemented-untested` · `pass (run id)` · `fail (run id)` · `env-limited` · `n/a`.

## 1. Traceability matrix (chain: requirement → design → code → test → evidence)

Evidence: unit + integration suite run `20261015T093021Z-cp1f-review-fixes` (202 passed incl. Codex CP1 regression tests; API and worker run as RLS-restricted roles, Python 3.12.3, Postgres 16.15); sandbox scenario `20261015T072919Z-demo-fake-mocks-rls` (47 API steps, 0 unexpected statuses).
**Mocks:** integration tests and the demo use `FakeExtractionProvider` (returns ground-truth fields) and `ScriptedChatModel` (fixed tool calls). "pass (mock)" below means the server-side logic is proven, not model quality.

| Req | Design | Code | Tests | Status |
|---|---|---|---|---|
| R1.1, R9.1 auth + isolation | SI-1, SI-2 | `services/core.py` (auth), all services take session `owner_id`; RLS `0002_rls.sql` | `test_security.py::test_sec_own_*`, `test_sec_auth_required_and_logout`, `test_sec_rls_blocks_cross_owner_even_without_app_filter` | pass (two layers; with RLS on, removing an app-level owner filter no longer leaks — re-checked by mutation) |
| R1.2 onboarding inputs | `05` | `core.put_profile`, `add_balance_observation` | used by every integration test | pass |
| R1.3, R9.6 consent (separate, revocable) | SI-5 | `core.grant/revoke_consent`, `imports.create_upload` | `test_sec_cons_*`, `test_no_auto_import_consent_means_confirm_in_review` | pass |
| R2.1 identify documents in album | client | mobile app | MOB-01/02 | **not started (no client)** |
| R2.2 extract fields | `04` | `providers.AnthropicExtractionProvider`, `domain/extraction_validation.py` | unit validation tests; real-model eval `scripts/eval_extraction.py` | real model run on 40 synthetic slips (`20261015T090604Z-haiku-synth40`): doc type 40/40, amount 39/39 (+1 correct abstention), date 39/40, payee 38/40, ref 29/30; 1 would-be wrong auto-import → fixed by date plausibility guard (re-run pending). **Real slips not evaluated.** |
| R2.3 scan status / last success | `05` | `imports.scan_status` | `test_scan_status_reports_last_success_and_pause` | pass (backend part); background scan **client, not started** |
| R2.4 duplicate images & payments (revised after Codex #5; ledger-level replay `20261015T092956Z-replay-v02-adv`: 0 double counts) | FI-28..30 | `domain/dedup.py`, `imports._route` | `test_exact_duplicate_image_is_idempotent`, `test_same_bank_ref_different_image_counts_once`, `test_two_waters_*`, `test_receipt_and_slip_count_once`, `test_sec_conc_manual_and_import_race` | pass (mock extraction) |
| R2.5 auto-save validated, marked, removable | FI-11 | `imports._insert_import_txn`, `delete_upload` | `test_e2e_slip_import_updates_plan`, `test_sec_cons_delete_then_retry_is_noop` | pass (mock extraction) |
| R2.6 review queue; unresolved excluded | FI-11 | `imports._route`, `resolve_review` | `test_unclear_amount_goes_to_review_and_is_excluded`, `test_pending_slip_recorded_but_excluded_from_totals` | pass |
| R2.7 pause / delete imported data (two-phase image purge after Codex #3: `test_f3_*`) | SI-5 | `revoke_consent`, `delete_upload`, `delete_all_imported` | `test_sec_cons_*` | pass (`/data/delete` route untested) |
| R3.1–R3.3 manual entry, edit, duplicate check | FI-14, FI-30 | `core.create_manual_txn`, `patch_txn`, `delete_txn` | `test_manual_duplicate_check_and_confirm`, `test_refund_reconciles_and_cannot_exceed` | pass (edit path lightly tested) |
| R4.1–R4.3 pockets, reallocation via approval (BP-1 added after Codex #1: `test_f1_*`) | FI-16, FI-17, FI-17a | `budget.create_pocket`, `pocket_status`, proposals | `test_reallocation_conserves_total_and_creates_no_expense`, `test_sec_agent_proposes_user_approves` | pass |
| R5.1 analyse history (3 months) | — | `domain/insights.monthly_history`, `GET /insights` | `test_monthly_history_and_recommendation` | pass (calendar months; averages use complete months only) |
| R5.2 allocations + allowance after bills/essentials/savings/buffer | FI-23..25 | `domain/cashflow.py`, `budget.suggest_budget_plan` | `test_waterfall_reconciles_without_double_reservation`, `test_budget_plan_reconciles` | pass |
| R5.3 amounts/percentages with base | FI-4 | `allocation.allocate_bps` | unit | pass (percent editing UI contract only) |
| R5.4 trade-off when a pocket increases | `cashflow.tradeoff_increase` | `budget.propose_tradeoff`, `POST /plan/tradeoff`, agent `propose_tradeoff` | `test_tradeoff_takes_from_unspent_room_proportionally`, `test_tradeoff_proposal_conserves_and_requires_approval` | pass |
| R5.5 overspend + shortage | FI-27 | `insights.pace_alerts`, `shortage_satang`, trade-off proposal as revised plan | `test_pace_alerts` | partial: alerts computed on request (no push); shortage date not computed |
| R5.6 recalc on change; apply after approval | SI-3 | `get_plan` recomputes; approvals | `test_slip_after_anchor_reduces_money_left`, `test_sec_apr_*` | pass |
| R6.1–R6.5 goals | `domain/goals.py` | `budget.goal_feasibility`, proposals `goal_create/update` | unit goal tests, `test_goal_feasibility_and_alternatives` | partial: goal progress from transfers not linked |
| R7.1–R7.2 bills; paid once (consent gate + review confirmation after Codex #2/#4: `test_f2_*`, `test_f4_*`) | FI-19..22 | `core.create_bill`, `link_bill_payment` | `test_bill_then_payment_counts_once` | pass |
| R7.3 recurring charges / bill changes | — | `insights.recurring_charges`, `bill_changes` | `test_recurring_monthly_with_change`, `test_irregular_payee_is_not_recurring`, `test_bill_changes`, `test_insights_and_spending_report` | pass (≥3 occurrences, weekly/monthly cadence) |
| R7.4 spending by category/merchant/period; budget vs actual | FI-18 | `GET /spending`, `pocket_status` | `test_insights_and_spending_report` | pass |
| R7.5 recommendations with estimated savings | — | `insights.recommendations` + goal impact in `budget.insights` | `test_monthly_history_and_recommendation` | partial: rule = return to earlier average; goal impact uses a simple capacity model |
| R7.6 detected/entered labelling | — | agent tool note, `source` field | — | partial |
| R8.1–R8.5 chat, cards, what-if, focused questions | `05 §5`, SI-6/7 | `services/agent.py`, `scripts/real_agent_demo.py` | `test_sec_agent_*`, `test_sec_tools_registry_has_no_write_authority`; demo dry run `20261015T080339Z-agent-dryrun-scripted` (14/14 DB-checked controls, scripted model) | real Sonnet run `20261015T090742Z-agent-sonnet`: 14/14 DB-checked controls; behaviour observed on 3 prompts only |
| R9.2 TLS + encryption at rest | SI-11 | deployment | manual | **blocked on D4 deployment** |
| R9.3 secrets backend-only | SI-8 | `settings.py`, `.env` gitignored | `test_sec_log_audit_has_no_sensitive_content` | pass (audit only; app logs not yet scanned) |
| R9.4 on-device filtering | client | — | MOB-02 | **not started** |
| R9.7 validate fields/tools; image text untrusted | SI-6, SI-9 | `extraction_validation`, Pydantic tool args | `test_sec_inj_image_text_cannot_act`, `test_injected_text_has_no_channel` | pass (mock); real-model injection eval pending |
| R9.8 duplicates, stale proposals, logging | SI-3, SI-4 | `infra.idempotent`, `budget.approve`, `audit` | `test_sec_apr_replay_and_repeat`, `test_sec_apr_concurrent_approvals_apply_once` (20 threads → 1 applied), `test_sec_apr_stale_after_data_change_returns_replacement` | pass |
| R10.1–R10.6 storage, satang, balance anchor, linking | FI-1..FI-15 | schema `0001_core.sql`, ledger | `tests/db/*`, `test_projected_balance_anchor_rules`, `test_old_slips_do_not_reduce_balance_again` | pass |
| R11 gamification (optional) | — | `goals.daily_amount_to_recover` only | — | not started |
| DC1 album → import/review → insights E2E | — | — | demo `20261015T072919Z-demo-fake-mocks-rls` covers upload → import/review → plan; album part needs client | partial |

Mutation checks (manual, 15 Oct): removing the owner filter in `get_proposal`, the watermark staleness check, or the idempotency hash check each made a test fail. Removing only the proposal row lock did **not** (plan row lock + watermark still serialise); removing all three let 10/20 concurrent approvals apply, which the test caught. Removing only the consent re-check did not fail because revocation also cancels the job; removing both did.

## 2. Test categories

1. **Deterministic calculation tests** (`tests/unit`): pure functions, independent expected outputs written by hand (or by Codex) before implementation; no DB.
2. **Ownership / approval / consent / security tests** (`tests/security`): run against Postgres with the runtime role; each SI has at least one negative test.
3. **Integration and concurrency tests** (`tests/integration`): API + DB + worker with a **fake** model provider; parallel requests via threads/processes.
4. **Actual extraction/classification evaluation** (`eval/`): real provider; reported as an evaluation run with model id and cost, not as pass/fail tests.
5. **Actual agent workflow evaluation** (`eval/agent/`): scripted scenarios on the real model; graded on tool calls made, proposal correctness (vs deterministic expected), arithmetic errors (should be zero because the model never computes), clarification count.
6. **Mobile-specific checks** (manual, recorded): cannot be proven by the backend.

## 3. Mobile-specific checks the backend cannot prove

MOB-01 permission prompt and limited/selected-photos behaviour on the chosen OS · MOB-02 on-device filtering uploads only candidates (count uploaded vs scanned) · MOB-03 scan on app open/refresh and last-successful-scan display · MOB-04 background scan within OS scheduling (best effort; document actual behaviour, iOS may defer) · MOB-05 pause/revoke stops uploads on device.

## 4. Classification and extraction evaluation protocol

**Data**: (a) synthetic slip images rendered from templates with known ground truth; (b) only with D7 consent: team members' redacted slips + their own purpose labels, stored outside Git (`eval/private/`, gitignored).

**Leakage control**
- Deduplicate by image sha256 and bank reference before splitting.
- Split by **payee_key groups** for the *new-merchant* condition (test payees never seen in dev).
- *Seen-merchant* condition = chronological replay: for each transaction in time order, predict using only confirmations strictly earlier; never use later labels.
- Thresholds (`N_MIN`, `P_MIN`, seed list) tuned on dev only, frozen (commit hash recorded) before the test run.

**Metrics (reported together)**
- Extraction: per-field exact accuracy (amount, date-time, ref, direction, status); critical-field error rate on auto-imported records (target: 0 known errors; any error is listed).
- Classification: precision of `predicted` among those predicted; coverage = predicted / all; accuracy if forced (diagnostic only); separately for seen vs new payees.
- Burden: questions per 100 transactions; corrections per 100 transactions (predicted later changed by user).
- Budget impact: Σ |pocket attribution error| in satang per period; count of false overspend alerts.
- Operations: latency p50/p95 per image, cost per image (provider pricing at run time), failure rate.

**Baselines**: B0 everything unclassified; B1 LLM category guess for every row (no history); ours. Sample sizes will be small; report counts and confidence intervals, not generalised claims.

## 5. Evidence manifest (per run)

Each run writes `evidence/runs/<UTC timestamp>-<slug>/` containing `manifest.json` (schema `evidence/manifest.schema.json`), raw tool output (`*.log`), and a short `summary.md`. Required fields: run id, timestamp UTC, git commit (or `uncommitted` + content hash), command, environment (OS, Python, Postgres version), configuration, model identifier(s) or `none`, `uses_mocks` list, expected vs actual per case, result. Personal images, tokens and chain-of-thought are never stored.
