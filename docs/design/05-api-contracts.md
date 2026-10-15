# 05 — API, error and state contracts (for the mobile client)

Status: **Proposed v0**. Visual UI is not designed; these contracts fix the interaction states the UI must support. The generated OpenAPI from FastAPI will become the machine-readable version once routes exist.

## 1. Conventions
- Base path `/v1`. JSON, UTF-8. Auth: `Authorization: Bearer <session token>`.
- Money: `{"amount_satang": 12050, "currency": "THB"}` — clients format; never send floats.
- Time: RFC 3339 with offset; dates `YYYY-MM-DD` interpreted in the user's timezone (returned in `/v1/me`).
- Every mutating request requires `Idempotency-Key` (UUID). Same key + same body → same response replayed. Same key + different body → `422 IDEMPOTENCY_KEY_REUSED`.
- Objects carry `version` (int). Mutations of versioned objects send `If-Match: <version>`; mismatch → `409 VERSION_CONFLICT`.
- Another user's id → `404 NOT_FOUND` (no existence leak).

## 2. Error envelope

```json
{
  "error": {
    "code": "PROPOSAL_STALE",
    "message": "Your budget changed since this proposal was made.",
    "fields": [{"path": "amount", "issue": "missing"}],
    "retryable": false,
    "request_id": "01J…",
    "details": {"replacement_proposal_id": "…"}
  }
}
```

| HTTP | code | Client behaviour |
|---|---|---|
| 400 | `VALIDATION_FAILED` | highlight `fields` |
| 401 | `UNAUTHENTICATED` / `SESSION_EXPIRED` | re-login |
| 403 | `CONSENT_REQUIRED` (`details.scope`) | show consent screen for that scope |
| 404 | `NOT_FOUND` | — |
| 409 | `VERSION_CONFLICT` | reload object |
| 409 | `PROPOSAL_STALE` | show replacement proposal |
| 409 | `PROPOSAL_ALREADY_APPLIED` | show applied result (idempotent outcome) |
| 409 | `POSSIBLE_DUPLICATE` (`details.candidates`) | ask "same as this?" or resend with `confirm_distinct=true` |
| 410 | `PROPOSAL_EXPIRED` | ask assistant to recompute |
| 413/415 | `UPLOAD_TOO_LARGE` / `UNSUPPORTED_MEDIA` | — |
| 422 | `IDEMPOTENCY_KEY_REUSED` | client bug |
| 422 | `NEXT_INCOME_DATE_PASSED` | ask for next income date |
| 429 | `RATE_LIMITED` | retry after header |
| 503 | `MODEL_UNAVAILABLE` (`retryable: true`) | keep record in queue; manual entry still available |

## 3. Endpoints (v0 list)

