# 11 — CP3b design and acceptance tests (proposal, not implemented)

Status: **design only** (16 Oct 2026). Nothing here is built. Starts after Codex closes CP3a.
Scope (from the Word brief R2.1, R2.3, R8.x, R9.4 and CP3 instructions): album scan, photo permissions including
partial access and revocation, local candidate filtering, background work, chat with approval cards, lifecycle.
Unchanged rules: synthetic images only, fake extraction / scripted chat in tests (visible TEST MODE), no paid model,
no deploy, no git by Claude, no security control relaxed for the demo.

## 1. Photo access model

| Situation (Android 14+, test phone Galaxy S22 Ultra (SM-S908E, Android 14)) | What the app can read | What the app shows / does |
|---|---|---|
| Full access granted (`READ_MEDIA_IMAGES`) | all images in MediaStore | "Scanning photos from <scan_from>" |
| Partial access (`READ_MEDIA_VISUAL_USER_SELECTED` only) | only the photos the user selected in the system sheet | "Scanning only the N photos you allowed — not your whole album"; button "Choose more photos" (re-request) |
| Denied | none | album scan off; manual Photo Picker still works (needs no permission) |
| Revoked later (Settings) | none; process restarted by the OS | on next start/worker run: permission check fails → scan stops, no error loop, notice "Photo access was turned off" |
| Android 13 | full or denied only | same as rows 1/3 |
| Android ≤12 (minSdk 26) | `READ_EXTERNAL_STORAGE` | same as rows 1/3 (not the demo device) |

Rules: never claim "whole album scanned" unless full access; the scan summary reports `{access: full|partial|none,
photos_seen, candidates, sent, skipped_by_reason}`. The OS permission, the server consent `photo_processing`, and
`auto_import` stay three separate switches (CP3a). Scanning requires **all** of: Ready session (SessionGate), OS
access, active `photo_processing` consent; photos older than the consent's `scan_from` are never read past metadata.

## 2. Album scan

- Query MediaStore `Images` with `DATE_TAKEN >= scan_from` (and `DATE_ADDED` fallback when `DATE_TAKEN` is null —
  such photos are **undated**: never auto-sent; listed for explicit confirmation, Codex answer 2).
- Incremental cursor per account: `(last DATE_ADDED, last _ID)` stored with the queue's owner; reset when the owner changes.
- Only candidates enter the `UploadQueue` (exactly-once per sha256 already exists). A photo already in the queue or
  already known to the server (200 `duplicate_image`) is never re-sent.

## 3. Local candidate filtering (prototype, on device, no model)

Goal: do not upload the album for the server to sort. Two cheap stages, deterministic, no network:
1. **Metadata:** MIME JPEG/PNG; size 20 KB–8 MB; portrait-ish aspect ratio (height/width 1.2–3.0, slips and
   screenshots); width ≥ 600 px; folder hints raise the score (`Screenshots`, bank-app export folders), camera folder lowers it.
2. **Pixels** (downscaled to 64×64 grayscale): fraction of near-white background, edge density in horizontal bands
   (text lines), presence of a large high-contrast square block (QR area). Score = weighted sum; threshold chosen on a
   dev split, frozen before the test split.

Evaluation on **synthetic** images only: positives = 40 synthetic slips/receipts/bills; negatives = generated
non-slip images (gradients, noise, shapes, synthetic "photos", synthetic chat screenshots, menus) — at least 200,
committed with their generator script and seed. Report on the frozen test split: confusion matrix, FP rate
(non-slips that would be uploaded), FN rate (slips that would be missed), per-category misses, latency per image on
the test phone (Galaxy S22 Ultra (SM-S908E, Android 14)). Known limits stated in the report: real bank slips and real photos differ from synthetic ones; this filter
reduces uploads, it does not decide what is a transaction (the server still validates everything).

## 4. Background work

- WorkManager unique periodic work `album-scan` (15 min minimum, OS may defer; documented as best effort), plus a
  one-off scan on app open. Constraints: network connected, battery not low. `ExistingPeriodicWorkPolicy.KEEP`.
- The worker has no UI, so it runs its own identity check: stored token → `GET /v1/me` → must equal the queue owner;
  otherwise stop (no send). Consent and OS access are re-checked at the start of each run; revocation mid-run stops
  before the next image (`requestPause`).
