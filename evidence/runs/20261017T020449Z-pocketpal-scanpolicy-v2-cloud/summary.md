# Pocket Pal scan policy v2 — cloud unit run (Claude)

- What ran: `ScanPolicyTest` (8 tests: capture window, v1 English rule, bounded read, attempt caps, census date classes, v2 layout rule positives, v2 layout negatives incl. amount-vs-time and amount-vs-BE-year, money-only counter) compiled with the Gradle-bundled Kotlin compiler in the cloud container. 8/8 passed.
- Not covered: `GalleryWorker.kt` / `ScanStore.kt` (Android SDK, ML Kit, MediaStore) were not compiled here — the owner's Mac Gradle build is the compile check. Text tests are not image precision/recall evidence; no real image was read.
- Inputs are synthetic strings. No paid calls, no real images, no Git.
- Same sources were copied to the owner's Mac repo; web `tsc --noEmit` passed in the device VM (local `node_modules/.bin/tsc`, exit 0) for `gallery-controls.tsx`. The mocked browser smoke (`web/scripts/native-controls-smoke.cjs`) is Mac-only and was NOT run in this round.
