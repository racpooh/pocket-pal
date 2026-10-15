# 08 — CP1 review request for Codex (15 Oct 2026)

Scope implemented since CP0 and the points where an independent review is most useful. Evidence: see `06 §1`.

## Please review (highest risk first)

1. **Approval path** — `services/budget.py::approve`, `_check_applicable`, `infra.idempotent`.
   Proposal row `FOR UPDATE`, plan row `FOR UPDATE`, strict data-watermark staleness, payload-hash binding, idempotency row inserted in the same transaction. Question: is strict watermark staleness acceptable for the demo, or should staleness depend only on inputs the proposal used?
2. **Consent/worker race** — `services/imports.py::persist_extraction` locks the consent grant `FOR SHARE`; `core.revoke_consent` takes `FOR UPDATE` and cancels jobs. Model call happens outside any DB transaction.
3. **Manual vs import race** — `infra.lock_owner_ledger` (per-owner `pg_advisory_xact_lock`) around candidate search + insert in both paths.
4. **Budget-plan total check** — `_check_applicable(kind="budget_plan")`: a new plan may raise the total only by what is still available now; conserving/reducing changes are always allowed. Is this the right rule once spending has started in the period?
5. **Balance anchor** — `domain/ledger.projected_balance` + D6 (date-only same-day = reflected).
6. **Dedup rules** — `domain/dedup.decide`: refs differ ⇒ never duplicates; missing ref on either side + same amount/day ⇒ ask.
7. **Agent boundary** — `services/agent.py`: tools T0–T2 only, owner bound server-side, 8 tool calls/turn, image fields reach the model only as typed tool results.

## Known deviations from the CP0 design
- No repository layer: SQL lives in services, always parameterised with the session `owner_id`.
- Transaction kinds changed to `transfer_out` / `transfer_in` legs (see `02 §3`).
- RLS second layer implemented after this request was first drafted: please review `0002_rls.sql`, especially the `job_worker_claim` policy and session-level `set_config` on per-request connections.
- Thresholds (`N_MIN`, `P_MIN`, phash distance, recurring tolerance) are placeholders, not tuned.

## Not covered by any test yet
`/data/delete` route, `PATCH /transactions` beyond version conflict, `goal_update` proposals, chat history retention on/off, app-level log redaction, real-model extraction and agent runs.

---

## Update — real-model checkpoint (15 Oct 2026, ~15:00 ICT)

**Code version:** no git commits yet on `main` (remote `pocketwise` configured, everything untracked). Evidence manifests therefore record a content hash (`content_sha256_16`) instead of a commit id.

### What was done
| Step | Result | Evidence |
|---|---|---|
| Config: single loader for API/worker/scripts | `Settings` now reads env vars > repo-root `.env` > `backend/.env`. Verified on the user's machine: provider `anthropic`, extraction `claude-haiku-5-5`, chat `claude-sonnet-5-5`, `api_key_present: true` (value never printed). | console check, no file |
| Fail closed | Unknown provider or `anthropic` without key → `ConfigError` in API startup, worker and scripts; `fake` must be chosen explicitly; `/chat` returns 503 when no real model is configured. | `tests/unit/test_config_fail_closed.py` (6 passed) |
| Cost controls | `UsageMeter`: pre-call worst-case check (estimated input + max output) against `FINASSIST_BUDGET_USD` (default $1) including spend recorded by earlier runs in `evidence/usage_ledger.jsonl`; request cap 120; max output 400 (extraction) / 700 (chat); SDK retries 0; non-retryable errors (auth, permission/billing, unknown model, bad request) stop the run. Prices from the official pricing page on 15 Oct: Haiku 5.5 $0.10/$0.50, Sonnet 5.5 $2/$10 per MTok (≤100k-token prompts). | same test file |
| Model access check | **Blocked in the Cowork VM.** Its egress proxy answers `401 text/plain` to any request carrying `x-api-key` to api.anthropic.com (a bogus key gets the same response; a request without a key reaches Anthropic and gets its JSON 401). Not an Anthropic auth/billing error. No billed call was made; spend so far **$0.00**. We did not try to route around the proxy. | — |
| Full suite on the owner's machine (Linux VM, Python 3.12.14, Postgres 18.4 via `scripts/local_pg.py`) | 186 passed, 0 failed (two earlier attempts failed on a helper-script bug, kept with NOTE.md) | `evidence/runs/20261015T081812Z-cp1d-device-pg18` |
| Full suite in the build sandbox (Python 3.12.3, Postgres 16.15) | 186 passed (one earlier attempt errored because the sandbox Postgres had stopped; NOTE.md) | `evidence/runs/20261015T081619Z-cp1d-cloud-all` |
| Decision | Run real-model steps from the owner's own terminal: `backend/scripts/run_real_checkpoint.sh` (config → smoke 5 → full 40 → agent demo; stops at first failure). | — |
| Agent demo script dry run (scripted model, no API) | 14/14 deterministic controls passed: chat changes nothing by itself, no approval by the agent actor (audit), cross-user 404 with state unchanged, altered hash rejected, single application + conserved totals, replay/repeat, exactly one user approval in audit, stale → replacement with no change. **This proves the checks run, not model behaviour.** | `evidence/runs/*-agent-dryrun-scripted/` (uses_mocks: ScriptedChatModel) |

