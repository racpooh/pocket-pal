# Pocket Pal gallery scan with dated test copies — owner-reported (S22 Ultra)

NOTE: Owner-reported result. Claude did not see the device; no logcat line for the successful scan was captured in this record. Timestamp in the run id is approximate (17 Oct 2026, ~11:00 ICT).

## Root cause of "only 2–4 photos found"
- Prepared real slips on the phone had no capture date (`DATE_TAKEN` NULL): 31 in `Download/PocketPal/slip/`, migrated from iPhone without metadata. The scanner excludes undated photos by design (no `DATE_ADDED` substitution).
- Census from adb (counts only): 768 images; 148 undated; 617 older than 30 days; 3 in window. Permission was "All photos" (not the cause).
- After pushing new files with adb, the app first saw 695 images (DCIM only) until a MediaStore rescan (`content call --method scan_volume`) was run; afterwards the new folder was visible.

## Test data (TEST ENVIRONMENT ONLY)
- 55 slips selected manually by the owner into a Photos album on the Mac and exported with osxphotos (`--exiftool`, `--convert-to-jpeg`): all JPEG, all with `DateTimeOriginal` from iPhone Photos metadata (1–17 Oct 2026), `OffsetTimeOriginal +07:00`. Capture dates were recovered, not invented.
- Copies kept in `eval/private/iphone-dated/` (gitignored by `**/private/`), pushed to `Pictures/PocketPalTEST/` on the S22. Originals on iPhone untouched. No file names, images or OCR text in this record.

## Result
- Owner reports automatic scan picked up and sent about 10 slips (one scan's attempt cap); results appeared after about 5 minutes. Bounds unchanged (10 attempts per scan, 20 per day).

## Not yet verified
- Amounts/dates correct per slip in Activity/Review; no duplicates; Chat answers using the imported data.
- Remaining ~45 slips (daily cap) and filter v2 false positives/negatives on a mixed gallery.
- Latency optimisation (≈5 minutes) deferred by the owner.