- One writer: the worker and the app share the single-thread queue dispatcher in-process; across processes the queue
  file is guarded by a file lock (WorkManager runs in the app process by default — verified in the test below).
- Logout / account switch cancels the unique work.

## 5. Chat and approval cards in the app

- Chat screen → `POST /v1/chat/messages`. In dev/test the backend uses a **scripted** chat model that must be
  enabled explicitly (`dev_server.py --scripted-chat`, TEST MODE banner, `/v1/health.test_mode`); no paid model.
- Cards are rendered **only from backend fields**: `card.summary`, `changes`, `transfer`, `effects`, `warnings`
  (severity high/medium/info, high shown first and above the buttons), `uncertainty`, `assumptions`, `expires_at`.
  The model's reply text is shown separately and never replaces card numbers.
- Approve: `POST /v1/proposals/{id}/approve {payload_hash, card_hash}` with an `Idempotency-Key` generated per tap
  and reused for retries of that tap. `409 PROPOSAL_STALE` → show `details.replacement` card and require a new tap;
  `PROPOSAL_MISMATCH` → reload card; `410` → "expired". Edit → amount form → `POST …/edit` → new card. Cancel.
- `GET /v1/proposals?status=pending` on screen open (reload-safe).

## 6. Lifecycle

Pause/resume, consent revoke with pending purge (`/v1/data/delete` result shows `images_pending_purge`), logout,
session expiry (SessionGate), account switch, process death and restart, permission revoked while backgrounded.

## 7. Acceptance tests (CP3B-*)

Automated = JVM core tests or backend/E2E in this repo; Device = owner on the test phone (Galaxy S22 Ultra (SM-S908E, Android 14)) (user-reported, dated, kept apart).

| ID | Test | Kind |
|---|---|---|
| CP3B-01 | Permission matrix (full / partial / denied / revoked) maps to the right scan mode and texts; partial never says "whole album" | core (pure mapping) + device |
| CP3B-02 | Partial access: only the selected photos are scanned; "Choose more" adds only those | device |
| CP3B-03 | Revoke in Settings while app is backgrounded → next run scans nothing, shows the notice, no crash/retry loop | device |
| CP3B-04 | Scan respects `scan_from`; undated photos are never auto-sent and appear for confirmation | core + device |
| CP3B-05 | Incremental cursor: second scan sends 0 new; cursor resets on account switch | core |
| CP3B-06 | Filter FP/FN report on the frozen synthetic test split (≥40 positives, ≥200 negatives), threshold frozen before | core eval (evidence run) |
| CP3B-07 | Filter latency on the test phone per image reported | device |
| CP3B-08 | Worker: identity mismatch or no session → sends nothing | core + E2E |
| CP3B-09 | Worker: consent withdrawn between runs → nothing new sent; withdrawn mid-run → stops before next image | core + E2E |
| CP3B-10 | Worker and app at the same time → each image sent once (one queue writer) | core (two threads) + device |
| CP3B-11 | Process death mid-scan → restart continues without duplicates | device |
| CP3B-12 | Chat card shows backend warnings before the approve button; numbers equal card fields, not reply text | core (render model) + device |
| CP3B-13 | Approve sends both hashes + idempotency key; double tap applies once | E2E |
| CP3B-14 | Stale proposal → replacement card shown → old card cannot be approved → new tap applies replacement | E2E |
| CP3B-15 | Edit → new card, old superseded; cancel | E2E |
| CP3B-16 | Data delete from the app shows pending purge until complete | E2E + device |
| CP3B-17 | Logout/account switch cancels background work and discards the previous account's queue | core + device |
| CP3B-18 | Scripted chat refused unless explicitly enabled; TEST MODE visible | backend test |

## 8. Order and size (estimate)

1. Permission/scan core + filter + synthetic negatives + eval (CP3B-01, 04–06) — largest, ~1 day.
2. Worker + one-writer guarantee (08–11, 17).
3. Chat/cards screens + scripted chat flag (12–15, 18).
4. Lifecycle + delete (16) and device checklist.

Decisions needed (team/Codex): filter thresholds policy (prototype values, frozen per §3); whether background scan is
in the demo or on-open scan is enough given OS deferral; scripted-chat flag in dev_server.