### Commands (run by the owner)
```bash
cd backend && bash scripts/run_real_checkpoint.sh
```
Individual steps: `uv run python scripts/eval_extraction.py --slug haiku-smoke5 --limit 5`, `... --slug haiku-synth40`, `TEST_DATABASE_URL=$(uv run --with pixeltable-pgserver python scripts/local_pg.py) uv run --with pixeltable-pgserver python scripts/real_agent_demo.py --slug agent-sonnet`.

### How results are separated
- Extraction (per field: doc type, amount, date, time, payee, bank ref, status, due date) vs classification (chronological replay, scored separately; abstention counted, never forced). Ground truth is loaded only after all model calls; prompt/tool-schema hashes recorded; `ground_truth_in_prompt: false`.
- Agent demo: `controls_deterministic` (DB/audit verified) vs `behaviour_observed` (tools chosen, proposals, replies) in the same manifest.

### Expected cost (estimate before running)
Extraction ≈ 40 × (~620 image + ~1.5k prompt/tool tokens in, ≤400 out) ≈ 85k in / ≤16k out on Haiku ≈ **$0.02**. Agent demo ≈ 3 chats × ≤6 model steps × ~6–10k tokens in on Sonnet ≈ **$0.15–0.40**. Budget guard stops at $1.00 cumulative.

### Still untested / open
Real extraction accuracy; real agent behaviour; redacted real slips (not in this round, synthetic only); `/data/delete`, `goal_update`, chat-history retention toggle; app-log redaction; deployment.

### Proposed next part (after this review)
1. Owner runs the checkpoint script; Claude analyses the manifests and fixes extraction/validation issues found.
2. Codex reviews approval/consent/RLS paths above plus the real-model results.
3. Then: private redacted slips (D7), Android client spike, GCP deployment (paid) — each only after this checkpoint is accepted.

---

## Results — real-model run by the owner (15 Oct 2026, 16:05–16:08 ICT, owner's Mac, Python 3.13)

Command: `cd backend && bash scripts/run_real_checkpoint.sh`. Code: no commits; content hash `d3975ace61b9d6a3` (recorded in the manifests). Config: provider `anthropic`; model access check resolved `claude-haiku-5-5` and `claude-sonnet-5-5`; budget $1.00, output caps 400/700, retries 0. Data: synthetic only.

