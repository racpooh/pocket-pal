# 15 — Pocket Pal web integration

Status: implemented for local browser validation; not full CP3 acceptance or deployment approval.

## Decision and source

The owner approved preserving Pocket Pal's UI while replacing demo data/actions with API connections, and using Chrome on the Galaxy S22 Ultra over USB for the immediate demo. The original `/Users/POOH/Development/case/pocket-pal` is untouched. Its `web` source is copied into this repo's `web/`; the Android Compose client remains separate. Next was updated from the copied 15.5.4 to 15.5.28. npm/package-lock is the installation path; the copied pnpm lock is archival only.

The owner authorized the existing Anthropic Console API key for Chat. It remains in backend settings; the browser receives neither the API key nor backend bearer token. No paid provider call was made during this web integration verification. The reported Console balance is not a newly authorized spending budget.

## Connected surfaces

| Surface | Real source/action | Verification and limits |
|---|---|---|
| Connect | signup/login, identity, health, consent | BFF synthetic smoke; no hardcoded credentials |
| Chat | POST chat/messages; server reply, simulations, proposal cards; image upload/poll/review | Fake-mode unavailable response verified; actual paid chat through this browser not yet run |
| Pockets | plan, pockets, profile, insights, date-bounded spending | Mobile-sized Chrome rendered from synthetic DB; daily guide is current/recomputed, not an opening-day limit |
| Activity | transactions, bills, review queue; correction/category; link paid bill | Load and review tested; all correction/link interactions not exhaustively browser-tested |
| Setup | profile, balance anchor, bills, pocket definitions, plan suggestion and human approval | Implemented; full first-run browser sequence pending |
| Goal | list, feasibility, create/update proposals with explicit approval | Page rendered; populated-goal interactions pending |
| Settings | profile, consent, audit, logout, imported-data deletion | Page rendered; destructive controls not exercised on owner's data |

Original rounded cards, typography, colors, navigation and page structure are reused. API-driven review/approval cards necessarily show backend-required fields and warnings. No assertion of pixel-for-pixel equality with the friend's clip is made. Original CSV import was already a placeholder. Demo seeding is not wired into real accounts. Full account deletion, dated goal contribution schedules, native gallery scanning/background jobs and automatic categorization certainty are not invented to fill UI space.

## Boundary and controls

Browser → same-origin Next BFF → loopback FastAPI → owner-scoped PostgreSQL and storage/provider. Session cookie is HttpOnly/SameSite Strict, Secure on HTTPS. Mutations require Origin matching Host/protocol; absent or foreign origin is rejected. Proxy buffers at most 9 MiB; backend keeps its own 8 MiB image constraint. Forwarded request headers are restricted. Auth endpoints cannot be called through the generic proxy. Data responses use no-store; only the backend sets owner identity.

Late errors do not clear a newer cookie. Identity verification gates page data, but multi-tab account switching and every in-flight browser race are not yet exhaustively tested. This local HTTP-over-USB configuration is not an Internet deployment. Rate limiting, persistent chat cost limits, CSP/deployment hardening and real-device browser lifecycle need follow-up. Existing backend runtime Chat does not receive a UsageMeter in `build_chat_model`; do not claim Settings.budget_usd is a persistent runtime cap.

Proposal approval sends server payload/card hashes and an idempotency key stable for retries. A stale response can replace the displayed proposal and requires a new user approval. The model has no approval action. Review uses allowed_decisions/candidates, requires critical inputs, handles 404 as failure, and never treats network uncertainty as success. Backend review extraction now includes due_date_text. Integration also exposed an overlapping-plan selection bug: the latest approved period that has started supersedes older periods, including after it expires (no fallback). Logging was corrected to retain location-only stack frames, excluding source literals, and to preserve Uvicorn access formatter arguments. No prompt/parser/reference contract change.

## Evidence

- `20261016T165051Z-web-bff-smoke`: 15 checks passed against real FastAPI/PostgreSQL in isolated e2e profile, fake extraction; fake Chat deliberately returns 503.
- `20261016T165659Z-web-bff-smoke`: same 15 checks on production Next build, passed.
- `20261016T165348Z-web-browser-smoke`: synthetic login, mobile-sized renders of Chat/Pockets/Activity/Settings/Goal, upload to Review and confirmation; 8 steps, no page errors. Chrome headless at 393×852, **not** physical S22. Screenshots contain synthetic data only.
- `20261016T165304Z-web-review-backend`: 4 focused regression tests passed, 0 skipped, isolated test DB. Covers preserved due date and existing required-input cases.
- `20261016T165437Z-web-build`: TypeScript + production build passed. A later final build may be listed in HANDOFF with source hash.
- Earlier failed smoke runs are retained: `20261016T163424Z` origin/host mismatch; `20261016T164838Z` incorrect test assumption that a new account already has pockets; `20261016T164943Z` missing pocket setup in test. They are not acceptance evidence. Earlier successful render-only runs are narrower than the later interaction run.

