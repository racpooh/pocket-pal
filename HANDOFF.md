# HANDOFF — read this first

## Gallery scan fix round 1 (17 Oct 2026, Claude) — "only 2 photos" diagnosis
**TL;DR:** The monitor counted only photos whose MediaStore `DATE_TAKEN` is inside 30 days (2), and both were marked by the v1 English-only filter, so it could not show *why* 20+ prepared slips were absent. Likely causes, not yet proven on the phone: (a) selected-photos access covering only some photos, (b) slips with no capture date (images saved/copied from another app usually lack EXIF date → `DATE_TAKEN` null → excluded by design), (c) capture date older than 30 days, (d) Thai slips rejected by the v1 English-only filter. Implemented: metadata-only census (visible / undated / older / future / in-window, permission mode), split seen-cache counters, and local filter **v2** (adds a language-independent slip-layout rule: amount with satang + masked account or long reference + `HH:MM` time or BE year). Photos marked by v1 are re-read **locally** once; a content-hash match with an earlier accepted upload is skipped and never re-sent; new marks are `acc:` / `rej:` (422) / `flt:v2:`. Undated photos are still never sent automatically and `DATE_ADDED` is not substituted; caps unchanged (100 local / 10 attempts per run, 20/day). APK versionCode 2 (`0.2.0-gallery`).

