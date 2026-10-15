# 01 — Architecture (proposed)

Status: **Proposed**, awaiting Codex review and decisions D1–D8 in `00`.

## 1. Shape

One backend codebase, two processes, one database, one private bucket. No microservices, broker, vector DB or agent framework.

```
 Mobile app (out of this round)                Backend (this repo)
 ┌──────────────────────────┐   HTTPS   ┌──────────────────────────────────────────┐
 │ album filter on device   │──────────▶│ api process (FastAPI)                    │
 │ (QR / screenshot heur.)  │  JSON +   │  http/  → services/ → domain/ (pure)     │
 │ consent screens          │  images   │             │           ▲                │
 │ cards: Approve/Edit/Cancel│◀─────────│             ▼           │                │
 └──────────────────────────┘           │         repositories ── Postgres 16 ◀──┐ │
                                        │             │                          │ │
                                        │             └── object store (private) │ │
                                        │ worker process (same code)             │ │
                                        │  polls `job` (SKIP LOCKED) ─────────────┘ │
                                        │  calls ModelProvider (extraction, chat)   │
                                        └──────────────┬───────────────────────────┘
                                                       │ HTTPS, server-side key
                                                       ▼
                                             External model provider (D2)
```

### Layers and dependency rule

| Layer | Path | May import | Must not import |
|---|---|---|---|
| domain (pure calculations, invariants) | `backend/src/finassist/domain/` | stdlib only | http, db, providers |
| services (use cases, transactions, authorization) | `services/` (next checkpoint) | domain, repositories, providers (interfaces) | FastAPI |
| repositories (SQL, owner-scoped) | **CP1 deviation:** SQL lives in `services/*` (no separate repository layer); every query takes `owner_id` from the session | psycopg | domain decisions |
| providers (model, storage) | `providers/` (next) | httpx/SDK | services |
| http (routing, schemas, error envelope) | `api/` | services | repositories directly |
| worker | `worker/` (next) | services | http |

A test (`tests/unit/test_layering.py`) enforces that `domain/` imports nothing outside the stdlib.

## 2. Stack choice (D1) — recommendation and trade-offs

| Option | For | Against |
|---|---|---|
| **Python 3.12 + FastAPI + Pydantic v2 + psycopg 3 (plain SQL) + Postgres 16** (recommended) | Pydantic validates LLM structured output and API bodies with one schema; OpenAPI generated for mobile; team background in Python/ML; image tooling (Pillow, QR decoding, perceptual hash) is mature; plain SQL keeps constraints/locking visible to reviewers | No shared types with a TS mobile app (mitigate: generate TS client from OpenAPI); async + sync DB discipline needed |
| Node/TypeScript (Fastify or NestJS + Kysely/Drizzle) | Shared types with React Native; NestJS gives DI/guards | NestJS adds ceremony that costs hours with no security gain at this size; image/QR tooling less convenient |
| Managed BaaS (Supabase: Postgres + Auth + Storage + RLS) | Auth, private buckets, TLS, at-rest encryption provided by the platform → strongest R9.2 evidence for least effort | Business logic still needs a server (approvals, jobs, model calls); RLS-heavy design is harder to unit test; vendor lock-in; the claims become "provided by vendor", which must be stated as such |

Hybrid worth considering for D4: this FastAPI backend deployed against a managed Postgres + private bucket (Supabase, Neon + R2, or a cloud provider), keeping auth in our code. This gives real encryption-at-rest evidence without moving logic into the BaaS.

No ORM: the core value is in constraints, row locks and idempotency; raw SQL in repositories keeps them reviewable. Migrations are numbered SQL files applied by a small runner (no Alembic yet).

## 3. Components

### 3.1 Identity and owner isolation
- Email + password (argon2id), opaque random session token (256-bit) returned to the client; only `sha256(token)` stored; expiry + revoke on logout. (D8 may replace with managed auth.)
- `owner_id` is taken **only** from the verified session, never from request bodies, model output or job payloads.
- Every owner-scoped table has `owner_id NOT NULL`; every repository function takes `owner_id` as a required first argument; child rows reference parents via composite FK `(owner_id, id)` so a row cannot point to another user's parent.
- Second layer (**implemented**, `db/migrations/0002_rls.sql`): RLS enabled and forced on every owner table; policy `owner_id = app.owner_id`. The API connects as `finassist_app` (no superuser, no BYPASSRLS) and binds `app.owner_id` from the verified session per request (`infra.set_owner`). The worker connects as `finassist_worker`, which may read all rows of `job` only (to claim work) and binds the job's owner before touching anything else. Integration tests run the API and worker under these roles.
- Object keys are `owners/{owner_id}/uploads/{upload_id}` and are never accepted from clients; download goes through an owner-checked endpoint (or a short-lived signed URL issued after the check).

### 3.2 Consent and data lifecycle
- `consent_grant(owner_id, scope, version, params, granted_at, revoked_at)`. Scopes: `photo_processing` (upload + extraction, incl. disclosure of the external provider), `auto_import` (save without review), `chat_history_retention`.
- Revocation is an UPDATE that sets `revoked_at` under row lock; workers read the grant `FOR SHARE` in the same transaction that persists results, so revoke and persist are serialised.
- Deletion: user-initiated delete of an upload / all imported data / account. Rows marked `deleted_at` then purged by a job; images deleted from the bucket; derived transactions removed or kept per the user's choice (D: default remove auto-imported, keep manual). Backups: disclosed retention window (deployment-specific).

