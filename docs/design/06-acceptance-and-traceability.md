# 06 — Acceptance plan and submission traceability

### Reference checkpoint status (Codex, 16 Oct 2026)

| Scope | Implemented | Tested | Not verified / open |
|---|---|---|---|
| Multi-reference design and legacy dedup regressions (`14`) | Proposal + synthetic tests; no production change | `20261016T122231Z-reference-contract-regressions`: 57 passed, 2 strict xfailed; unmasked new suite: 2 failed, 8 passed | REF-GAP-1 alternate-field double count; REF-GAP-2 untyped ID false merge; typed storage/mapping and DB replay pending |

Status: **Proposed**. "Status" columns reflect what has actually run (see `evidence/`). Never mark a row `pass` without an evidence file.

Columns: **Implemented** = code exists; **Tested** = a test or eval ran and its evidence id is given; **Not verified** = what no evidence covers yet. `cp2` = suite run `20261015T120215Z-cp2-cards-gaps` (236 passed); `cp2b` = `20261015T130541Z-cp2b-review-fixes` (245 passed, after Codex CP2 review); `cp2c` = `20261015T131509Z-cp2c-transfer-pairs` (248 passed, transfer-pair DB guard). A passing test count is not a competition score.

**Checkpoint status:** CP1 accepted by Codex review; **CP2 accepted by Codex review (15 Oct 2026)** after fixes cp2b/cp2c; CP3a submitted for review (see `09`).

## 1. Traceability matrix (chain: requirement → design → code → test → evidence)

Evidence: latest suite run `20261015T131509Z-cp2c-transfer-pairs` (248 passed, x86_64, PG 16.15); same 248 in the Linux ARM64 VM on the owner's Mac (not native macOS), PG 18.4: `20261015T131712Z-cp2c-device-pg18-arm64`. Previous: `20261015T130541Z-cp2b-review-fixes` / `20261015T130810Z-cp2b-device-pg18-arm64` (245). Before the CP2 review: `20261015T120215Z-cp2-cards-gaps` (236 passed; API and worker as RLS-restricted roles; Python 3.12.3, Postgres 16.15); same 236 in the Linux ARM64 VM on the owner's Mac (not native macOS), Postgres 18.4: `20261015T120443Z-cp2-device-pg18-arm64`. Earlier: `20261015T094412Z-cp1g-rereview-fixes` (209; device `20261015T094715Z-cp1g-device-pg18`, Postgres 18.4, Linux ARM64 VM). Sandbox scenario `20261015T120158Z-demo-fake-cp2` (47 API steps, 0 unexpected).
**Mocks:** integration tests and the demo use `FakeExtractionProvider` (returns ground-truth fields) and `ScriptedChatModel` (fixed tool calls). "pass (mock)" below means the server-side logic is proven, not model quality.

