# Pocket Pal APK — clean gallery trial

This is the `:pocketpal` module, package `dev.finassist.pocketpal`, separate from the earlier Compose app (`dev.finassist.android`). It hosts the connected Pocket Pal web UI. It does not bundle slips, fixture accounts, or API keys.

## Open the installed app

1. Keep the S22 connected to the Mac by USB. Open **Pocket Pal** (the new app, not FinAssist).
2. Create an account. This trial uses an empty, separate database; an account from the old dev environment is not present here. Use a test email you choose and a new password; there is no seeded login.
3. Explicitly allow photo processing. The Android connect screen defaults the consent start date to 30 days ago; check that date before continuing. Enable automatic import only if desired; otherwise processing results need review.
4. Set up balance and income through **Set up balance and income**. These are inputs, not imported transactions.
5. Open **Settings → Slips from the last 30 days**. Choose photo access (all photos or selected photos), read the processing notice, enable scanning, and confirm the native dialog.
6. Use **Scan now**. Check the scan status, then Activity → Refresh for imported/review items and Chat for questions. Upload acceptance precedes extraction; wait a few seconds and refresh again if processing is still underway. No manual upload is necessary for a detected candidate.
7. In Chat, **Enable memory** explicitly allows future conversation storage/context. Without it, tab switching retains text only for the current browser session; the model does not receive previous turns. **New chat** clears the conversation, not transactions, budgets or pending proposals.

Fresh baseline before the owner's trial: gallery database has zero users/uploads/transactions/bills/review items/chat messages/jobs; upload storage has zero files. APK installed fresh with photo permissions denied and scanning disabled. The old dev database, old APK and Gallery source photos were not erased.

## Services (if no longer running)

Backend terminal:

```bash
cd ~/Development/case/shenzen/backend
uv run --with pixeltable-pgserver python scripts/dev_server.py --profile gallery --provider anthropic
```

Web terminal:

```bash
cd ~/Development/case/shenzen/web
FINASSIST_BACKEND_URL=http://127.0.0.1:8002 npm run start -- --hostname 127.0.0.1 --port 3002
```

USB terminal:

```bash
export PATH="$HOME/Library/Android/sdk/platform-tools:$PATH"
adb reverse tcp:3002 tcp:3002
adb shell am start --user 0 -n dev.finassist.pocketpal/.MainActivity
```

Do not add `--reset`. The existing `dev` profile on 8000 is separate. This is a local debug trial, not an independently hosted release: the web server, backend, Mac and USB forwarding must remain available. Android can delay background work; force-stop prevents scheduled work until the app is opened again.

## Build

```bash
cd ~/Development/case/shenzen/android
export ANDROID_HOME="$HOME/Library/Android/sdk"
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
./gradlew :pocketpal:testDebugUnitTest :pocketpal:assembleDebug
adb install --user 0 -r pocketpal/build/outputs/apk/debug/pocketpal-debug.apk
```

## Implemented scan behavior and limitations

- Capture timestamp (`MediaStore.DATE_TAKEN`) within the rolling last 30 × 24 hours, additionally restricted by processing consent. Never substitutes date-added for an unknown/old capture date. Unknown dates are skipped, so downloaded slips lacking capture metadata may need manual upload.
- Full/selected-only/denied Android access; revoked access stops reads. Only JPEG/PNG up to 8 MiB. The local bundled ML Kit Latin recognizer checks payment terms, amount-like text and supporting financial words before upload. OCR here is only a candidate filter; extraction still runs on the backend with Anthropic.
- The filter is a heuristic, not a validated slip classifier. Thai-only slips may be missed and non-slips can match. No claim of recall/precision; the planned frozen 40-positive/200-negative image evaluation remains unrun. Unit tests use text, not actual OCR images.
- At most 100 new eligible photos inspected locally and 10 upload attempts per run; 20 attempts per owner per day, reserved durably before network calls. Repeated scans progress past locally remembered results. An uncertain network response consumes an attempt; a repeated identical image is deduplicated by backend hash.
- Native scheduling uses WorkManager (15-minute periodic request plus Scan now). It rechecks the signed-in identity, cookie, permission, processing consent, owner binding and pause state. Logout pauses scanning. Upload already in flight may finish; server consent/owner checks still apply.
- Origin-allowlisted, main-frame-only WebMessage bridge. No unrestricted JavaScript interface, raw tokens in JavaScript, file access, mixed content, TLS bypass, backups or remote debugging. Debug cleartext only to loopback; a release requires a configured HTTPS web origin.
- Native status is masked when its session binding differs from the current WebView cookie. Old-account scan results are not shown as the new account's status.

Physical gallery scanning, process death/retry, permission revocation during work, false-positive/negative image evaluation and extended on-device background behavior still need acceptance testing. Build/install/launch alone does not prove these pass.
