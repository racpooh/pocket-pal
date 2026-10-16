# FinAssist Android client (CP3a)

Minimal client to test flows end to end against the real backend. No final visual design.

## Stack decision (D3a, Claude proposal for team/Codex acceptance)

**Native Kotlin + Jetpack Compose + (CP3b) WorkManager**, minSdk 26, target/compile SDK 35, test phone Samsung Galaxy S22 Ultra (SM-S908E, Android 14) (D3 said S23; corrected 16 Oct).

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

Prerequisites: Android Studio (Ladybug 2024.2 or newer; it bundles a JDK), USB debugging on the phone (Galaxy S22 Ultra (SM-S908E, Android 14)), `adb` on PATH
(Android Studio → SDK Manager → Platform-Tools), `uv`.

1. Backend, test mode (terminal 1, repo root):
   ```bash
   cd backend
   uv run --with pixeltable-pgserver python scripts/dev_server.py --profile dev --provider fake --reset
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
4. Build + install: Android Studio → Open `android/` → wait for Gradle sync → Run ▶ on the phone (debug).
   Command line alternative: `cd android && ./gradlew :core:selfTest :app:installDebug`.
5. Client-core E2E with Gradle (optional, Mac): `python3 android/tools/cp3a_e2e.py --slug cp3a-client-e2e-mac --runner gradle`
   (it starts its own `--profile e2e` server on port 8001 with its own database and cluster; the phone's server from step 1
   can keep running — see `docs/design/12` §1).
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
| 10 | Pick 028 while offline: run `adb reverse --remove tcp:8000` first (airplane mode does **not** cut `adb reverse`, it runs over USB), wait ~10 s, then `adb reverse tcp:8000 tcp:8000` and press Refresh | "Waiting to retry (NETWORK)" while offline, then Imported/Needs review once; no duplicate |
| 11 | Force-stop the app during an upload, reopen | The entry is sent once (no duplicate record) |
| 12 | Consent → Withdraw photo processing, pick another slip | Not sent; status explains why |
| 13 | Log out → sign in again | Queue empty (local copies discarded); data still on the server |
| 14 | Stop the server (Ctrl-C), act in the app | "Server not reachable…", nothing lost |
| 15 | Pick 3 slips, press "Pause sending" immediately | At most the one already uploading finishes; the rest show "Paused" |
| 16 | Pick a photo without a date (e.g. a screenshot of a synthetic slip saved by an app that drops EXIF; if none, skip) | Dialog "1 photo(s) have no date"; "Don't send" sends nothing |
| 17 | Upload the receipt + its slip pair (see `ground_truth.jsonl` group tag `same_purchase_as`) | Review shows the existing record and only "Same purchase — attach", "Different purchase", "Not a transaction"; attach → no new transaction |
| 18 | With photos waiting (consent withdrawn), end the session: stop the server and start it again with `--reset` (all sessions and accounts are gone); in the app act once ("Session ended"), then create/sign in a different account | "N unsent photo(s) from another account … discarded"; nothing of the first account appears or is sent |
| 19 | Signed in, close the app; stop the server; open the app | "Checking your account…" then "could not be confirmed" with Retry; no tabs, no queue. Start the server, Retry → tabs open |

### Slice 1 device checklist (Galaxy S22 Ultra, SM-S908E) — new UI (docs/design/13 §6), record pass/fail + what you saw

Setup: latest sources → `cd android && ./gradlew :core:selfTest :app:installDebug` (expect `35/35 passed`, app version
`0.4.1-slice1`). Backend: `cd backend && uv run --with pixeltable-pgserver python scripts/dev_server.py --profile dev --provider fake`
(add `--reset` only if you want a fresh dev DB yourself), `adb reverse tcp:8000 tcp:8000`. Synthetic slips only (step 3 above, plus 015, 016).

| # | Do | Expect |
|---|---|---|
| S1 | Open the app | Grey ground, white rounded cards; yellow TEST MODE strip; sign-in card |
| S2 | Create a new account | "Checking your account…", then the **You** tab opens on Consent (photo processing not allowed yet) |
| S3 | Upload tab → "Upload slip photos" → pick 003 before allowing | Card "Waiting: photo processing is not allowed"; hint pill says sending stopped |
| S4 | You → Consent → Allow (from 2026-07-01); auto-import on | Upload: 003 → Processing → Imported |
| S5 | Pick 024 | Card "Needs your review" with "Open review" → Review sheet: photo on top, Amount marked "Needed"; buttons exactly "Confirm with these details" and "Not a transaction" |
| S6 | Type 120.00 → Confirm | Message "Recorded."; pocket chooser → pick Food (or Skip); Activity shows −฿120 under its day |
| S7 | Pick 015, wait for Imported; pick 016 (its receipt) → Review | Notice "receipt of a payment you already have"; existing record ฿237 shown; buttons "Same purchase — attach…", "Different purchase…", "Not a transaction"; attach → "No new spending was added"; Activity has no second ฿237 |
| S8 | Pick 028 (bill) | Activity: "Upcoming bills" card (if it becomes a bill) or a Waiting row "Not counted yet" |
| S9 | Activity → "Waiting (n)" chip → tap a waiting row | Opens that item in Review |
| S10a | **Stale review (404).** Open a waiting item in Review and leave the sheet open. On the Mac, resolve the same item for the same account with the commands in "S10a helper" below. Back on the phone, press a decision | Message: the item **is no longer waiting** and nothing is shown as saved; the list refreshes; Activity has the record once |
| S10b | **Network failure.** Open a waiting item. Run `adb reverse --remove tcp:8000`, then press a decision | Message: **no answer from the server, may or may not have been saved**; never "Recorded.". Run `adb reverse tcp:8000 tcp:8000`, then Refresh: the item is still waiting (the request never reached the server), and deciding again works once |
| S11 | Stop the server; Activity → Refresh | Red "Couldn't load … Server not reachable" card with Retry; Retry after restart loads |
| S12 | Upload a JPG > 8 MB or a HEIC | Not queued; message "Larger than 8 MB" / "Not a JPG or PNG photo" |
| S13 | You → Log out with a photo still waiting; sign in as another account | Upload tab empty; Activity shows nothing of the first account |
| S14 | Visual check against the pocket-pal style board | note differences (font, icons not bundled yet) |
| S15 | **Finding 1, bill without a due date.** Push `backend/fixtures/synthetic/review_variants/var_bill_no_due_date.png` (a synthetic test variant with a yellow "TEST VARIANT" strip) and upload it | Review sheet: "Due date (as printed)" marked **Needed**; the save button stays disabled. Type `2026-10-20` and save: "Saved as a bill."; Activity → Upcoming bills shows ฿3,600 due 2026-10-20; **no new expense row** |
| S16 | **Finding 1, unknown status → Completed.** Upload `var_slip_status_unknown_a.png` | "Did this payment go through?" with **nothing pre-selected**, marked Needed; the save button is disabled until you choose. Choose "Completed — counted": the row appears with −฿899 and is counted in the day's total |
| S17 | **Finding 1, unknown status → Failed.** Upload `var_slip_status_unknown_b.png`, choose "Failed — recorded, not counted" | The row shows the tag "Failed · not counted"; the day's total does not include ฿350 |
| S18 | **Finding 2, negative money.** You → Setup: income 1,000, next pay a date 2–3 weeks ahead, rent 5,000 (due day before the next pay), balance 1,000 → Save | The summary says **"Until next pay: Short ฿4,000"** (balance − rent); it never shows a positive "฿… to spend" when money is short |

S10a helper (Mac terminal; synthetic account only; replace the email and password with the ones you used in the app):

```bash
BASE=http://127.0.0.1:8000/v1
TOKEN=$(curl -s -X POST $BASE/auth/login -H 'Content-Type: application/json' -d '{"email":"you@example.test","password":"your password here"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -s $BASE/review-items -H "Authorization: Bearer $TOKEN" | python3 -c 'import sys,json;[print(i["id"],i["reason"],i["allowed_decisions"]) for i in json.load(sys.stdin)["items"]]'
curl -s -X POST $BASE/review-items/ITEM_ID/resolve -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"decision":"not_a_transaction"}'
```

Put the id of the item that is open on the phone in place of ITEM_ID. Pushing the variants: `for f in var_bill_no_due_date var_slip_status_unknown_a var_slip_status_unknown_b; do adb push backend/fixtures/synthetic/review_variants/$f.png /sdcard/Pictures/FinAssistSynthetic/; done`, then run the media-scan command from step 3.

S10b proves only that a request which never reached the server is not shown as saved. A response lost **after** the server committed cannot be produced reliably by hand. That case is covered by the E2E step "resolving an item that is no longer open → NoLongerOpen", which sends the decision again for an item that was already resolved.

Screenshots (synthetic data only; crop out the status bar if it shows notifications):
`adb exec-out screencap -p > evidence/runs/<UTC>-cp3a-device/NN-<step>.png`. Do not record real accounts or photos.
