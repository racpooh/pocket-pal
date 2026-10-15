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
| Proposals | `POST /v1/proposals` (user-initiated edit), `GET /v1/proposals/{id}` | T2 | |
| | `POST /v1/proposals/{id}/approve {payload_hash}` | T3 | |
| | `POST /v1/proposals/{id}/cancel` | T3 | |
| Chat | `POST /v1/chat/messages {text}` → `{reply, cards[]}` | T0–T2 | streaming optional later |
| Data | `POST /v1/data/delete {scope: imported|all}` | T5 | async; returns job id |
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

## 5. Chat cards (contract, not visuals)

```json
{
  "type": "proposal",
  "proposal_id": "…",
  "payload_hash": "sha256:…",
  "title": "Move ฿500 from Food to Shopping",
  "before": [{"pocket": "Food", "allocation_satang": 300000}, …],
  "after":  [{"pocket": "Food", "allocation_satang": 250000}, …],
  "effects": {"daily_allowance_delta_satang": 0, "goal_delays": []},
  "assumptions": [{"text": "฿300 of spending guessed as Food", "kind": "predicted_category", "items": ["txn_…"]}],
  "calculation": {"function": "reallocate", "version": "cashflow@0.1.0", "inputs_ref": "snapshot_…"},
  "expires_at": "…",
  "actions": ["approve", "edit", "cancel"]
}
```
Other card types: `question` (one focused question with options, linked to what it would change), `insight` (overspend/shortage with evidence links), `simulation` (affordability result, explicitly "not recorded"), `review_batch`.
