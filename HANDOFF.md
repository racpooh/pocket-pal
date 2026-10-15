# HANDOFF — read this first

## TL;DR (15 Oct 2026, ~20:20 ICT, CP2 — Codex CP2 findings fixed incl. re-review P2 (hard delete of one transfer leg), waiting for Codex)
- Internal acceptance deadline: **16 Oct 2026** (team review). Official submission: 20 Oct 22:59 ICT.
- Decisions D1–D8 answered (`docs/design/00 §Decisions`). Provider: Anthropic (Haiku extraction, Sonnet chat). Deploy proposal: GCP (not executed).
- Codex accepted CP1 round-2 fixes (R1–R3) and the CP2 card design; its three CP2 findings (transfer leg status, approval vs concurrent ledger change, worker log messages) are fixed: `docs/design/08` section "Codex CP2 review → fixes". Re-review P2 (trigger missed a hard `DELETE` of one leg) fixed in migration 0007. Latest suite `20261015T131509Z-cp2c-transfer-pairs`: 248 passed; same 248 in the Linux ARM64 VM on the owner's Mac, PG 18.4 (`20261015T131712Z-cp2c-device-pg18-arm64`).

### Status
| Area | Implemented | Tested (evidence) | Not verified |
|---|---|---|---|
| Backend core (auth/RLS, consent, upload→extract→validate→dedup→import/review, ledger, bills, waterfall, pockets, proposals/approvals, goals, insights, chat agent T0–T2) | yes | suite `20261015T120215Z-cp2-cards-gaps` 236 passed (x86_64, PG 16.15); same 236 in the Linux ARM64 VM on the owner's Mac, PG 18.4, `20261015T120443Z-cp2-device-pg18-arm64` (not native macOS) | anything needing a deployed server or a client |
| Approval card contract (`05 §5`, FI-31..35) | yes (backend) | `test_cp2_cards.py`; examples `20261015T120156Z-card-examples` (11/11) | final UI; thresholds are provisional product policy |
| `/data/delete`, `goal_update`, chat retention, PATCH /transactions, app-log redaction | yes | `test_cp2_gaps.py` (14) | GCS store; deployed log config |
| Real-model extraction | yes | 40 synthetic slips, Haiku (`20261015T091318Z-haiku-synth40-v02`); replay `20261015T120337Z-replay-v02-adv-cp2` 0 double counts | real (redacted) slips; generalisation |
| Real agent | yes | Sonnet run `20261015T090742Z-agent-sonnet` 14/14 DB-checked controls | behaviour beyond 3 prompts |
| Android client, album scan, encryption at rest | no | — | all |

All suites use FAKE extraction and SCRIPTED chat; test counts are regression coverage, not a competition score.

## Next steps
1. Codex re-review of `docs/design/08` "Codex CP2 re-review → fix". No paid runs needed.
2. Team: confirm card warning thresholds (`card-policy@0.1`) or change them.
3. After CP2 closes: redacted real slips (D7, private, not in Git), Android client spike, GCP deployment (paid, after approval).
4. Update `06` and this file after each run.

## Open risks
- `scripts/local_pg.py` sometimes returns no URL on its first start in the owner's VM; DB tests are then skipped (one invalid run kept with NOTE.md). Check `skipped: 0` in every device manifest.
- Album scanning (R2.1/R2.3/R9.4) needs an Android client; backend tests cannot prove it.
- Proposal staleness is strict (any data change invalidates pending proposals): safe but may cause refreshes in the demo.
- Thresholds N_MIN=2, P_MIN=80% are placeholders until tuned on a dev split.
