# FinAssist — FinTechathon 2026 International Track, Topic A (Personal Finance Assistant)

**Status (15 Oct 2026, CP1): backend prototype with tests; not feature-complete.** See `docs/design/06-acceptance-and-traceability.md` for what is proven, partial, or not started, and `HANDOFF.md` for the current state.
Implemented: auth + owner isolation, consent grant/revoke, image upload → extraction job → validation → dedup → auto-import or review, ledger (transactions, refunds, transfers, bills paid once), cash-flow waterfall + daily allowance, pockets, proposals → approval with idempotency, goals feasibility, affordability, chat agent with T0–T2 tools.
Also: Postgres RLS as a second isolation layer (API and worker run as restricted roles), insights (3-month history, recurring charges, bill changes, pace alerts, recommendations), trade-off proposals.
Not yet: mobile app/album scanning, real-model evaluation results, deployment (instructions in `deploy/gcp.md`, not executed).

## Repository map

```
docs/                     original sources (do not edit) + design/
  design/00-requirements-baseline.md   confirmed requirements, assumptions, decisions, conflicts, gaps
  design/01-architecture.md            components, layering, stack trade-offs
  design/02-financial-invariants.md    money, balance, transfers, bills, refunds, waterfall, duplicates (FI-*)
  design/03-security-and-permissions.md security invariants (SI-*), permission tiers, threats, privacy
  design/04-import-and-classification.md extraction + category suggestion stance, evaluation questions
  design/05-api-contracts.md           endpoints, error envelope, state machines, chat cards
  design/06-acceptance-and-traceability.md requirement → design → code → test → evidence
  design/07-checkpoints.md             plan for Codex review
backend/
  src/finassist/domain/   pure calculations (stdlib only — enforced by a test)
  src/finassist/api/      FastAPI app (health + error envelope only at CP0)
  db/migrations/          numbered SQL migrations (0001 is a draft)
  tests/unit|api|db/      tests; db tests need a disposable Postgres
  fixtures/synthetic/     synthetic fixtures only (no real slips)
  scripts/record_evidence.py  runs tests and writes an evidence bundle
evidence/runs/            sanitized execution evidence, one folder per run
eval/                     extraction/classification evaluation protocol (private data gitignored)
HANDOFF.md                current state and next steps (read first)
AGENTS.md                 rules for AI collaborators (Claude, Codex)
```

## Run it

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/). Postgres 16 only for DB tests.

```bash
cd backend
uv sync                     # creates .venv with Python >= 3.12
uv run pytest               # unit + API tests; DB tests are skipped without a database
```

DB tests (destructive: they drop and recreate `public` in the target DB; the name must end with `_test`):

```bash
docker compose -f backend/docker-compose.yml up -d     # or any local Postgres 16
cd backend
TEST_DATABASE_URL=postgresql://finassist:finassist@localhost:55432/finassist_test uv run pytest
```

Record an evidence bundle (writes `evidence/runs/<UTC>-<slug>/`):

```bash
cd backend
TEST_DATABASE_URL=... uv run python scripts/record_evidence.py --slug cp0
```

Run the API and worker against a local Postgres (apply the migration first):

```bash
for f in backend/db/migrations/*.sql; do psql "$OWNER_DATABASE_URL" -f "$f"; done   # then create finassist_app / worker logins (see deploy/gcp.md)
cd backend
uv run uvicorn finassist.api.app:app --reload          # API on :8000, OpenAPI at /docs
uv run python -m finassist.worker                       # extraction worker (FINASSIST_MODEL_PROVIDER=fake|anthropic)
```

Or the whole stack with Docker: `docker compose -f deploy/docker-compose.yml up --build` (local only; the compose DB applies 0001 only — run 0002_rls.sql and create roles if you want RLS locally).

Sandbox scenario → execution evidence (synthetic data; resets the `_test` database):

```bash
cd backend
TEST_DATABASE_URL=... uv run python scripts/demo_scenario.py --slug demo-fake                        # mocks
TEST_DATABASE_URL=... uv run python scripts/demo_scenario.py --slug demo-real --provider anthropic   # real model calls
```

Real-model extraction/classification evaluation (needs `FINASSIST_MODEL_API_KEY` in `.env`):

```bash
cd backend
uv run python scripts/eval_extraction.py --set synthetic --slug haiku-synth
uv run python scripts/eval_extraction.py --set private --slug haiku-private   # eval/private/slips + labels.csv (gitignored)
```

Regenerate synthetic slips: `uv run --with pillow --with qrcode python tools/synth_slips.py --out fixtures/synthetic/slips --seed 7 --n 40` (font: Noto Sans Thai, SIL OFL 1.1, `tools/fonts/`).

## Data handling rules
- Never commit real slips, receipts, bank screenshots or personal data. `eval/private/` and `backend/var/` are gitignored.
- Secrets live in `.env` (gitignored). Copy `.env.example`.
- Evidence bundles must not contain images, tokens, or chain-of-thought.

## Submission language
Per competition rules, submissions are in English. Team discussion may be in Thai.


## Android client (CP3a)
See `android/README.md`: stack decision, build on the Mac, run against `backend/scripts/dev_server.py --profile dev --provider fake` via `adb reverse`, device checklist.
