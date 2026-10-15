# 09 — CP3a review request for Codex (15 Oct 2026, ~21:00 ICT)

Scope: Android client skeleton + auth/setup + manual upload → review → ledger, connected to the real backend.
CP3b (album scan, OS permissions, background, chat/approval, lifecycle) is **not started**.
Rules kept: no git, no paid deploy, no paid model calls, no real slips, no security control relaxed for the demo.

## Environment limits (honest)
- Build sandbox and the owner's Cowork Linux VM cannot reach Google Maven, the Gradle Plugin Portal or the
  Android SDK, and have no KVM. **The APK was not built and nothing ran on an emulator or the S23.**
- The `app` module was only parsed by the Kotlin compiler (remaining errors are unresolved Android/Compose
  symbols, which is expected without the SDK). It is unverified until the owner builds it.
- What did run: the pure-Kotlin `core` (the same code the app uses for every API call and the upload queue),
  compiled with Gradle's bundled Kotlin 2.0.21, its self-tests, and an end-to-end scenario against the real backend.

## Changes

Backend
| File | Change |
|---|---|
| `settings.py` | **No default model provider** (was `fake`): unset → `ConfigError`; `fake` refused unless `FINASSIST_ENV` is `dev`/`test`. |
| `api/app.py` | `/v1/health` adds `test_mode` and `env`; `app` for uvicorn is built lazily (PEP 562) so importing the module does not need config; log redaction re-installed at startup (uvicorn configures handlers after app creation); optional injected extraction provider, allowed only with `fake`. |
| `services/imports.py`, `routes.py` | `POST /v1/uploads/{id}/retry` (from `extract_failed`/`cancelled_consent` only; consent + date range re-checked; one live job). |
| `services/budget.py`, `routes.py` | `GET /v1/pockets` (owner-scoped list with category mapping). |
| `scripts/dev_server.py` | Local backend for the phone: real app + Postgres + RLS roles (fresh random passwords per start) + embedded worker; `--provider` required; fake provider preloaded with synthetic fixtures; binds 127.0.0.1; resets only a DB named `finassist_dev`. |
| `scripts/demo_scenario.py` | passes the provider/env explicitly. |
| tests | `test_cp3a_client_api.py` (3), 2 new config tests. |

Android (`android/`, see `android/README.md` for the stack decision D3a and the device steps)
| Path | What |
|---|---|
| `core/…/Api.kt` | API client: error envelope, 401 → token cleared, offline → `NetworkException`, idempotency key on manual transactions, generic upload file name. |
| `core/…/UploadQueue.kt` | Persisted queue, one entry per content hash; state saved before each send; restart → re-send → server `duplicate_image`; backoff for offline/5xx/429, give up after 6; queue-wide block on `CONSENT_REQUIRED`, user pause, session end; local copy deleted after the server confirms. |
| `core/…/Http.kt` | `HttpURLConnection` transport (no redirects), multipart, `BaseUrlPolicy`. |
| `core/…/Json.kt`, `Money.kt` | dependency-free JSON; THB parsing with backend rules. |
| `app/…` | Compose screens (Auth, Setup, Consent, Upload, Review, Ledger), TEST MODE banner, `KeystoreTokenStore`, prefs queue store, private file blob store, network security config (debug local-only cleartext), backup exclusion. |
| `tools/cp3a_e2e.py` | Reproducible evidence run (starts dev server, self-tests, E2E, manifest). |

## API contract used by the client (all existing except the two marked new)
`GET /v1/health` (+`test_mode`), auth signup/login/logout, `GET/PUT /v1/me/profile`, `GET /v1/accounts`,
`POST …/balance-observations`, **`GET /v1/pockets` (new)**, `POST /v1/pockets`, consents list/grant/revoke,
`POST /v1/uploads` (multipart `image`, optional `captured_at`), `GET /v1/uploads/{id}`, **`POST /v1/uploads/{id}/retry` (new)**,
`GET /v1/scan-status`, `GET /v1/review-items`, `POST /v1/review-items/{id}/resolve`, `GET /v1/transactions`,
`POST /v1/transactions/{id}/category`, `GET /v1/plan`.

## Results
| Run | Evidence | Result |
|---|---|---|
| Backend full suite (x86_64, Python 3.12.3, PG 16.15; DB enabled, skipped 0) | `evidence/runs/20261015T134610Z-cp3a-backend` | 253 passed |
| Client core self-tests | `evidence/runs/20261015T134438Z-cp3a-client-e2e-cloud/core_selftest.log` | 17/17 |
| Client core ↔ real backend E2E (fake extraction, synthetic fixtures) | same run, `client_e2e_steps.json` | 22/22 steps |
| Backend full suite, Linux ARM64 VM on the owner's Mac (not native macOS), PG 18.4 | `evidence/runs/20261015T135038Z-cp3a-backend-device-pg18-arm64` | 253 passed, skipped 0 |
| Client core self-tests + E2E in the same VM (Java 11; core jar compiled here from the same sources with `-jvm-target 11`), PG 18.4 dev server | `evidence/runs/20261015T135405Z-cp3a-client-e2e-device-pg18-arm64` | 17/17, 22/22 |
| Invalid attempts kept with NOTE.md | `20261015T135129Z-…` (jar built for Java 17 on a Java 11 VM), `20261015T135212Z-…` (pgserver cold start: Postgres not yet accepting connections → fixed with a retry in `dev_server.py` and `local_pg.py`) | not evidence |

