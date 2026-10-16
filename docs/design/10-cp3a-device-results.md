# 10 — CP3a device results (Samsung S23)

> **Device correction (16 Oct 2026, ~20:40 ICT):** the phone used for testing is a Samsung Galaxy S22 Ultra (SM-S908E, Android 14), as shown by the owner's install log (model SM-S908E, Android 14; that log is on the owner's Mac, not in this repo). Earlier text called it "S23". Results recorded below are unchanged; only the device name was wrong.


**Kind of evidence: user-reported.** These results were observed and reported by the owner (Pooh). They are not
automated runs; no logs or screenshots exist for them, and none were created afterwards. Automated evidence is in
`09` and `evidence/runs/`.

## Report 1 — received 16 Oct 2026, ~13:40 ICT

- Reported by: owner, via the chat with Claude (relayed together with Codex's instructions).
- Device: Samsung S23 (D3). Backend: `backend/scripts/dev_server.py --provider fake` on the owner's Mac via `adb reverse`.
- Build: debug APK built by the owner on the Mac. **Not stated:** which sources (latest = 401 fix, `versionName 0.3.0-cp3a`
  is the same for every CP3a build), the exact test time, Android version. To be confirmed by the owner.

| # (owner) | Scenario as reported | Result (reported) | Checklist line(s) in `android/README.md` |
|---|---|---|---|
| R1 | Import two synthetic photos; the records appear in Ledger | pass | 5 (pass); 9 partly — money left, "Not yet categorised" and `source` values not reported |
| R2 | Pick the same photo again; no extra record | pass | 6 |
| R3 | slip_024 goes to review; amount corrected to 120.00 → one record added | pass | 7 partly (024 only; 021 not reported), 8 |
| R4 | Pause while sending; Resume works as expected | pass | 15 |
| R5 | Withdraw consent; new photos are not imported until consent is given again | pass | 12 (+ re-grant part of 5) |
| R6 | Backend stopped, app opened: IdentityFailed with Retry, no tabs/queue; backend started, Retry works | pass | 19 |
| R7 | Log out with photos waiting, sign in to a new account: neither the old queue nor the old records are visible | pass | 13 partly ("data still on the server" for the first account not reported); **not** 18 (18 is a session that ends without logout) |

## Checklist coverage after Report 1

| Line | Status |
|---|---|
| 5, 6, 8, 12, 15, 19 | reported pass |
| 7, 9, 13 | partly reported (see above) |
| 1, 2, 3 | not reported (needed for R1–R7, but the expected texts were not confirmed) |
| 4 | not tested — photos picked before any consent |
| 10 | not tested — offline/retry. **Checklist fix:** airplane mode does not cut `adb reverse` (it runs over USB), so line 10 now uses `adb reverse --remove` instead |
| 11 | not tested — force-stop during upload, restart |
| 14 | not tested — server stopped while the app is open |
| 16 | not tested — photo without a date |
| 17 | not tested — receipt + slip pair, attach adds no spending |
| 18 | not tested — session ends without logout, then another account |

The seven reported scenarios do **not** complete the checklist. CP3a stays open until lines 4, 10, 11, 14, 16, 17
and 18 are reported (and the partly-reported lines confirmed), or Codex decides otherwise.

## Steps for the remaining lines (owner, ~20 min)

Setup once: latest sources → `cd android && ./gradlew :core:selfTest :app:installDebug` (expect `27/27 passed`); terminal 1:
`cd backend && uv run --with pixeltable-pgserver python scripts/dev_server.py --profile dev --provider fake --reset`; terminal 2:
`adb reverse tcp:8000 tcp:8000`. Push the extra synthetic slips:
```bash
for f in slip_015_transfer_out slip_016_receipt slip_028_bill slip_032_transfer_out slip_033_transfer_out slip_034_transfer_out; do
  adb push backend/fixtures/synthetic/slips/$f.png /sdcard/Pictures/FinAssistSynthetic/; done
adb shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/Pictures/FinAssistSynthetic/
```
New account, Setup as in line 3. Note for each line: pass / fail + what you saw (text on screen).

| Line | Do | Expect |
|---|---|---|
| 1–3 | Open app, create account, Setup | Yellow TEST MODE banner; tabs; "Money left … ฿10,000.00" |
| 4 | **Before** any consent: Upload → pick 032 | "Waiting: photo processing is not allowed"; Ledger has no record |
| 16 | While picking in line 4/5, watch for the dialog "N photo(s) have no date" | If it appears: press "Don't send" once (nothing queued), pick again and "Send these photos". If it never appears for pushed PNGs, report "no dialog" — then the phone supplies a date for them and line 16 needs a different test image |
| 5 | Consent → allow photo processing (from 2026-07-01) + auto-import | 032 → Processing → Imported |
| 10 | `adb reverse --remove tcp:8000`; pick 033; wait ~10 s; `adb reverse tcp:8000 tcp:8000`; Refresh | "Waiting to retry (NETWORK)", then Imported; Ledger shows 033 once |
| 11 | Pick 034, 015, 028 and **immediately** `adb shell am force-stop dev.finassist.android`; reopen the app | Entries continue and finish; each appears once in Ledger |
| 17 | After 015 is imported, pick 016 (its receipt) | Review: existing record ฿237.00 shown; buttons only "Same purchase — attach", "Different purchase", "Not a transaction"; attach → Ledger total unchanged, no new ฿237.00 row |
| 14 | Ctrl-C the server; in the app press Refresh / open Ledger | "Server not reachable…"; restart the server (no `--reset`), Refresh → data still there |
| 18 | Withdraw consent, pick 003 (stays waiting). Ctrl-C the server, start it **with `--reset`**; in the app open Ledger and press Refresh → "Session ended…"; create a new account | Message "1 unsent photo(s) from another account … discarded"; no old queue entry, no old records |
| 9, 13 | Ledger of the first account before line 18: money left, "Not yet categorised", sources `auto_import`/`review_import` | as listed |

Cleanup: `adb shell rm -r /sdcard/Pictures/FinAssistSynthetic`, `adb reverse --remove-all`.


## Note — automated runs reset the phone's dev database (16 Oct 2026, ~13:45 ICT)

`android/tools/cp3a_e2e.py` started `dev_server.py --reset` on the same local database the phone uses
(`finassist_dev`). Claude's automated runs in the owner's VM therefore wiped the synthetic accounts and records
created during the device tests — including the run `20261016T064357Z-cp3a-notice-client-e2e-device-pg18-arm64`,
made after Report 1 was received. No real data was involved; the phone's stored session became invalid (the app
shows "Session ended" / identity check). **Fix:** automated runs now use a separate database `finassist_e2e`
(`dev_server.py --db-name`); `finassist_dev` is only reset when the owner runs `--reset` himself.