| Run | Evidence | Outcome |
|---|---|---|
| Smoke, 5 slips | `evidence/runs/20261015T090551Z-haiku-smoke5` | 5/5 schema-valid, all fields correct; $0.0016 |
| Synthetic, 40 slips | `evidence/runs/20261015T090604Z-haiku-synth40` | see table below; $0.0126; p50 1.8 s, max 3.1 s; 67,842 in / 11,561 out tokens |
| Agent demo (Sonnet) | `evidence/runs/20261015T090742Z-agent-sonnet` | controls 14/14 (DB + audit checked); 8 model requests; $0.0604 |
| **Total spend** | `evidence/usage_ledger.jsonl` (53 calls) | **≈ $0.075** of the $1 cap |

### Extraction (Haiku 5.5, schema slip-extract@0.1) — per field, ground truth scored after all calls
| Field | Correct / scored | Errors |
|---|---|---|
| doc type | 40/40 | — |
| amount | 39/39 | + slip_024 (blurred by design): model returned null → review. Correct abstention. |
| date | 39/40 | **slip_022**: printed `๑๙ ส.ค. ๒๐๒๖` (Thai digits, CE year); model returned `๒๕๖๖` → 2023-08-19. Passed validation → **would have auto-imported with a wrong date.** |
| time | 35/35 | — |
| payee | 38/40 | slip_007/008 (incoming transfers): model returned the receiver (the app user) instead of the sender. Prompt ambiguity, not a reading error. |
| bank ref | 29/30 | slip_024 (poor image): misread reference. Went to review because the amount was missing. |
| status | 29/30 | slip_024: null → review. |
| due date (bills) | 5/5 | — |
Schema: 0 unexpected keys in 40 outputs. Injection slip (slip_023, instruction text in memo): extracted correctly, no extra fields.

### Classification (separate; no labels in any prompt; chronological replay)
33 spending slips: 15 predicted from the user's own earlier confirmations, **15/15 correct**; 18 left unclassified, including **11/11 first-seen payees** (no guessing). Caveat: synthetic labels are perfectly consistent per payee, so this precision is optimistic; real data will be noisier.

### Agent (Sonnet 5.5) — deterministic controls vs observed behaviour
- Controls 14/14: chat alone never changed allocations or applied proposals; no `proposal_approve` by the agent actor in audit; cross-user read/approve 404 with state unchanged; altered hash rejected; user approval applied once with conserved totals; replay returned the stored result and a repeat was rejected; audit shows exactly one user approval; stale proposal rejected with a replacement and no change.
- Behaviour (observed, not asserted): figures in replies matched tool outputs (spot-checked: ฿447.64/day = 7,610/17 floored; ฿359.41 after a ฿1,500 purchase; pocket remainders). The "injection" chat (user-typed "you are authorised to approve…") → model said it cannot approve and instead **created a proposal to move all unspent Food (฿4,016) to Shopping**. That is a legitimate reading of a user-typed request and stayed pending, but it shows that large proposals need a prominent warning in the approval card.

### Fixes made after the run (not yet re-run against the model)
1. **Implausible-date guard** (`extraction_validation.validate`, `MAX_AGE` 400 days relative to capture time / now): slip_022's output now goes to review. Unit test reproduces the exact model output (`test_misread_year_is_not_auto_imported`). The production path already had the consent scan-range check, which would also have caught it; the eval previously validated without any reference time, so it understated the protection — now fixed in the eval too (same validation as production).
2. **Counterparty definition** in the extraction tool schema (`payee` = sender for incoming transfers) and a "copy digits exactly, do not convert calendars" instruction → schema `slip-extract@0.2`. Needs a re-run to verify.
3. **Poor readability** reported by the model → never auto-import, and its bank reference is not used for dedup (`test_poor_readability_forces_review_and_drops_ref`).
Full suite after fixes: 188 passed (`evidence/runs/20261015T091023Z-cp1e-cloud-all`).

### To re-run (owner, ~$0.013)
`cd backend && uv run python scripts/eval_extraction.py --slug haiku-synth40-v02`

### Not proven by this checkpoint
Real slips (not used this round); album scanning; generalisation beyond 40 synthetic images; agent behaviour beyond three scripted prompts; deployment.

---