E2E outcomes (synthetic): 003, 004 and bill 028 imported automatically; 021 and blurred 024 went to review; the
non-fixture image failed extraction, retry re-queued it once and it failed again (honest for a fake extractor);
user typed 120.00 for 024 → one transaction; resolving again → 404; server-side duplicate of 003 → 200
`duplicate_image`; user B without auto-import → `confirm_import` review → accepted; B cannot read A's upload;
after withdrawing photo consent nothing is sent and a direct upload gets `CONSENT_REQUIRED`; after logout the old
token is rejected (`SESSION_EXPIRED`).

## Not verified (must not be claimed)
- Android build, install, screens, Photo Picker, Keystore, network security config on a device or emulator.
- Album scanning, OS photo permissions (denied/revoked/partial), background work, local candidate filtering and
  its FP/FN on synthetic images — CP3b.
- Chat and approval cards in the app — CP3b.

## Questions for Codex
1. No default provider + `fake` only in dev/test: OK as the "no silent fake" rule? (It changes how the server is started: provider must be set.)
2. Manual pick without a capture date (`captured_at` absent) skips the server's date-range check (`03 §4` gap). Accept for user-picked photos, or require a date and ask the user?
3. Logout discards unsent local copies. OK, or keep them per account?
4. `POST /uploads/{id}/retry` also covers `cancelled_consent` after re-consent. OK?
5. Native Kotlin/Compose (D3a) acceptable before CP3b?

## What the owner needs to run (Mac + S23)
`android/README.md` → "Build and run on the Mac" and the 14-line device checklist. Results (and synthetic-only
screenshots) go to `evidence/runs/<UTC>-cp3a-device/`; Claude then updates `06`/`09` with what actually passed.


---

## Codex CP3a review → fixes (15 Oct 2026, ~21:20 ICT)

Codex did not close CP3a: three P1 findings, plus the requirement to build and run the app on Android. Answers to
the five questions adopted: no default provider ✔; undated photos must be confirmed per photo, separately from
automatic scanning; discarding queued photos must also cover session expiry and account switch; retry after
re-consent ✔ (latest grant/range re-checked); Kotlin/Compose ✔ (D3a accepted).

| # | Finding | Fix | Tests |
|---|---|---|---|
| 1 [P1] | Queue not bound to an account: after A's session expired, B's sign-in resumed A's photos with B's token | Every entry records its account; the queue is bound to one owner (`GET /v1/me` after every sign-in and at app start, before anything is shown or sent); binding to a different account **discards** the previous account's entries and local copies; an unbound queue sends nothing and cannot enqueue; logout clears and unbinds. Defence in depth: each upload sends `expected_owner_id`, the server refuses a mismatch (`409 OWNER_MISMATCH`, nothing stored) | core: `#1 owner: A's photos are discarded …` (A expires with 2 photos → restart → B binds → 0 sent, 0 shown, 0 local copies; each request names its account), `#1 owner: same account … keeps its queue; unbound queue sends nothing`; backend: `test_upload_for_another_account_is_refused_and_stores_nothing`, `test_me_returns_only_the_session_owner`; E2E: account switch step (C expires with 2 queued → D signs in on the same phone → C and D both have 0 uploads), OWNER_MISMATCH step |
| 2 [P1] | Pause waited for the whole batch (same single-thread executor) | `UploadQueue.requestPause()` is thread-safe (volatile) and checked before **every** request; the UI calls it immediately (pause button, consent withdrawal, logout, session end) and then persists the pause on the queue thread | core: `#2 pause requested while the first upload is in flight → the second never starts` (two real threads, latch inside the first request) |
| 3 [P1] | Receipt review offered "Confirm" (= `accept`, a new expense) instead of linking | Server returns `allowed_decisions` and `candidates` (amount, date, payee, source of the existing record) per review item and **refuses** other decisions (`409 DECISION_NOT_ALLOWED`); a supplied `txn_id` must be one of the candidates. `receipt_link` → attach / different purchase / not a transaction; `possible_duplicate` → same payment / different / not a transaction. The app renders only `ReviewActions.forItem(item)` and shows the candidate | backend: `test_receipt_review_offers_link_not_accept_and_link_adds_no_spending` (accept refused, non-candidate refused, link adds no spending); core: `#3 review actions follow the server …`; E2E: receipt step (no accept offered; attach; transaction count unchanged) |
| A2 | Undated photo skipped the consent range check | Server: no `captured_at` → `422 CAPTURE_DATE_REQUIRED` unless `confirmed_undated=true` (audited `undated_confirmed`). App: photos without a date are held back and listed in a dialog ("N photos have no date … send anyway?"); a queued one that hits the error shows "Send without date". Album scanning (CP3b) never sets the flag | backend: `test_undated_photo_needs_explicit_confirmation`; core: `undated photo: … only an explicit confirm sends it`; E2E undated step |

