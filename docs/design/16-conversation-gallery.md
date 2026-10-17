# Conversation continuity and clean native gallery trial

Status: implemented, built, and new APK installed/launched on S22 Ultra (SM-S908E, Android 14). **Physical gallery acceptance is pending.** No personal photo read or model request was performed during this checkpoint. Activity now has a manual Refresh control for asynchronous gallery extraction results. No RAG/vector database was introduced.

## Phase 1.1 — conversation

- Owner-bound in-memory store survives client tab navigation and in-flight responses. It is cleared on identity failure, account change and sign-out/connect. A synchronous route guard hides the old subtree until identity is verified for the new route.
- Existing `chat_history_retention` consent controls persistence and model history. Explicit Enable memory saves future turns; without it, tab memory is display-only and disappears on a full reload. No silent consent or retroactive upload of unsaved turns.
- `GET /v1/chat/messages` returns the current owner's retained history only; `DELETE` starts a new conversation. A per-owner transaction advisory lock serializes turns and deletion. Revocation during a model request cannot restore history afterwards.
- Keep at most 200 stored messages and at most 12 recent context messages / 12,000 characters, with per-message clipping. The client cannot supply system/tool-role history. The model still uses tools for current financial numbers; old assistant prose is not an authoritative balance.
- Restored proposal cards are fetched again by ID. Late responses and edits cannot append to another account/epoch. Refreshing cards cannot overwrite a newer in-flight response.

## Phase 2 — APK and media path

The separate `android/pocketpal` module uses `dev.finassist.pocketpal`, preserving the connected Next.js UI through WebView. The existing Compose APK remains. The default debug origin is `http://127.0.0.1:3002`; web BFF points to the new `gallery` backend profile on 8002, with its own database, roles and upload storage. The existing dev database on 8000 was not reset or queried for personal records.

The Android-specific bridge is restricted to the configured origin and main frame through AndroidX WebMessageListener. It offers only status, permissions, enable/pause and scan. The native worker reads the HttpOnly cookie through native CookieManager, snapshots it, and rechecks unchanged cookie + server identity + processing consent before upload. Session hashes mask prior-account native status. Late enable callbacks are guarded on the UI thread so Pause wins. Native cookies and API keys are not exposed to JavaScript.

MediaStore queries capture dates in the last 30 × 24 hours; unknown capture dates are never replaced with date-added. The consent start date is also checked before local OCR and upload. Local bundled ML Kit Latin text recognition filters candidate JPEG/PNG images; originals are sent only for candidate matches and under consent. No persistent local copy of image bytes is kept. Durable owner-scoped hashes prevent repeated sends; server duplicate handling covers uncertain responses. WorkManager schedules periodic and manual scans, with one worker at a time, bounded local work, max 10 attempts/run and 20 attempts/owner/day reserved before sending.

This is a **debug local-service APK**, not standalone hosted deployment. Mac services and USB forwarding must be available. Release requires a configured HTTPS origin. User guide: `android/POCKETPAL_GALLERY.md`.

## Evidence

| Run | Result | Boundary |
|---|---|---|
| `20261017T012325Z-conversation-gallery-backend` | 300 passed, 0 failed, 2 existing strict reference xfails | Full isolated test-profile suite; no dev reset |
| `20261017T012328Z-conversation-browser` | 5 checks passed | Synthetic HTTP fixtures: tab continuity, new chat, in-flight navigation, account switch, consent/reload |
| `20261017T012243Z-native-controls-browser` | 3 checks passed | Mock native bridge, no actual photo access; opt-in/actions/event-loop guard |
| `20261017T012905Z-web-build` | TypeScript and production build passed | Web code |
| `20261017T012431Z-pocketpal-apk` | APK build + 4 policy tests passed | Date boundaries, candidate examples, size/read boundary and work limits; not actual OCR-image accuracy |
| `20261017T012521Z-gallery-clean-baseline` | All aggregate counts zero; storage zero files; test_mode false | Fresh gallery profile only, no test account seeded |
| `20261017T012628Z-pocketpal-install` | Fresh install and process launch; HTTP connect 200; photo permissions denied | Actual SM-S908E/Android 14; no scan or model call |

Earlier failed and environment-limited runs remain with their notes. Browser account-switch check initially failed; route isolation and explicit navigation waits were added. A subsequent harness run matched two headings and failed; narrowed selector before the passing run. No failures were deleted.

## Open acceptance and limitations

