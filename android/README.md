# FinAssist Android client (CP3a)

Minimal client to test flows end to end against the real backend. No final visual design.

## Stack decision (D3a, Claude proposal for team/Codex acceptance)

**Native Kotlin + Jetpack Compose + (CP3b) WorkManager**, minSdk 26, target/compile SDK 35, demo device Samsung S23 (D3).

Why native rather than a cross-platform framework, given what is still to come:
- Photo access is the core of the product: Android 13 `READ_MEDIA_IMAGES`, Android 14+ partial access
  (`READ_MEDIA_VISUAL_USER_SELECTED`), the system Photo Picker and `MediaStore` date queries are first-class in
  Kotlin. In React Native/Flutter they come through plugins that lag OS changes, and we would have to verify the
  plugin as well as our code.
- Background scanning must use WorkManager with constraints; native gives this without a bridge.
- One language for the shared core and the app; the core runs on a plain JVM, so the client logic is tested
  without Android tooling (important here: see "Environment limits").
- Time: one screen set, no iOS in scope.

## Structure

| Module | What | Built/tested where |
|---|---|---|
| `core/` (pure Kotlin/JVM, **no third-party dependencies**) | `ApiClient` (contract `docs/design/05`), `UploadQueue` (exactly-once intent per image, persisted, backoff, consent/pause/session blocks), `BaseUrlPolicy` (HTTPS rule), `Json`, `Money`, `UploadLabels` | compiled and run in the build sandbox (Gradle's bundled Kotlin 2.0.21 compiler) and by `./gradlew :core:selfTest` |
| `core/src/test` | `CoreSelfTest` — 17 dependency-free tests | same |
| `core/src/e2e` | `Cp3aE2E` — the core against the **real backend** (FastAPI + Postgres + RLS + embedded worker), fake extraction with synthetic fixtures | `tools/cp3a_e2e.py` |
| `app/` (Android) | Compose screens: sign in/up, Setup, Consent (3 separate items), Upload (Photo Picker, status, retry, pause), Review (edit/confirm), Ledger (money left, pockets, unclassified, transactions, set category); `KeystoreTokenStore`; queue storage | **not built in the build sandbox** — owner builds it (steps below) |

## Security choices (client side)

- Model API key: never in the app (D2). The app only knows the backend base URL.
- Session token: AES-256-GCM, key in Android Keystore (non-exportable); ciphertext in app-private prefs.
  Never logged (the app has no logging calls). 401 from the server clears it and returns to sign in.
- Logout: server session revoked (best effort), local token cleared, **unsent local image copies discarded**.
- Transport: release builds accept only `https://` (BaseUrlPolicy at startup + `network_security_config` with
  cleartext off). Debug builds allow cleartext **only** to `127.0.0.1`, `localhost`, `10.0.2.2` (your own machine
  via `adb reverse` or the emulator host). No redirects are followed (Authorization never forwarded).
- Backup/transfer: `allowBackup=false` and `data_extraction_rules` exclude everything.
- Images: only photos the user picks; copied to app-private `noBackupFilesDir` until the server confirms receipt,
  then deleted. The original file name is not sent. Failed/discarded entries keep the copy until the user
  retries or discards (shown in the list).
- TEST MODE banner whenever `/v1/health` says `test_mode: true` (fake extraction). Never silent.
- Warnings on approval cards will be shown from backend fields (CP3b); the app never computes or rewrites amounts.

## Environment limits (stated up front)

- **Build sandbox (cloud):** no access to Google Maven / Gradle Plugin Portal / Android SDK, no `/dev/kvm`
  → cannot build the APK or run an emulator. The `app` module was **parsed** by the Kotlin compiler (no syntax
  errors found besides unresolved Android/Compose symbols, which are expected without the SDK) but **not
  compiled against Android**. Treat it as unverified until the owner's build passes.
- **Owner's Cowork Linux VM:** same — no access to those hosts.
- **Owner's Mac:** Android Studio + the phone are where the app is built and run. Not done by Claude.

## Build and run on the Mac (owner)

Prerequisites: Android Studio (Ladybug 2024.2 or newer; it bundles a JDK), USB debugging on the S23, `adb` on PATH
(Android Studio → SDK Manager → Platform-Tools), `uv`.

1. Backend, test mode (terminal 1, repo root):
   ```bash
   cd backend
   uv run --with pixeltable-pgserver python scripts/dev_server.py --provider fake --reset
   ```
   Wait for the `TEST MODE` banner and `Uvicorn running on http://127.0.0.1:8000`.
2. Phone → your Mac (terminal 2): `adb devices` (accept the prompt on the phone), then
   `adb reverse tcp:8000 tcp:8000`.
3. Synthetic slips on the phone (they will appear in Gallery; delete the folder afterwards):
   ```bash
   adb shell mkdir -p /sdcard/Pictures/FinAssistSynthetic
   for f in slip_003_transfer_out slip_004_transfer_out slip_021_transfer_out slip_024_transfer_out slip_028_bill; do
     adb push backend/fixtures/synthetic/slips/$f.png /sdcard/Pictures/FinAssistSynthetic/; done
   adb shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/Pictures/FinAssistSynthetic/
   ```
   (If the scan broadcast is ignored on your Android version, open the folder once in "My Files".)
4. Build + install: Android Studio → Open `android/` → wait for Gradle sync → Run ▶ on the S23 (debug).
   Command line alternative: `cd android && ./gradlew :core:selfTest :app:installDebug`.
5. Client-core E2E with Gradle (optional, Mac): `python3 android/tools/cp3a_e2e.py --slug cp3a-client-e2e-mac --runner gradle`
   (stop the server from step 1 first, the script starts its own).
6. Cleanup: `adb shell rm -r /sdcard/Pictures/FinAssistSynthetic` and `adb reverse --remove-all`.

### Manual device checklist (CP3a) — record the result of each line

| # | Do | Expect |
|---|---|---|
| 1 | Open app | Yellow TEST MODE banner; sign-in screen |
| 2 | Create account with a synthetic email (e.g. `cp3a-demo@example.test`) | Tabs appear |
| 3 | Setup: income 20,000, next pay 2026-11-01, rent 5,000 day 30, balance 15,000 → Save | "Money left … ฿10,000.00" |
| 4 | Upload → Choose slip photos (pick 003, 004) **before** any consent | Entries show "Waiting: photo processing is not allowed"; nothing sent |
| 5 | Consent → Allow photo processing (from 2026-07-01); turn auto-import on | Upload tab: entries go Processing → Imported |
| 6 | Pick 003 again | No new entry (same image) |
| 7 | Pick 024 and 021 | "Needs your review" |
| 8 | Review → blurred slip: type amount 120.00 → Confirm | Item disappears; Ledger shows a ฿120.00 transaction |
| 9 | Ledger | Money left, "Not yet categorised" list, transactions with source `auto_import`/`review_import` |
| 10 | Airplane mode, pick 028, then turn network back on, Refresh | "Waiting to retry (NETWORK)" then Imported/Needs review |
| 11 | Force-stop the app during an upload, reopen | The entry is sent once (no duplicate record) |
| 12 | Consent → Withdraw photo processing, pick another slip | Not sent; status explains why |
| 13 | Log out → sign in again | Queue empty (local copies discarded); data still on the server |
| 14 | Stop the server (Ctrl-C), act in the app | "Server not reachable…", nothing lost |
| 15 | Pick 3 slips, press "Pause sending" immediately | At most the one already uploading finishes; the rest show "Paused" |
| 16 | Pick a photo without a date (e.g. a screenshot of a synthetic slip saved by an app that drops EXIF; if none, skip) | Dialog "1 photo(s) have no date"; "Don't send" sends nothing |
| 17 | Upload the receipt + its slip pair (see `ground_truth.jsonl` group tag `same_purchase_as`) | Review shows the existing record and only "Same purchase — attach", "Different purchase", "Not a transaction"; attach → no new transaction |
| 18 | With photos waiting (consent withdrawn), end the session: stop the server and start it again with `--reset` (all sessions and accounts are gone); in the app act once ("Session ended"), then create/sign in a different account | "N unsent photo(s) from another account … discarded"; nothing of the first account appears or is sent |

Screenshots (synthetic data only; crop out the status bar if it shows notifications):
`adb exec-out screencap -p > evidence/runs/<UTC>-cp3a-device/NN-<step>.png`. Do not record real accounts or photos.