Mutation checks (fix removed → test fails): owner discard (1 core test), pause flag (1), review actions offering
`accept` (1), server decision check (1), server owner check (1), server undated check (1).

Also found: two new backend tests left queued extraction jobs that a later test's worker picked up (the worker
claims across owners) → 2 unrelated failures in one run. Fixed by draining in those tests. That failed run's folder
was deleted in the build sandbox before syncing (it was never shared); disclosed here instead.

### Results
| Run | Evidence | Result |
|---|---|---|
| Backend full suite (x86_64, PG 16.15; DB enabled) | `evidence/runs/20261015T141505Z-cp3a-fix-backend` | 257 passed, skipped 0 |
| Client core self-tests + E2E vs real backend (x86_64) | `evidence/runs/20261015T140955Z-cp3a-fix-client-e2e-cloud` | 22/22, 26/26 |
| Backend full suite, Linux ARM64 VM on the owner's Mac (not native macOS), PG 18.4 | `evidence/runs/20261015T141840Z-cp3a-fix-backend-device-pg18-arm64` | 257 passed, skipped 0 |
| Client core self-tests + E2E in the same VM (Java 11 jar compiled here from the same sources) | `evidence/runs/20261015T141923Z-cp3a-fix-client-e2e-device-pg18-arm64` | 22/22, 26/26 |

### Android build: still not done by Claude
Both environments here still cannot reach Google Maven / the Android SDK. The `app` module was re-parsed after the
changes (only unresolved-Android-symbol cascades remain). **The owner's Gradle build on the Mac is the first
compile of the app module**; compile errors from it come back to Claude to fix before the device checklist.


---

## Codex CP3a re-review → fix (15 Oct 2026, ~23:50 ICT)

[P1] `signedInNow()` opened the signed-in screens (`signedIn = true`) before `GET /v1/me` and `bindOwner()` had
finished; with a slow or failing `/me`, B could see A's queue metadata or add photos to A's queue.

**Fix:** new `core/SessionGate` with states `SignedOut / Checking / IdentityFailed / Ready`.
- `begin()` stops the queue at once (keeps a stronger stop the user chose: their pause or withdrawn consent) and
  enters `Checking`. Screens: `Checking` → "Checking your account…" only; `IdentityFailed` → explanation +
  **Retry** + Log out, queue hidden; only `Ready` opens the tabs.
- The queue is reachable only through the gate: `readyQueue()` returns it only when `Ready` and bound to that same
  account; `visibleEntries()`, `enqueue()`, `pumpOnce()` go through it. The app module no longer touches the queue
  directly except the thread-safe `requestPause`.
- Each check has an epoch; `complete()` applies a `/me` result only for the current check, so a late answer after
  logout or after another sign-in cannot bind the queue. `signOut()` (logout, any 401) invalidates checks in flight.

Tests (core, `CoreSelfTest`): A queued → B signs in → `/me` fails → A's queue hidden, enqueue refused, nothing
sent (also by a direct `runOnce`) → retry → Ready for B, A's photo discarded; late `/me` of an earlier check ignored
after logout and after another sign-in; session end while Ready hides and stops, same-account re-check restores
its photos and keeps the user's own pause. E2E (real backend): E queues a photo → F signs in → `/me` offline →
IdentityFailed, 0 visible, 0 sent, enqueue refused → retry → Ready for F, no uploads. Mutations: `readyQueue`
ignoring state (2 tests fail), stale `/me` applied (1), `begin` not stopping the queue (1).

| Run | Evidence | Result |
|---|---|---|
| Client core + E2E vs real backend (x86_64, PG 16.15) | `evidence/runs/20261015T164817Z-cp3a-gate-client-e2e-cloud` | 25/25, 27/27 |
| Backend full suite (no backend change this round; DB enabled) | `evidence/runs/20261015T164958Z-cp3a-gate-backend` | 257 passed, skipped 0 |
| Invalid attempt kept with NOTE.md | `20261015T164627Z-cp3a-gate-client-e2e-cloud` (sandbox Postgres had stopped) | not evidence |
| Client core + E2E, Linux ARM64 VM on the owner's Mac (Java 11 jar compiled here from the same sources), PG 18.4 | `evidence/runs/20261015T165304Z-cp3a-gate-client-e2e-device-pg18-arm64` | 25/25, 27/27 |

Observed on the owner's Mac at ~23:51 ICT: `android/app/build/outputs/apk/debug/app-debug.apk` (8.8 MB, versionName 0.3.0-cp3a) exists, built from the **previous** sources (before this gate fix); Gradle's problems report lists only plugin deprecation warnings. So the app module compiled at least once — by the owner, not by Claude. The gate fix needs a rebuild. Not verified: install and the 19-line checklist on the S23.