1. Native permission transitions, kill/restart during upload, revoked consent during real device work, delayed WorkManager scheduling and first gallery-to-ledger flow remain unverified on-device. Installation is not acceptance of CP3b.
2. The Latin text filter is heuristic. It can miss Thai-only slips and admit a non-slip; the planned frozen ≥40 positive / ≥200 negative image evaluation is not run. Text unit tests are not image recall/precision evidence. Unknown-date downloaded slips may require manual upload. The app discloses these limits.
3. Existing REF-GAP-1 / REF-GAP-2 remain open; the 2 strict xfails are not security passes. No new claim of universal dedup accuracy.
4. Runtime upload-attempt bounds are not an invoice-level dollar cap. Existing real-provider usage accounting limitations still apply. This checkpoint used no paid calls.
5. Owner must create a fresh account, allow processing and photo access, and explicitly enable scanning. No gallery image will be read/uploaded automatically on first launch. Gallery originals and old dev records were intentionally preserved.

Primary implementation references: [ML Kit bundled text recognition](https://developers.google.com/ml-kit/vision/text-recognition/v2/android), [origin-scoped WebMessageListener](https://developer.android.com/reference/androidx/webkit/WebViewCompat.WebMessageListener), [selected photo access](https://developer.android.com/about/versions/14/changes/partial-photo-video-access), [periodic work constraints](https://developer.android.com/reference/androidx/work/PeriodicWorkRequest).

## Scan observability update (17 Oct 2026, Codex)
**TL;DR:** Added persisted per-scan stages and counters in native Settings, plus `PocketPalScan` logcat events containing only fixed stage codes, timestamps, counters and HTTP status. Existing phone state showed zero attempts and two previously marked metadata entries; this does not establish total album size or why those photos were skipped. Latest scans previously hid this distinction. Monitor now separates accessible dated photos, already checked, unsupported, consent-window skips, local checks, filtered-out candidates and server acceptances. Unknown capture dates remain excluded; local heuristic and upload policy unchanged. APK updated with `-r`, preserving user data. No paid calls or real-image reads by Codex; user-triggered end-to-end scan acceptance is still pending.

Evidence: `20261017T015209Z-pocketpal-apk` build and existing policy tests; `20261017T015210Z-web-build` typecheck/build; `20261017T015252Z-native-controls-browser` four mocked UI checks and installation record. Sandbox-limited build `20261017T015153Z-pocketpal-apk` retained with NOTE. Web 3002 restarted against gallery 8002. Scan monitor values appear after the next scan; server acceptance is not completed OCR/import.

## Gallery scan fix round 1 (17 Oct 2026, Claude) — "only 2 photos" diagnosis
**TL;DR:** The monitor counted only photos whose MediaStore `DATE_TAKEN` is inside 30 days (2), and both were marked by the v1 English-only filter, so it could not show *why* 20+ prepared slips were absent. Likely causes, not yet proven on the phone: (a) selected-photos access covering only some photos, (b) slips with no capture date (images saved/copied from another app usually lack EXIF date → `DATE_TAKEN` null → excluded by design), (c) capture date older than 30 days, (d) Thai slips rejected by the v1 English-only filter. Implemented: metadata-only census (visible / undated / older / future / in-window, permission mode), split seen-cache counters, and local filter **v2** (adds a language-independent slip-layout rule: amount with satang + masked account or long reference + `HH:MM` time or BE year). Photos marked by v1 are re-read **locally** once; a content-hash match with an earlier accepted upload is skipped and never re-sent; new marks are `acc:` / `rej:` (422) / `flt:v2:`. Undated photos are still never sent automatically and `DATE_ADDED` is not substituted; caps unchanged (100 local / 10 attempts per run, 20/day). APK versionCode 2 (`0.2.0-gallery`).

Tested: `20261017T020449Z-pocketpal-scanpolicy-v2-cloud` (8/8 JUnit, synthetic strings, cloud); web `tsc --noEmit` passed in device VM. Not verified: APK compile of GalleryWorker/ScanStore (owner's Mac Gradle), mocked browser smoke (Mac-only), real scan on S22 Ultra, end-to-end OCR→Activity/Review→Chat, v2 image FP/FN (no benchmark). Originals of the changed files kept at `.sync/pp-orig-v1/`. No paid calls, no real images read by Claude, no Git, no reset.

Seen-cache scheme (keys never contain names, paths or OCR text): `seen:<owner>:<id>:<taken>:<size>` legacy v1 mark (cause not stored) → re-read once by v2; `seen:acc:<meta>` and `seen:<owner>:<sha256>` accepted → never sent again; `seen:rej:<meta>` server 422 → not retried automatically; `seen:flt:v<N>:<meta>` filtered by version N → re-checked only when `FILTER_VERSION` increases. Monitor adds: photos visible, no capture date, older than 30 days, already sent before, rechecked with updated filter, unmatched-but-showing-an-amount, could not be read, filter version.