Tested: `20261017T020449Z-pocketpal-scanpolicy-v2-cloud` (8/8 JUnit, synthetic strings, cloud); web `tsc --noEmit` passed in device VM. Not verified: APK compile of GalleryWorker/ScanStore (owner's Mac Gradle), mocked browser smoke (Mac-only), real scan on S22 Ultra, end-to-end OCR→Activity/Review→Chat, v2 image FP/FN (no benchmark). Originals of the changed files kept at `.sync/pp-orig-v1/`. No paid calls, no real images read by Claude, no Git, no reset.

## Scan observability update (17 Oct 2026, Codex)
**TL;DR:** Added persisted per-scan stages and counters in native Settings, plus `PocketPalScan` logcat events containing only fixed stage codes, timestamps, counters and HTTP status. Existing phone state showed zero attempts and two previously marked metadata entries; this does not establish total album size or why those photos were skipped. Latest scans previously hid this distinction. Monitor now separates accessible dated photos, already checked, unsupported, consent-window skips, local checks, filtered-out candidates and server acceptances. Unknown capture dates remain excluded; local heuristic and upload policy unchanged. APK updated with `-r`, preserving user data. No paid calls or real-image reads by Codex; user-triggered end-to-end scan acceptance is still pending.

Evidence: `20261017T015209Z-pocketpal-apk` build and existing policy tests; `20261017T015210Z-web-build` typecheck/build; `20261017T015252Z-native-controls-browser` four mocked UI checks and installation record. Sandbox-limited build `20261017T015153Z-pocketpal-apk` retained with NOTE. Web 3002 restarted against gallery 8002. Scan monitor values appear after the next scan; server acceptance is not completed OCR/import.

## Phase 1.1 + Phase 2 trial (17 Oct 2026, Codex)
**TL;DR:** Conversation continuity implemented (tab memory; explicit consent for saved context/history; New chat; owner/late-result isolation). Separate Pocket Pal APK `dev.finassist.pocketpal` built and installed/launched on S22 Ultra, with 30-day gallery scanning OFF and photo permissions denied. Fresh `gallery` profile (8002) + web (3002) verified zero users/slips/transactions/files; original dev and Gallery originals untouched. No real-image reads, paid calls or Git commands. Backend 300 passed + 2 existing reference xfails; browser 5 conversation + 3 mocked bridge checks; APK 4 policy tests and build passed. Physical gallery, filter image accuracy, native revoke/restart/background acceptance remain pending—do NOT mark CP3b complete. See `docs/design/16-conversation-gallery.md` for evidence and `android/POCKETPAL_GALLERY.md` for the owner's morning steps. Local services/USB are required; this is not a cloud-hosted standalone release. Delegated implementation/review hit usage limits; Codex main finished guards, verification, installation and handoff.

## Phase 1 update (17 Oct 2026 ICT, Codex)
**TL;DR:** Chat now renders safe Markdown and receives explicit budget/date context. Pockets show their date window and offer a human-approved increase with proportional tradeoffs. 25 focused backend tests passed (`20261016T174645Z-phase1-backend`); five synthetic mocked browser checks passed (`20261016T174520Z-phase1-browser`); production build passed (`20261016T174704Z-web-build`). No paid calls, Git commands, real-image reads or dev resets. Original UI source repo untouched. Restart backend and web to load changes; owner must evaluate new Chat questions. No claim about real-model quality from mock tests. Arbitrary pocket target editing remains out of scope for this slice. Phase 2 APK/gallery last-30-day scanner is assessed but not implemented; see doc 15.

## Web integration update (16 Oct 2026, Codex)

**TL;DR:** Pocket Pal web is connected to the backend in `web/`, preserving the source UI structure. Final build `20261016T170510Z-web-build` passed; HTTP smoke 15/15; browser `20261016T170403Z-web-browser-smoke` 9 steps including approved buffer; full backend `20261016T170440Z-web-plan-supersession` 294 passed, 2 existing reference xfails. Original pocket-pal repo untouched. Existing Anthropic key stays backend-only; no paid calls in verification. Owner approved web on S22 tonight. Fixed latest-plan selection and source-free logging after runtime tests. Physical-device web and paid Chat acceptance remain. Web is on localhost:3000, USB forwarded; owner must restart the existing dev Anthropic backend without --reset to load backend fixes. See `docs/design/15-web-integration.md` and `web/README.md`.


**Codex targeted Slice 1 fix review (16 Oct 2026):** Original required-input and negative-money findings closed at source/automated-evidence level. Core 35/35 and E2E 34/34 in existing VM evidence; backend evidence 290 passed with 2 reference strict xfails (not accepted controls). Owner reports successful build/install on SM-S908E / Android 14. Device S1–S18 remains pending; no overall CP3 acceptance. Review provenance: `evidence/runs/20261016T141918Z-slice1fix-codex-review/manifest.json`. No tests rerun by Codex for this review.

## Codex reference checkpoint (16 Oct 2026; parallel to Claude UI integration)
- Contract proposal: `docs/design/14-reference-contract.md`. Existing HTTP/provider schema and Android unchanged; no model calls, Git commands, private-image access or dev DB changes.
- Synthetic domain evidence `20261016T122231Z-reference-contract-regressions`: 57 passed, **2 strict xfailed OPEN gaps**. Running without xfail yields 2 failed / 8 passed in the new test file. Existing validation tests included. No DB pipeline run.
- REF-GAP-1: alternate printed reference fields can create a second payment. REF-GAP-2: reused/untyped equal identifier at equal amounts can merge distinct payments. These are not fixed. General dedup safety is NOT accepted.
- Next implementation: review and activate typed reference persistence/mapping plus worker candidate retrieval and DB regressions. Claude continues UI slice 1 against existing APIs; coordinate backend edits before implementation.

## TL;DR (16 Oct 2026, ~20:45 ICT — slice 1 fixed after Codex review: review inputs for due date/status/type (no defaults), signed money formatting; core 35/35, E2E 34/34, backend 290 on this machine; app NOT compiled here; test phone is Galaxy S22 Ultra SM-S908E / Android 14, not S23; see `docs/design/13` §7)
- Previous TL;DR: (16 Oct 2026, ~19:05 ICT — R2 unseen pilot scored (`20261016T120301Z-real-slip-r2-score`): freeze intact; all fields except bank_ref 5/5; 5 auto-imported right, 0 unsafe; ledger 5 counted once; bank_ref 0/5 unresolved pending owner image check on the Mac (`docs/design/12` §6); R1 revised kept separate)
- **Real-slip r1:** `docs/design/12` §4. Baseline replay `20261016T110650Z-real-slip-r1-score` (1 counted, 4 held in review because of the parser); after fix `20261016T110739Z-real-slip-r1-score` (5/5 counted once, 0 unsafe, 0 double). Backend 269 passed `20261016T110910Z-r1-dateparser-backend-device-pg18-arm64`. Owner to write labels.v2.csv (UTF-8) from the images.
- **Environment isolation + real-slip eval:** `docs/design/12-real-slip-eval.md`. Profiles dev (phone) / e2e / test / realeval each have their own cluster, DB, roles, storage, port (`backend/scripts/local_envs.py`; `dev_server.py --profile` now required). Evidence: isolation 15/15 `20261016T082236Z-env-isolation-device-pg18-arm64`; backend 257 passed, skipped 0 `20261016T083337Z-env-isolation-backend-device-pg18-arm64`; harness self-test `20261016T083101Z-real-slip-harness-selftest`. Real round r1 (5 images) prepared in `eval/private/real-r1/` (gitignored); needs owner labels + approval to send to Anthropic ($0.10 cap).
- Internal acceptance deadline: **16 Oct 2026** (team review). Official submission: 20 Oct 22:59 ICT.
- **CP2 accepted by Codex review** (after cp2b/cp2c fixes). CP3a review request + fixes: `docs/design/09-cp3a-review-request.md`. D3a (Kotlin/Compose) accepted by Codex.
- S23 user-reported results (16 Oct): `docs/design/10-cp3a-device-results.md` (lines 5,6,8,12,15,19 pass; 4,10,11,14,16,17,18 untested; steps there). CP3b design + acceptance tests: `docs/design/11-cp3b-design.md` (not implemented).
- CP3a re-review 2: a late 401 of an older session no longer clears the new token or ends the new session (`clearIf`, `staleToken`, epoch in `SessionGate.finish`). Core 27/27, E2E 27/27 (`20261015T172759Z-cp3a-stale401-client-e2e-cloud`). Owner's build of pre-gate sources: BUILD SUCCESSFUL.
- CP3a re-review: `SessionGate` — screens and queue only after `/me` + bind; Retry on failure; late `/me` ignored. Core 25/25, E2E 27/27 (`20261015T164817Z-cp3a-gate-client-e2e-cloud`); backend 257 (`20261015T164958Z-cp3a-gate-backend`); ARM64 VM: core/E2E 25/25, 27/27 (`20261015T165304Z-cp3a-gate-client-e2e-device-pg18-arm64`). Owner's first `assembleDebug` produced an APK from the pre-gate sources (rebuild needed).
- CP3a fixes: queue bound to the signed-in account (`GET /v1/me`, `expected_owner_id`), pause effective mid-batch, review decisions from the server (`allowed_decisions`), undated photos need explicit confirmation. Backend 257 passed (`20261015T141505Z-cp3a-fix-backend`); client core 22/22 + E2E 26/26 (`20261015T140955Z-cp3a-fix-client-e2e-cloud`); same in the Linux ARM64 VM on the Mac, PG 18.4 (`20261015T141840Z-cp3a-fix-backend-device-pg18-arm64`, `20261015T141923Z-cp3a-fix-client-e2e-device-pg18-arm64`).
- CP3a: `android/` (native Kotlin + Compose, D3a proposal). The pure-Kotlin `core` (API client, upload queue) is compiled
  and tested here: self-tests 17/17 and E2E vs the real backend 22/22 (`evidence/runs/20261015T134438Z-cp3a-client-e2e-cloud`).
  Backend suite 253 passed, DB enabled, skipped 0 (`20261015T134610Z-cp3a-backend`). Same results in the Linux ARM64 VM on the owner's Mac, PG 18.4 (`20261015T135038Z-cp3a-backend-device-pg18-arm64`, `20261015T135405Z-cp3a-client-e2e-device-pg18-arm64`).
- **Not built or run on Android yet**: neither environment here can reach Google Maven / the Android SDK. Owner steps:
  `android/README.md` (build on the Mac, `adb reverse`, 14-line device checklist).
- Backend now has **no default model provider**; start servers with `--provider fake` (dev/test) or `anthropic` explicitly.

### Status
| Area | Implemented | Tested (evidence) | Not verified |
|---|---|---|---|
| Backend core (auth/RLS, consent, upload→extract→validate→dedup→import/review, ledger, bills, waterfall, pockets, proposals/approvals, goals, insights, chat agent T0–T2) | yes | suite `20261015T120215Z-cp2-cards-gaps` 236 passed (x86_64, PG 16.15); same 236 in the Linux ARM64 VM on the owner's Mac, PG 18.4, `20261015T120443Z-cp2-device-pg18-arm64` (not native macOS) | anything needing a deployed server or a client |
| Approval card contract (`05 §5`, FI-31..35) | yes (backend) | `test_cp2_cards.py`; examples `20261015T120156Z-card-examples` (11/11) | final UI; thresholds are provisional product policy |
| `/data/delete`, `goal_update`, chat retention, PATCH /transactions, app-log redaction | yes | `test_cp2_gaps.py` (14) | GCS store; deployed log config |
| Real-model extraction | yes | 40 synthetic slips, Haiku (`20261015T091318Z-haiku-synth40-v02`); replay `20261015T120337Z-replay-v02-adv-cp2` 0 double counts | real (redacted) slips; generalisation |
| Real agent | yes | Sonnet run `20261015T090742Z-agent-sonnet` 14/14 DB-checked controls | behaviour beyond 3 prompts |
| Android client (CP3a) | core + app code | core: self-tests 17/17, E2E 22/22 vs real backend (`20261015T134438Z-cp3a-client-e2e-cloud`) | APK build, screens, Photo Picker, Keystore on device |
| Album scan, background, chat/approval in app (CP3b), encryption at rest | no | — | all |

All suites use FAKE extraction and SCRIPTED chat; test counts are regression coverage, not a competition score.

## Next steps
1. Owner: run the remaining device lines in `docs/design/10` (~20 min) with the latest build; report per line. Then Codex decides on closing CP3a.
2. Team: confirm card warning thresholds (`card-policy@0.1`) or change them.
3. After CP3a review: CP3b (album scan + permissions + candidate filter FP/FN on synthetic images, background work, chat/approval cards, lifecycle). Later: redacted real slips (D7), GCP deployment (paid, after approval).
4. Update `06` and this file after each run.

## Open risks
- Before 16 Oct ~15:30 all local scripts shared one pgserver cluster and rotated the shared role passwords (and the E2E defaulted to the phone's port); Claude's runs once wiped the phone's synthetic data (`10` note). Now separate profiles (`12` §1). The phone's data moves to the new `pgdata-dev` cluster: one `--reset` start needed.
- `scripts/local_pg.py` / `dev_server.py`: pgserver could return before Postgres accepted connections on a cold start (DB tests skipped once, dev server failed once; kept with NOTE.md). Now retried for 30 s. Still check `skipped: 0` in every device manifest.
- Album scanning (R2.1/R2.3/R9.4) needs an Android client; backend tests cannot prove it.
- Proposal staleness is strict (any data change invalidates pending proposals): safe but may cause refreshes in the demo.
- Thresholds N_MIN=2, P_MIN=80% are placeholders until tuned on a dev split.