### 3.3 Image ingestion → extraction → validation → dedup → review
State machine in `05-api-contracts.md §4`. Steps:
1. Client uploads a candidate image with `Idempotency-Key`, client-side `sha256`, capture time. Server checks consent, size (≤ 8 MB), MIME by magic bytes (JPEG/PNG/HEIC→convert), recomputes sha256. Exact byte duplicate → returns the existing upload.
2. Job `extract`: re-check consent, call extraction provider with a fixed JSON schema (no tools), store raw structured result + model id + latency + cost; optionally decode QR locally.
3. Deterministic validation (`domain/extraction_validation.py`, next checkpoint): amount parse to satang, date plausibility vs capture time and scan range, direction from document type and wording, status (success/pending/failed), field-level `ok | missing | conflicting`.
4. Dedup (see `02 §7`).
5. Decision: all critical fields ok + auto-import consent + no dedup ambiguity → create transaction `source=auto_import`, `category_state=unclassified|predicted`. Otherwise → review item listing only the problem fields.

### 3.4 Ledger: transactions, bills, balance
See `02-financial-invariants.md`. Key tables: `account`, `balance_observation`, `txn`, `bill`, `bill_payment_link`, `txn_link` (refund-of, duplicate-of, receipt-evidence-of).

### 3.5 Budget / cash-flow engine and goals
Pure functions in `domain/cashflow.py` (next checkpoint) over a snapshot loaded by a service. One waterfall computes reserved lines (bills, essentials, savings/goal contributions, buffer) and the discretionary remainder; pockets and the daily/weekly allowance are views of that single computation, so nothing is reserved twice. Goals call the same projection with a contribution schedule.

### 3.6 Classification and confirmed history
See `04-import-and-classification.md`. SQL over the user's own confirmed rows plus a small seed merchant dictionary; LLM only as a labelled hint for cold start. No model training.

### 3.7 Agent tools and authority
- Single LLM loop with function calling; no agent framework. Max tool calls per turn (8) and per minute.
- Tools are server functions bound to the session's `owner_id` (not a model argument). Tool args validated by Pydantic; unknown fields rejected.
- Tiers (see `03 §2`): T0 read, T1 simulate, T2 propose. No tool approves, deletes, changes consent or moves money.
- Extracted image text reaches the model only as quoted, typed fields inside a data block.

### 3.8 Proposal → approval → atomic execution
- `proposal(owner_id, kind, payload jsonb, payload_hash, base_plan_version, base_data_watermark, status, expires_at, created_by)` — created by the agent or by direct user edits.
- Approve = `POST /proposals/{id}/approve {payload_hash, card_hash}` + `Idempotency-Key`, authenticated user only. One DB transaction: **lock order (Codex CP2 #2): per-owner ledger advisory lock → `owner_watermark` row `FOR UPDATE`** (every ledger writer takes the same advisory lock first and bumps that row in its own transaction, so an uncommitted writer blocks the approval and a later writer waits for it) → lock proposal → check owner/status/expiry/hash → check `plan.version == base_plan_version` and `data_watermark == base_data_watermark` → apply → bump version → mark applied → audit. Any mismatch → `409 PROPOSAL_STALE` with a freshly computed replacement proposal.
- Edit never mutates a proposal; it creates a new one and supersedes the old.

### 3.9 Background jobs, retry and audit
- `job(id, owner_id, kind, subject_id, consent_grant_id, status, attempts, run_after, locked_until, lease_token, last_error_code)`. Worker: `SELECT … FOR UPDATE SKIP LOCKED` over queued-and-due jobs **and running jobs whose lease (5 min) expired**; each claim gets a new `lease_token` and every job-state write by the worker (done/retry/dead, extraction persist) is conditional on it, so a crashed-then-revived worker cannot overwrite. Exception by design: `_purge_object()` (also called from `DELETE /uploads/{id}` without a lease) closes the purge job by owner+upload and clears `object_key` only where it still equals the deleted key; idempotent object deletion makes the first confirmed delete win and later callers no-ops. Extraction: exponential backoff, max 5 attempts (including reclaims), then `dead`. Image purge: never `dead`; capped backoff (≤1 h) and an `image_purge_overdue` audit event every 5 failures; a repeated `DELETE` re-queues it.
- `audit_event(owner_id, actor{user|agent|worker}, action, subject_type, subject_id, result, request_id, at, details_redacted)`. No image content, no raw OCR text, no tokens.

### 3.10 Private storage and secrets
- Dev: local directory outside the web root, served only by the owner-checked endpoint. Deployed: private bucket with server-side encryption (D4).
- Secrets via environment (`.env` only locally, never committed); provider key never sent to the client; logs pass through a redaction filter (tokens, emails, amounts in free text, image bytes).

## 4. What is deliberately not built
Multi-bank connectors, open-banking/FAPI flows, real transfers, autonomous reallocation, message broker, vector DB, separate classifier model, multi-agent orchestration, LINE. Each could be added later without changing the ledger semantics.