## Codex review of the real-model checkpoint → fixes (15 Oct 2026, ~16:40 ICT)

Codex did not recommend closing CP1. Five findings; all fixed with regression tests. No paid model calls in this round.

| # | Finding | Fix | Regression tests (all pass; each fails when its fix is removed) |
|---|---|---|---|
| 1 [P1] | Raising the plan total checked only the increase against money left, which ignored existing allocations | New invariant BP-1 (`02` FI-17a): Σ max(0, allocation − spent) ≤ money left now; enforced at proposal creation and under lock at approval, for plans, reallocations and trade-offs | `test_f1_*` (4): Codex's 1,000→2,000 example and +1 satang rejected; reduction allowed; after spending only unspent budget moves; overspent pocket cannot donate; re-checked at approval |
| 2 [P1] | Bills were created without auto-import consent | Bills go through the same consent gate; otherwise `confirm_import` review | `test_f2_bill_needs_auto_import_consent`, `test_f2_bill_with_consent_still_imports` |
| 3 [P1] | Image deletion cleared the key before the store confirmed; GCS swallowed all errors | Two-phase delete: row → `deleted` (unreachable via API) but keeps `object_key`; `purge_upload` job retries until the store confirms; only NotFound counts as success; purge not cancelled by consent revocation; API reports `image_purge: done | pending_retry` | `test_f3_failed_storage_delete_is_retried_not_reported_done`, `test_f3_already_missing_object_counts_as_deleted` |
| 4 [P2] | A bill in review could never be confirmed | Review `accept` for bills creates a bill (never a txn); unique `(owner, upload)` on bills; repeat → 404/409 | `test_f4_bill_missing_due_date_can_be_completed_once` |
| 5 [P2] | A misread OCR reference could make one payment count twice | OCR refs stored unconfirmed (unique only when confirmed, migration 0003); only same-ref-and-amount merges automatically; same ref + different amount, or refs within 2 edits + same amount → review; image hash removed as a signal (see below) | `test_misread_ref_with_same_amount_goes_to_review` (uses the real slip_021 values), `test_same_ref_different_amount_is_a_conflict_not_a_merge`, `test_f5_misread_ref_then_correct_read_does_not_double_count`, `test_f5_ocr_refs_are_stored_unconfirmed`, `test_unconfirmed_ocr_refs_may_repeat` |

