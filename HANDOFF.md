# HANDOFF — read this first

## TL;DR (15 Oct 2026, ~21:00 ICT, CP3a — Android client skeleton submitted for Codex review)
- Internal acceptance deadline: **16 Oct 2026** (team review). Official submission: 20 Oct 22:59 ICT.
- **CP2 accepted by Codex review** (after cp2b/cp2c fixes). CP3a review request: `docs/design/09-cp3a-review-request.md`.
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
1. Codex review of CP3a (`docs/design/09`); owner runs the device checklist in `android/README.md`.
2. Team: confirm card warning thresholds (`card-policy@0.1`) or change them.
3. After CP3a review: CP3b (album scan + permissions + candidate filter FP/FN on synthetic images, background work, chat/approval cards, lifecycle). Later: redacted real slips (D7), GCP deployment (paid, after approval).
4. Update `06` and this file after each run.

## Open risks
- `scripts/local_pg.py` / `dev_server.py`: pgserver could return before Postgres accepted connections on a cold start (DB tests skipped once, dev server failed once; kept with NOTE.md). Now retried for 30 s. Still check `skipped: 0` in every device manifest.
- Album scanning (R2.1/R2.3/R9.4) needs an Android client; backend tests cannot prove it.
- Proposal staleness is strict (any data change invalidates pending proposals): safe but may cause refreshes in the demo.
- Thresholds N_MIN=2, P_MIN=80% are placeholders until tuned on a dev split.