| Area | Method + path | Tier | Notes |
|---|---|---|---|
| Auth | `POST /v1/auth/signup`, `POST /v1/auth/login`, `POST /v1/auth/logout` | — | |
| Profile | `GET/PUT /v1/me/profile` | T0/T3 | income amount, frequency, next income date, essentials, savings preference, timezone |
| Balance | `POST /v1/accounts/{id}/balance-observations` | T3 | `amount`, `as_of` or `as_of_date` |
| Consent | `GET /v1/consents`, `POST /v1/consents` `{scope, version, params}`, `DELETE /v1/consents/{scope}` | T5 | params: photo scope description, scan date range |
| Uploads | `POST /v1/uploads` (multipart: image, sha256, captured_at) | T4 path | 202 + upload state |
| | `GET /v1/uploads?status=` , `GET /v1/uploads/{id}`, `DELETE /v1/uploads/{id}` | T0/T5 | |
| Scan status | `GET /v1/scan-status` | T0 | last successful scan, counts by state (client reports device-side scan times via `POST /v1/scan-status/heartbeat`) |
| Review | `GET /v1/review-items` (grouped by payee option) | T0 | only problem fields listed |
| | `POST /v1/review-items/{id}/resolve` `{fields…, decision}` | T3 | decisions: `accept`, `not_a_transaction`, `duplicate_of`, `distinct` |
| | `POST /v1/review-items/batch-categorise` `{payee_key, category, set_default}` | T3 | |
| Transactions | `GET /v1/transactions?from&to&category&state` | T0 | |
| | `POST /v1/transactions` (manual) | T3 | may return `409 POSSIBLE_DUPLICATE` |
| | `PATCH /v1/transactions/{id}`, `DELETE /v1/transactions/{id}` | T3 | correction audited |
| | `POST /v1/transactions/{id}/category` `{category, set_payee_default?}` | T3 | sets `confirmed` |
| Bills | `GET/POST /v1/bills`, `POST /v1/bills/{id}/link-payment {txn_id}` | T0/T3 | |
| Pockets | `GET /v1/pockets?period=current` | T0 | allocation, spent_confirmed, spent_predicted, remaining |
| Plan | `GET /v1/plan` (current period waterfall) | T1 | lines with sources + allowance |
| Simulate | `POST /v1/simulate/affordability {amount, category?, date?}` | T1 | no write |
| Goals | `GET/POST /v1/goals`, `GET /v1/goals/{id}/feasibility` | T0/T1/T2 | create/update goes via proposal |
| Proposals | `POST /v1/proposals {kind, payload}`, `GET /v1/proposals?status=pending`, `GET /v1/proposals/{id}` | T2/T0 | response = proposal view with stored card (§5) |
| | `POST /v1/proposals/{id}/approve {payload_hash, card_hash}` + `Idempotency-Key` | T3 | both hashes required (FI-32) |
| | `POST /v1/proposals/{id}/edit {payload_hash, payload}` | T2 | 201 new proposal; old → `superseded` (FI-33) |
| | `POST /v1/proposals/{id}/cancel` | T3 | |
| Chat | `POST /v1/chat/messages {text}` → `{reply, cards[]}` | T0–T2 | streaming optional later |
| Data | `POST /v1/data/delete {scope: "imported"}` | T5 | synchronous per upload; returns `complete`, `images_pending_purge`, `pending_upload_ids`; repeat resumes (scope `all` not implemented) |
| Audit | `GET /v1/audit?subject_id=` | T0 | user-visible history of imports/approvals |

## 4. State machines

**Upload / import item**
```
received ──(job)──▶ extracting ──▶ validated ──▶ imported            (auto-import consent, no issues)
   │                    │              │
   │                    │              └──▶ needs_review ──(resolve)──▶ imported | rejected | merged_duplicate
   │                    └──(provider error, retry ≤5)──▶ extract_failed ──(user)──▶ manual entry / retry
   └──▶ duplicate_image (same sha256: returns existing)
any non-terminal ──(consent revoked)──▶ cancelled_consent
any ──(user delete)──▶ deleted   (terminal; jobs become no-ops)
```

**Proposal**
```
pending ──approve(hash ok, versions ok)──▶ applied
pending ──approve(version/watermark changed)──▶ stale  (+ replacement pending)
pending ──edit──▶ superseded (+ new pending)
pending ──cancel──▶ cancelled
pending ──time > expires_at──▶ expired
```

**Consent grant**: `active → revoked` (new grant = new row with new version; never reactivated).

**Transaction category**: `unclassified → predicted → confirmed`, `predicted → unclassified` (if source default removed), `confirmed` changes only by user.

## 5. Approval card (implemented: `approval-card@1`, `services/cards.py`)

Contract, not visuals. Every number, warning and flag is computed by deterministic code from the snapshot the
proposal is bound to (its data watermark, read **before** the card is computed). The chat model never computes or
edits a card; it receives a summary of the finished card as a tool result. The card is stored with the proposal
(`proposal.card`, `card_hash` = sha256 of its canonical JSON), cannot be updated (DB trigger, migration 0005) and is
returned unchanged on every read.

Proposal view (`POST /v1/proposals`, `GET /v1/proposals/{id}`, list, edit, and `details.replacement` of a stale 409):
```json
{
  "type": "proposal", "proposal_id": "…", "kind": "reallocate", "status": "pending|applied|stale|superseded|cancelled|expired",
  "created_by": "user|agent", "created_at": "…", "expires_at": "…", "decided_at": null,
  "payload": {…}, "payload_hash": "sha256:…", "card_hash": "sha256:…",
  "superseded_by": null, "edited_from": null,
  "actions": [
    {"action": "approve", "method": "POST", "path": "/v1/proposals/{id}/approve",
     "body": {"payload_hash": "sha256:…", "card_hash": "sha256:…"}, "requires_header": "Idempotency-Key"},
    {"action": "edit", "method": "POST", "path": "/v1/proposals/{id}/edit"},
    {"action": "cancel", "method": "POST", "path": "/v1/proposals/{id}/cancel"}
  ],
  "card": { … see below … }
}
```
`status` reads `expired` once `expires_at` has passed (no write needed) and `actions` is then empty; actions are
present only while the proposal is pending.