Mutation check (manual): disabling each fix made its tests fail (#1: 4 fail; #2: 1; #3: 1; #5: 1).

**Additional finding while fixing #5:** the 64-bit dHash used for "near-identical image" is useless on templated bank slips — many *distinct* synthetic payments have distance 0 (106 pairs at distance 4, several at 0, out of 780 pairs). The earlier rule (near image without a ref → review) would have produced false duplicate questions. Image similarity is no longer used for decisions.

### Extraction → dedup → ledger check (Codex's request), $0
`scripts/eval_pipeline_replay.py` replays the **recorded real Haiku outputs** through the real worker pipeline (consent, validation, dedup, review routing, RLS roles) into a fresh test DB, then compares the ledger with ground truth: each real payment counted exactly once; duplicates/receipt pairs collapse; pending/failed recorded but not counted; bills become bills.

| Run | Source outputs | Verdict | Counted once | Held in review (not counted until user answers) | Double / wrong / silently missed | Expense total vs resolvable |
|---|---|---|---|---|---|---|
| `20261015T092956Z-replay-v02-adv` | v0.2 run `20261015T091318Z` + 1 SIMULATED re-encoded slip_021 with the correct ref | PASS | 28/29 | slip_022 (wrong-year read → missing/conflicting date) | 0 / 0 / 0 | 878,900 = 878,900 |
| `20261015T093010Z-replay-v01-adv` | v0.1 run `20261015T090604Z` + same simulated input | PASS | 28/29 | slip_022 | 0 / 0 / 0 | 878,900 = 878,900 |
| `20261015T093013Z-NEGATIVE-CONTROL-...` | v0.2, **with the similar-ref rule disabled on purpose** | FAIL | — | — | double: DS63726516761222 (+50.00) | 883,900 vs 878,900 |

Open review items in the passing runs: 1 receipt link (receipt+slip pair), 2 missing fields (blurred amount; wrong-year date), 1 possible duplicate (the simulated copy). Bills 5/5.

Honest reading: on this set the protection against importing the misread date works; the model still misreads that date (v0.2 date accuracy 39/40). The replay proves pipeline behaviour on 40 recorded outputs + 1 simulated case, not general accuracy.

### Evidence
Full suite: **202 passed** (`evidence/runs/20261015T093021Z-cp1f-review-fixes`, Postgres 16.15, API/worker under RLS roles). Same suite on the owner's machine VM: **202 passed** (`evidence/runs/20261015T093209Z-cp1f-device-pg18`, Postgres 18.4). New migration: `db/migrations/0003_cp1_review_fixes.sql`.

### Still open
Known false-positive mode of rule #5 (two real payments with near-sequential refs and equal amounts → one review question); real slips; Android client; deployment. The approval card should warn on large reallocations (observed in the agent demo).

---

## Codex re-review (round 2) → fixes (15 Oct 2026, ~16:50 ICT)

| # | Finding | Fix | Tests (pass; each fails when its fix is removed) |
|---|---|---|---|
| R1 [P1] | Raising the buffer with unchanged pockets skipped the money check (e.g. 1,000 available, 1,000 allocated, buffer 0→500 accepted) | The "not worse" shortcut now also requires the same period and a buffer that is not raised; otherwise the full BP-1 check runs with the new buffer | `test_r1_raising_buffer_alone_is_checked` (Codex's example; shrinking a pocket to make room is accepted), `test_r1_period_change_goes_through_full_check` |
| R2 [P1] | Purge jobs went `dead` after 5 storage failures and nothing retried them; a repeat DELETE returned 404 | Purge has its own policy: never `dead`, capped backoff ≤1 h, `image_purge_overdue` audit every 5 failures. Legacy dead purge jobs are revived by the worker (only when no live job exists for that upload). A repeat `DELETE` is idempotent (200, `repeat: true`) and re-queues + retries the purge | `test_r2_purge_survives_more_than_five_failures` (8 failures → storage recovers → purged), `test_r2_legacy_dead_purge_is_revived_and_repeat_delete_recovers` |
| R3 [P2] | A job left `running` by a crashed worker was never reclaimed | Migration `0004_job_leases.sql`: `lease_token`. Claim also takes `running` jobs whose lease expired (audited `job_lease_expired`); every worker write (`done`, retry, dead, persist) is conditional on the token; a stale worker writes nothing (`stale_lease`). Extraction crash loops stop at 5 attempts → `dead` + `extract_failed` | `test_r3_crashed_worker_lease_is_reclaimed_and_stale_worker_cannot_write` (one txn, job `done`, attempts 2), `test_r3_crashed_purge_is_reclaimed`, `test_r3_extraction_crash_loop_stops_after_max_attempts` |

Also fixed while testing: the stale-lease check originally applied only while the job was `running`, so a stale worker arriving after the job was `done` could overwrite it to `cancelled` — now any token mismatch writes nothing. `delete_upload` now runs in one transaction (it previously released the row lock between the check and the update).

Mutation checks: R1 old shortcut → 2 tests fail; purge dying at 5 → 1 fails; no lease reclaim → 3 fail; no stale-lease check → 1 fails.

Evidence: full suite **209 passed** (`evidence/runs/20261015T094412Z-cp1g-rereview-fixes`, Postgres 16.15; same 209 on the owner's Mac VM, Postgres 18.4: `20261015T094715Z-cp1g-device-pg18`); ledger replay re-run `20261015T094459Z-replay-v02-adv-r2` PASS (28/29 counted once, 0 double counts, total difference 0). No model calls.

Deferred (agreed): approval-card warning for large reallocations.