No dev database reset, real image transfer, Git command, or paid model call was performed for these runs. Isolated PostgreSQL data lives under `/private/tmp/pocket-pal-web-test`. The production web on 3000 points to the owner's existing backend on 8000, whose health reports test_mode=false; no user data was read to verify this.

## Open acceptance

Physical S22 Chrome normal-flow recording, paid Chat response through web, full setup/goal/edit/reallocation UI interactions, account-switch race tests, and deployment security review remain. REF-GAP-1/2 remain open. Web access does not satisfy native album scan/background requirements. These are explicit gaps, not waived requirements. Technical/security documentation can describe the implemented architecture and evidence now, but must retain these limitations.

## Final validation update (17 Oct 2026 ICT)

- `20261016T170403Z-web-browser-smoke`: 9 browser steps passed, now including setup → explicit plan approval → read back buffer 50,000 satang. This closes the setup buffer defect found in failed `170030Z`; it is still not physical-device evidence.
- `20261016T170440Z-web-plan-supersession`: full backend suite 294 passed, 0 failed, 2 skipped entries are the existing strict reference xfails, not accepted controls. Added plan-supersession and log compatibility/source-privacy regressions.
- `20261016T170510Z-web-build`: final TypeScript and production build passed, source SHA-256 in manifest.
- Runtime dev backend on port 8000 was detected as `scripts/dev_server.py --profile dev --provider anthropic`. It must be restarted with the same environment, without --reset, to load the new backend fixes. Codex did not terminate the owner's existing process. USB port 3000 is forwarded; production web is started against existing port 8000.

Physical connection check only: adb successfully launched Chrome with http://localhost:3000/connect; local HTTP returned 200. This is not evidence of successful on-device login/upload/chat. Isolated synthetic API process was stopped after validation; owner dev backend was left running.


## Phase 1: mobile chat readability and pocket scope (17 Oct 2026 ICT)

Implemented:
- Assistant replies render through react-markdown and remark-gfm: headings, paragraphs, lists and horizontally scrollable tables. Raw HTML is skipped; model images are disabled; links use the default safe URL transform and isolated new tabs. User messages remain plain text.
- Chat instructions prefer concise answers in the user's language and mobile-friendly bullets. Overview tools now expose today, next payday, budget period, historical-spending scope and the existing bill reservation policy. This changes the chat prompt only; extraction prompts and frozen OCR experiments are unchanged.
- Pockets explicitly show the active date window (end exclusive), explain historical slips, and refresh on focus or on request. A category edit does update an in-period expense's pocket. Older categorized expenses remain in Activity/historical spending and do not consume a newer budget. This is verified with synthetic transactions, not inspection of the owner's account.
- Added an increase-by-THB editor using the existing tradeoff API. The server proposes proportional reductions from other pockets' unspent funds. Only explicit approval applies changes; the total allocation is conserved. This is not a full arbitrary-target/decrease editor. Edit amounts returns to the editor without an automatic model call.

Evidence:
- `20261016T174404Z-web-review-backend`: 6 focused tests passed.
- `20261016T174645Z-phase1-backend`: 25 tests passed (slice review, category/date scope, existing API flows including tradeoff conservation and human approval), isolated test DB; no dev reset.
- `20261016T174520Z-phase1-browser`: five UI checks passed with explicitly mocked synthetic HTTP responses; Thai formatting, HTML/image/unsafe-link handling, 393px layout, integer-satang proposal and explicit approval refresh. Not real-model evidence or a physical S22 run.
- `20261016T174704Z-web-build`: types and production build passed. Earlier `174401Z` is retained as environment-limited (Turbopack sandbox port binding).

No paid calls were made. The user's unseen-question evaluation and physical S22 acceptance are still pending. Existing reference ambiguity gaps remain open.

### Phase 2 feasibility, not implementation

Preserve Pocket Pal UI in an Android host with a deliberately scoped native media/work bridge; do not assume the Next.js server-side session proxy can be bundled as static files. The final hosting/session design must retain backend-only API keys. Off-USB use requires a reachable HTTPS service, separately from producing an APK.

Use Android media permissions with full, selected-only, denied and revoked access states; scan only accessible images within a rolling 30-day capture-time window. Run a local slip-candidate filter before sending candidates under explicit processing consent; never upload every gallery image. Unknown dates require manual selection/confirmation. Retain account binding, pause/revocation, deduplication and retry controls. Provide Scan now in addition to WorkManager: periodic work is not guaranteed to run immediately. This remains unimplemented and unverified; the existing APK does not yet contain the web UI and this scanner.

Primary references: [react-markdown](https://github.com/remarkjs/react-markdown), [remark-gfm](https://github.com/remarkjs/remark-gfm), [Android selected photo access](https://developer.android.com/about/versions/14/changes/partial-photo-video-access), [WorkManager periodic scheduling](https://developer.android.com/reference/androidx/work/PeriodicWorkRequest).