| Req | Design | Code | Tests | Implemented | Tested (evidence) | Not verified |
|---|---|---|---|---|---|---|
| R1.1, R9.1 auth + isolation | SI-1, SI-2 | `services/core.py` (auth), all services take session `owner_id`; RLS `0002_rls.sql` | `test_security.py::test_sec_own_*`, `test_sec_auth_required_and_logout`, `test_sec_rls_blocks_cross_owner_even_without_app_filter` | yes | pass `cp2` | — |
| R1.2 onboarding inputs | `05` | `core.put_profile`, `add_balance_observation` | used by every integration test | yes | pass `cp2` | onboarding UI |
| R1.3, R9.6 consent (separate, revocable) | SI-5 | `core.grant/revoke_consent`, `imports.create_upload` | `test_sec_cons_*`, `test_no_auto_import_consent_means_confirm_in_review` | yes | pass `cp2` | consent UI wording |
| R2.1 identify documents in album | client | mobile app | MOB-01/02 | no (client) | — | everything (no Android client) |
| R2.2 extract fields | `04` | `providers.AnthropicExtractionProvider`, `domain/extraction_validation.py` | unit validation tests; real-model eval `scripts/eval_extraction.py` | yes | real-model eval on 40 synthetic slips (`20261015T090604Z-haiku-synth40`, v0.2 `20261015T091318Z-haiku-synth40-v02`): doc type 40/40, amount 39/39 (+1 correct abstention), date 39/40 (guarded), payee 40/40 (v0.2), ref 28/30 | real (redacted) slips; generalisation beyond 40 synthetic images |
| R2.3 scan status / last success | `05` | `imports.scan_status` | `test_scan_status_reports_last_success_and_pause` | backend only | pass `cp2` | background scan on device (client) |
| R2.4 duplicate images & payments (revised after Codex #5; ledger-level replay `20261015T092956Z-replay-v02-adv`: 0 double counts) | FI-28..30 | `domain/dedup.py`, `imports._route` | `test_exact_duplicate_image_is_idempotent`, `test_same_bank_ref_different_image_counts_once`, `test_two_waters_*`, `test_receipt_and_slip_count_once`, `test_sec_conc_manual_and_import_race` | yes | pass `cp2` (mock extraction); replay of real outputs `20261015T120337Z-replay-v02-adv-cp2`: 0 double counts | real-slip duplicates |
| R2.5 auto-save validated, marked, removable | FI-11 | `imports._insert_import_txn`, `delete_upload` | `test_e2e_slip_import_updates_plan`, `test_sec_cons_delete_then_retry_is_noop` | yes | pass `cp2` (mock extraction) | — |
| R2.6 review queue; unresolved excluded | FI-11 | `imports._route`, `resolve_review` | `test_unclear_amount_goes_to_review_and_is_excluded`, `test_pending_slip_recorded_but_excluded_from_totals` | yes | pass `cp2` | — |
| R2.7 pause / delete imported data (two-phase image purge after Codex #3: `test_f3_*`; purge never dies, repeat DELETE recovers, worker lease reclaim: `test_r2_*`, `test_r3_*`) | SI-5 | `revoke_consent`, `delete_upload`, `delete_all_imported` | `test_sec_cons_*` | yes | pass `cp2`; `/data/delete` with failing store, resume and owner scope: `test_data_delete_*` (CP2) | GCS behaviour (local store only); `scope: all` not implemented |
| R3.1–R3.3 manual entry, edit, duplicate check | FI-14, FI-30 | `core.create_manual_txn`, `patch_txn`, `delete_txn` | `test_manual_duplicate_check_and_confirm`, `test_refund_reconciles_and_cannot_exceed` | yes | pass `cp2`; corrections: `test_patch_*` (amount/date/category effects, anchor crossing, link guards, invalid values; CP2) | edit UI |
| R4.1–R4.3 pockets, reallocation via approval (BP-1 added after Codex #1: `test_f1_*`; buffer/period rule: `test_r1_*`) | FI-16, FI-17, FI-17a | `budget.create_pocket`, `pocket_status`, proposals | `test_reallocation_conserves_total_and_creates_no_expense`, `test_sec_agent_proposes_user_approves` | yes | pass `cp2` | — |
| R4.2/R8.2 approval card for budget/goal changes (CP2) | `05 §5`, FI-31..34 | `services/cards.py`, `budget._insert_proposal/edit_proposal/approve`, migration `0005_approval_cards.sql` | `test_cp2_cards.py` (13): content incl. move-all Food→Shopping, thresholds, uncertainty, goal effects, reload identity, card-hash binding, DB immutability, stale replacement recomputed, edit = new proposal, expiry on reload, agent sees card only as tool result | yes (backend contract) | pass `cp2`; examples `20261015T120156Z-card-examples` (11/11 checks) | final UI; thresholds are provisional product policy |
| R5.1 analyse history (3 months) | — | `domain/insights.monthly_history`, `GET /insights` | `test_monthly_history_and_recommendation` | yes | pass `cp2` | real multi-month data |
| R5.2 allocations + allowance after bills/essentials/savings/buffer | FI-23..25 | `domain/cashflow.py`, `budget.suggest_budget_plan` | `test_waterfall_reconciles_without_double_reservation`, `test_budget_plan_reconciles` | yes | pass `cp2` | — |
| R5.3 amounts/percentages with base | FI-4 | `allocation.allocate_bps` | unit | yes (API) | pass `cp2` | percent-editing UI |
| R5.4 trade-off when a pocket increases | `cashflow.tradeoff_increase` | `budget.propose_tradeoff`, `POST /plan/tradeoff`, agent `propose_tradeoff` | `test_tradeoff_takes_from_unspent_room_proportionally`, `test_tradeoff_proposal_conserves_and_requires_approval` | yes | pass `cp2` | — |
| R5.5 overspend + shortage | FI-27 | `insights.pace_alerts`, `shortage_satang`, trade-off proposal as revised plan | `test_pace_alerts` | partial | pass `cp2` (alerts on request) | push notifications; shortage date not computed |
| R5.6 recalc on change; apply after approval | SI-3 | `get_plan` recomputes; approvals | `test_slip_after_anchor_reduces_money_left`, `test_sec_apr_*` | yes | pass `cp2` | — |
| R6.1–R6.5 goals | `domain/goals.py` | `budget.goal_feasibility`, proposals `goal_create/update` | unit goal tests, `test_goal_feasibility_and_alternatives` | partial | pass `cp2`; `goal_update` via proposal/approval, staleness, validation: `test_goal_update_*` (CP2) | goal progress from transfers not linked |
| R7.1–R7.2 bills; paid once (consent gate + review confirmation after Codex #2/#4: `test_f2_*`, `test_f4_*`) | FI-19..22 | `core.create_bill`, `link_bill_payment` | `test_bill_then_payment_counts_once` | yes | pass `cp2` | — |
| R7.3 recurring charges / bill changes | — | `insights.recurring_charges`, `bill_changes` | `test_recurring_monthly_with_change`, `test_irregular_payee_is_not_recurring`, `test_bill_changes`, `test_insights_and_spending_report` | yes | pass `cp2` | real recurring data |
| R7.4 spending by category/merchant/period; budget vs actual | FI-18 | `GET /spending`, `pocket_status` | `test_insights_and_spending_report` | yes | pass `cp2` | — |
| R7.5 recommendations with estimated savings | — | `insights.recommendations` + goal impact in `budget.insights` | `test_monthly_history_and_recommendation` | partial | pass `cp2` | rule is simple (return to earlier average) |
| R7.6 detected/entered labelling | — | agent tool note, `source` field | — | partial | — | labelling not tested |
| R8.1–R8.5 chat, cards, what-if, focused questions | `05 §5`, SI-6/7 | `services/agent.py`, `scripts/real_agent_demo.py` | `test_sec_agent_*`, `test_sec_tools_registry_has_no_write_authority`; demo dry run `20261015T080339Z-agent-dryrun-scripted` (14/14 DB-checked controls, scripted model) | yes | pass `cp2` (scripted model); real Sonnet run `20261015T090742Z-agent-sonnet`: 14/14 DB-checked controls; scripted dry run `20261015T120205Z-agent-dryrun-scripted-cp2` 14/14 | model behaviour beyond 3 prompts; final card UI |
| R9.2 TLS + encryption at rest | SI-11 | deployment | manual | no | — | **blocked on deployment (D4)** |
| R9.3 secrets backend-only | SI-8 | `settings.py`, `.env` gitignored | `test_sec_log_audit_has_no_sensitive_content`, `test_unhandled_error_log_is_redacted` | yes | pass `cp2`; app-log redaction: `test_unhandled_error_log_is_redacted`, `test_third_party_log_lines_are_pattern_redacted` (CP2); worker path `test_r3_*` in `test_cp2_review_fixes.py`, pass `cp2b` | logs of a deployed server (uvicorn/GCP handlers configured outside the app) |
| R9.4 on-device filtering | client | — | MOB-02 | no (client) | — | everything |
| R9.7 validate fields/tools; image text untrusted | SI-6, SI-9 | `extraction_validation`, Pydantic tool args | `test_sec_inj_image_text_cannot_act`, `test_injected_text_has_no_channel` | yes | pass `cp2` (mock) | real-model injection eval |
| R9.8 duplicates, stale proposals, logging | SI-3, SI-4 | `infra.idempotent`, `budget.approve`, `audit` | `test_sec_apr_replay_and_repeat`, `test_sec_apr_concurrent_approvals_apply_once` (20 threads → 1 applied), `test_sec_apr_stale_after_data_change_returns_replacement` | yes | pass `cp2`; approval vs concurrent ledger change (two connections, controlled timing): `test_r2_*` in `test_cp2_review_fixes.py`, pass `cp2b` | — |
| R10.1–R10.6 storage, satang, balance anchor, linking | FI-1..FI-15 | schema `0001_core.sql`, ledger | `tests/db/*`, `test_projected_balance_anchor_rules`, `test_old_slips_do_not_reduce_balance_again` | yes | pass `cp2`; transfer legs change/delete together + DB trigger (FI-13a): `test_r1_*` in `test_cp2_review_fixes.py`, pass `cp2b`; hard delete / lone leg / group move: `test_r1b_*`, pass `cp2c` | — |
| R11 gamification (optional) | — | `goals.daily_amount_to_recover` only | — | no | — | optional |
| DC1 album → import/review → insights E2E | — | — | demo `20261015T072919Z-demo-fake-mocks-rls` covers upload → import/review → plan; album part needs client | partial | demo `20261015T120158Z-demo-fake-cp2` (47 API steps, mocks) | album part (client) |

### 1b. Android client (CP3a) — `cp3a-e2e` = `20261015T134438Z-cp3a-client-e2e-cloud` (client core vs real backend, 22/22 steps; core self-tests 17/17); backend `cp3a-be` = `20261015T134610Z-cp3a-backend` (253 passed, DB enabled, skipped 0). Same in the Linux ARM64 VM on the owner's Mac (PG 18.4): backend `20261015T135038Z-cp3a-backend-device-pg18-arm64` (253), client `20261015T135405Z-cp3a-client-e2e-device-pg18-arm64` (17/17, 22/22)

| Req | Design | Code | Tests | Implemented | Tested (evidence) | Not verified |
|---|---|---|---|---|---|---|
| R1.1 sign up / sign in / logout / session expiry (client) | SI-1, `05` | `core/Api.kt`, `app/Storage.kt` (Keystore), `AppState` | `CoreSelfTest` (401 clears token, offline logout), E2E 3–4, 22 | yes | core + E2E pass `cp3a-e2e` | app screens and Keystore on a device |
| R1.2 financial setup from the app | `05` | `SetupScreen`, `ApiClient.putProfile/addBalance/createPocket`, `GET /v1/pockets` | E2E 5; `test_list_pockets_is_owner_scoped` | yes | pass `cp3a-e2e`, `cp3a-be` | screen on a device |
| R1.3/R9.6 consent separate from OS permission; auto-import separate | SI-5 | `ConsentScreen`, `UploadQueue` blocks | E2E 6–7, 19, 21; `CoreSelfTest` consent block | yes | pass `cp3a-e2e` | screen on a device; OS permission flow (CP3b) |
| Manual photo selection (fallback) | `android/README.md` | `UploadScreen` (system Photo Picker, JPEG/PNG ≤ 8 MB, DATE_TAKEN when available) | device checklist | yes | **user-reported** on S22 Ultra (SM-S908E; called "S23" before the 16 Oct correction), 16 Oct 2026 (`10`, scenarios R1–R7; not automated evidence) | checklist lines 4, 10, 11, 14, 16, 17, 18 |
| Queue bound to account; pause mid-batch; undated confirmation; review decisions by server (Codex CP3a review) | `09` §fixes | `UploadQueue.bindOwner/requestPause/confirmUndated`, `ReviewActions`, `GET /v1/me`, `expected_owner_id`, `confirmed_undated`, `allowed_decisions` | core `#1/#2/#3`, undated; backend `test_upload_for_another_account…`, `test_undated…`, `test_receipt_review…`; E2E 4 new steps | yes | pass `20261015T141505Z-cp3a-fix-backend` (257), `20261015T140955Z-cp3a-fix-client-e2e-cloud` (22/22, 26/26) | screens on a device |
| Late 401 of an older session ignored by client, gate and queue (CP3a re-review 2) | `09` re-review 2 | `Api.kt` (`clearIf`, `staleToken`), `SessionGate.finish/onUnauthorized`, `UploadQueue` | core: 2 tests | yes | pass `20261015T172759Z-cp3a-stale401-client-e2e-cloud` (27/27) | screens on a device |
| Session gate: screens/queue only after `/me` + bind; stale `/me` ignored (CP3a re-review) | `09` re-review | `core/SessionGate.kt`, `AppState`, `MainActivity` | core gate tests (3), E2E gate step | yes | pass `20261015T164817Z-cp3a-gate-client-e2e-cloud` (25/25, 27/27) | screens on a device |
| Upload status, retry, duplicate guard, restart | FI-29, SI-4 | `UploadQueue`, `UploadLabels`, `POST /v1/uploads/{id}/retry` | `CoreSelfTest` (8 queue tests), E2E 8–15, `test_retry_*` | yes | pass `cp3a-e2e`, `cp3a-be` | WorkManager/background (CP3b) |
| Review: edit and confirm (slice 1 sheet; Codex slice-1 finding 1) | R2.6, `13` §4/§7 | `ReviewView` (inputs incl. due_date_text, status, doc_type; required-before-save; only changed fields), `ReviewResolver` (404 ≠ success), `ReviewScreen`/`ReviewSheet` | core 35 (5 review tests), E2E 31–34 incl. bill-without-due-date → bill and unknown status → user choice; backend `test_slice1_review_inputs.py` (3) | yes | pass `20261016T133608Z-slice1fix-client-e2e-device-pg18-arm64` (35/35, 34/34), `20261016T133727Z-slice1fix-backend-device-pg18-arm64` (290 passed; 2 skipped = Codex's strict xfail reference gaps) | app not compiled here (owner builds); screens on the S22 Ultra: checklist S1–S18 |
| Activity (slice 1; replaces the CP3a Ledger tab) and money text (Codex slice-1 finding 2) | R4.1, R7.4, `13` §4 | `ActivityModel`, `MoneyText.magnitude/amount/signed/safeToSpend`, `ActivityScreen`, Setup summary | core money test (negatives, zero, satang), activity test; E2E activity step | yes | pass `20261016T133608Z-slice1fix-client-e2e-device-pg18-arm64` | screens on the S22 Ultra (S9, S18); pocket budgets need a plan (CP3b) |
| No silent fake provider | SI-8 | `settings.py` (no default; fake only dev/test), `/v1/health.test_mode`, TEST MODE banner | `test_provider_must_be_explicit_and_fake_only_in_dev_test`, `test_health_reports_test_mode`, E2E 1 | yes | pass `cp3a-be`, `cp3a-e2e` | banner on a device |
| HTTPS-only release | SI-11 | `BaseUrlPolicy`, `network_security_config` (debug override local only) | `CoreSelfTest`, E2E 2 | yes | policy pass `cp3a-e2e` | release build on a device |

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
