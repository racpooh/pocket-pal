# HANDOFF — read this first

## TL;DR (15 Oct 2026, ~16:20 ICT, CP1 — real-model checkpoint done, waiting for Codex review)
- Internal acceptance deadline: **16 Oct 2026** (team review). Official submission: 20 Oct 22:59 ICT.
- Decisions D1–D8 answered (see `docs/design/00 §Decisions`). Provider: Anthropic (Haiku extraction, Sonnet chat). Deploy proposal: GCP (pending account).
- Backend implemented: auth/isolation, consent, upload→extract→validate→dedup→import/review, ledger, bills, cash-flow waterfall, pockets, proposals/approvals with idempotency, goals feasibility, affordability, chat agent (T0–T2 tools).
- Evidence: `evidence/runs/20261015T081619Z-cp1d-cloud-all` — 186 tests (API/worker under RLS roles; fail-closed config) passed on Postgres 16.15 (extraction = fake provider, chat = scripted model). Sandbox scenario `20261015T072919Z-demo-fake-mocks-rls` — 47 API steps, all expected.
- **Not proven yet:** real-model extraction accuracy, real agent behaviour, album scanning on Android, encryption at rest (no deployment). Dockerfile written but not built (no Docker daemon in the build sandbox).

- Real-model checkpoint run by the owner (Cowork VM proxy blocks keyed calls): Haiku extraction on 40 synthetic slips, Sonnet agent demo 14/14 controls; total ≈ $0.075. One wrong-date auto-import found and guarded; prompt fixed (schema 0.2) — re-run pending. Details: `docs/design/08` (Results).

## Next steps
1. Owner re-runs `uv run python scripts/eval_extraction.py --slug haiku-synth40-v02` to verify schema 0.2; then Codex review of `docs/design/08`.
2. Done since: insights (3-month history, recurring charges, bill changes, pace alerts, recommendations + goal impact), trade-off proposals, spending report. Remaining partials listed in `06`.
3. Deployment: follow `deploy/gcp.md` once a GCP project with billing exists; capture config as evidence.
4. Update `06` statuses and this file after each run.

## Open risks
- Album scanning (R2.1/R2.3/R9.4) needs an Android client; backend tests cannot prove it.
- Proposal staleness is strict (any data change invalidates pending proposals): safe but may cause refreshes in the demo.
- Thresholds N_MIN=2, P_MIN=80% are placeholders until tuned on a dev split.
