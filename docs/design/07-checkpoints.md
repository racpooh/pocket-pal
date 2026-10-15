# 07 — Implementation checkpoints (for Codex review)

Times are ICT. Each checkpoint ends with: code + tests that actually ran + an evidence run + updated `HANDOFF.md`. A checkpoint that misses its exit is reported as missed; scope is not silently reduced.

| CP | Target window | Claude implements | Codex reviews | Exit evidence |
|---|---|---|---|---|
| CP0 (this) | 15 Oct afternoon | Requirements baseline, design docs, API/state contracts, schema draft, money/period/allocation core with tests, repo layout | Financial semantics FI-*, permission tiers, schema constraints, classification stance | Unit + schema tests run; this checklist |
| CP1 | 15 Oct evening → 16 Oct morning | Auth (signup/login/session), repositories with owner scope, migrations runner, transactions/bills/pockets/balance observations, ledger + cash-flow waterfall, proposal/approve with idempotency | Waterfall reconciliation, duplicate paths, approve transaction, cross-user test list | CALC-*, SEC-OWN-*, SEC-APR-*, INT-CONC-01 run on Postgres |
| CP2 | 16 Oct | Upload endpoint, job table + worker, extraction provider (fake + real once D2), validation, dedup, review items, consent grant/revoke/delete, classification suggestion | Injection boundary, revoke/retry races, validation rules | SEC-CONS-*, SEC-INJ-* (fake), INT-DUP-*; one real-model extraction run on synthetic slips |
| CP3 | 17 Oct | Agent loop + tools (T0–T2), affordability, goals feasibility + alternatives, insights (overspend, shortage, recurring bills), RLS layer | Tool registry, agent eval scenarios, goal math | Agent eval run (real model); E2E-01 via API |
| CP4 | 18 Oct | Fix findings; deployment (D4); classification/extraction eval; evidence runner | Re-run affected; self-assessment draft review | Eval report; deployed sandbox |
| CP5 | 19–20 Oct (before 22:59) | Docs, security self-assessment, README/deploy steps, evidence bundle; support deck/video | Final review, known-risk list | Submission package |

Feasibility: CP1 is the riskiest for the original 16 Oct target; with answers to D1/D2/D5/D6 today, CP1 by 16 Oct midday and CP2 by 16 Oct night is plausible but tight. Mobile album scanning depends on a parallel client effort (D3) and is not covered by these checkpoints.

## Decisions requested from Codex at CP0
1. Accept or amend FI-9 (same-day cutoff) and FI-21 (one payment per bill).
2. Accept strict data-watermark staleness for proposals (simple, may cause extra refreshes) vs dependency-specific staleness.
3. Accept the classification stance in `04` (no extra model; LLM hint not counted as `predicted`).
4. Accept per-owner advisory lock for manual/import races (FI-30).
5. Review `db/migrations/0001_core.sql` constraints.