Card fields:
| Field | Content |
|---|---|
| `schema`, `policy` | `approval-card@1`; thresholds used and their status (provisional product policy) |
| `summary` | `{code, text}`, e.g. `REALLOCATE` "Move ฿3,750.00 of budget from Food to Shopping." |
| `changes` | pockets: `allocation_before/after`, `delta`, `spent_confirmed`, `spent_predicted`, `remaining_before/after` (satang); goals: `{field, before, after}` |
| `transfer` | reallocate only: `amount_satang`, `from`/`to` with remaining before/after |
| `effects.money_left` | discretionary before/after and daily allowance before/after |
| `effects.buffer`, `effects.commitments` | buffer before/after; bills/essentials/savings before/after and `changed` |
| `effects.unspent_budget` | Σ unspent before/after vs money left after, `fits` (BP-1 view) |
| `effects.goals` / `effects.this_goal` | goal feasibility before/after when money left changes; for goal proposals: events until deadline, required per event, `contribution_covers_required`. A pocket move reports `changed:false` with a reason code instead of numbers |
| `warnings[]` | `{code, severity: high|medium|info, text, params}` (table below) |
| `uncertainty[]` | `PREDICTED_CATEGORY_SPENDING`, `UNASSIGNED_SPENDING`, `EXCLUDED_UNRESOLVED`, `OPEN_REVIEW_ITEMS`, `BALANCE_OBSERVATION_OLD` |
| `assumptions[]`, `not_computed[]` | code-written assumptions (e.g. trade-off method); items that could not be computed with the reason code (e.g. `BALANCE_REQUIRED`) |
| `period`, `days_until_income`, `balance_as_of`, `computed_at`, `payload_hash`, `created_by`, `edited_from`, `extra.calculation` | provenance |

Warnings (thresholds = `card-policy@0.1`, **provisional product policy, not a competition requirement**; team to confirm):
| Code | Severity | Rule |
|---|---|---|
| `MOVES_ALL_REMAINING` | high | a pocket with unspent budget > 0 would have ≤ 0 left |
| `PLAN_EXCEEDS_MONEY_LEFT_AFTER` | high | goal proposal: current pocket budgets' unspent total would exceed money left after the new saving |
| `CAUSES_SHORTAGE` | high | money left goes from ≥ 0 to < 0 |
| `LARGE_MOVE` | medium | a pocket loses ≥ 50 % of its unspent budget, or the move is ≥ 25 % of all unspent pocket budget |
| `POCKET_LOW_AFTER` | medium | 0 < left < 10 % of the pocket's allocation before |
| `BUFFER_REDUCED` | medium | buffer after < before |
| `GOAL_BECOMES_INFEASIBLE` | medium | a goal reachable before is not reachable after (capacity = money left) |
| `GOAL_CONTRIBUTION_BELOW_REQUIRED` | medium | the goal's contribution per income is below what the deadline needs |
| `SUGGESTED_BY_ASSISTANT` | info | `created_by = agent` |

Why these numbers: ฿100 out of a ฿4,000 Food pocket (routine top-up) stays quiet; moving more than half of what a
pocket still has, or emptying it, is what the real agent demo produced and what a user should notice. A warning
never blocks approval; BP-1 and staleness do.

Binding (FI-32): approval requires `payload_hash` **and** `card_hash` of the stored proposal; either mismatch → 409
`PROPOSAL_MISMATCH`, nothing applied, audited (`hash_mismatch` / `card_mismatch`). Staleness, owner isolation,
idempotency and BP-1 re-check at approval are unchanged. A stale approval returns a replacement whose card is
**recomputed** on current data.

Edit (FI-33): `POST /edit` validates the new payload exactly like a new proposal, inserts a new proposal (new card,
new hashes, `edited_from`), and marks the old one `superseded` in the same transaction. Old id or old hashes can
never apply the edited content. No-op edit → 400 `NO_CHANGE`; editing a non-pending proposal → 409 with
`superseded_by`.

Other card types: `question` (one focused question with options, linked to what it would change), `insight` (overspend/shortage with evidence links), `simulation` (affordability result, explicitly "not recorded"), `review_batch`.
