# Pocket Pal Technical Documentation

Topic A Personal Finance Assistant | POC review edition | 17 October 2026

Pocket Pal turns consented payment images and manually entered records into a personal ledger, budget pockets and a conversational finance assistant. Deterministic backend functions calculate money; the language model explains results and proposes changes that require user approval. The prototype does not connect to banks or move real money.

## Demonstrated outcome and scope

The owner reports that the Galaxy S22 Ultra automatically discovered and submitted approximately ten dated slip images and displayed results after approximately five minutes. The owner considers this sufficient to proceed with POC documentation. This confirms a reported device workflow, not per-image extraction accuracy, duplicate safety or a measured latency distribution [E4].

The current APK hosts the integrated Pocket Pal web interface. It requires the local web server, backend and USB forwarding. A signed, remotely hosted standalone release is not delivered. Latency improvement is deferred at the owner’s request; all unverified requirements remain visible.

| Component | Current implementation |
| --- | --- |
| Android | Kotlin WebView host, WorkManager, MediaStore, bundled ML Kit Latin OCR; package dev.finassist.pocketpal; v0.2.0-gallery reported installed by owner. |
| Web | Next.js 15 and React 19; Chat, Pockets, Activity, Goals, setup and Settings; same-origin backend proxy. |
| Backend | Python 3.12 or later, FastAPI, Pydantic, psycopg and PostgreSQL; local evidence includes PostgreSQL 18.4. |
| Models | Configured Anthropic IDs: claude-haiku-5-5 for extraction and claude-sonnet-5-5 for chat. These are repository configuration values, not a statement about current provider availability. |
| Storage | PostgreSQL and owner-restricted local upload storage in the current demonstration. Cloud deployment remains proposed. |

## How to read this document

This is a team review draft for competition technical documentation. Sections cover architecture, algorithms, API and data contracts, reproduction, and evidence. Evidence IDs refer to repository paths in the final section. Source authority is the original product brief, followed by the supplied competition PDF; design documents do not replace their requirements.

# Architecture and trust boundaries

Data flow: permitted Android photos → local date and candidate filters → authenticated web proxy → FastAPI upload validation → PostgreSQL job queue → extraction provider → deterministic validation and duplicate checks → ledger or review queue → financial tools → chat explanation or pending proposal.

## Client and API boundary

The web server converts its HttpOnly session cookie into a backend bearer token. The browser never receives the model key. Mutating proxy requests require matching origin, and proxy paths and request sizes are bounded. Android uses an origin-allowlisted, main-frame WebMessage bridge for gallery controls. The old Compose prototype is a separate module and package; its Keystore and queue tests are not automatically evidence for this WebView client.

## Service and domain separation

backend/src/finassist/domain contains standard-library calculation and validation logic. FastAPI routes establish authenticated ownership; services implement SQL transactions and business operations. Database, storage and provider adapters remain outside the domain. PostgreSQL row-level security and owner-aware constraints add protection beneath application scoping.

Uploads and their jobs are recorded transactionally. Workers claim jobs using leases and tokens; stale workers cannot persist results after their lease has been replaced. Extraction retries are bounded. Image purge jobs retain retry state instead of permanently abandoning deletion. Upload acceptance therefore precedes extraction, review and import.

| Boundary | Data and authority |
| --- | --- |
| Phone to local host | Candidate image, capture timestamp and expected owner assertion; authenticated session remains authoritative. |
| Backend to Anthropic | Consented image for extraction, or bounded conversation and financial tool data for chat. Image text cannot grant permissions. |
| Model to tools | Validated read, simulation or proposal requests. No approve, delete, consent-change or payment tool. |
| User to approval service | Explicit approval of an exact proposal, checked against current state and committed in one transaction. |

## Storage responsibilities

Core records include users and hashed sessions, accounts and balance observations, income schedules, transactions, bills, pockets and budget plans, goals, uploads and review items, jobs, consent grants, proposals, chat messages and audit events. Images are served through owner checks rather than public file paths. Chat retention is optional and distinct from transaction storage.

Implementation anchors: backend/src/finassist/api/routes.py, services/, infra.py, worker.py and db/migrations/; web/src/app/api/; android/pocketpal/src/main/kotlin/dev/finassist/pocketpal/.

# Image discovery extraction and review

## Discovery and candidate filtering

The scanner reads accessible MediaStore metadata, distinguishing undated, old, future and in-window images. Eligibility uses DATE_TAKEN within a rolling 30-day interval plus the user’s consent window. DATE_ADDED is not substituted. Full or selected-photo permission determines the visible set. JPEG and PNG inputs are bounded to 8 MiB.

Filter version 2 uses local Latin OCR. A candidate matches either the original English payment-word rule or a layout rule: decimal money, a masked account or long alphanumeric reference, and an HH:MM time or Buddhist-era year. This is an engineering heuristic, not a trained transaction classifier or a validated privacy boundary. Nonfinancial images can match and true slips can be missed. The eight policy tests use synthetic text, not an image accuracy benchmark [E3].

Each scan allows at most 100 local checks and ten upload attempts; each owner has a local daily cap of twenty attempts. Attempts are reserved before sending. Versioned rejection markers allow older-filter results to be inspected locally again; accepted metadata and content hashes avoid resending known accepted images. Cache migration still needs broader device regression evidence.

## Extraction and ledger decisions

The backend validates ownership, consent, size and image type before scheduling extraction. Schema-constrained extraction identifies document type, amount, date, time, counterparty, status and reference where available. Parsing and validation then decide whether the record can be imported or must await review. Processing permission alone does not grant auto-import permission.

An unresolved amount, direction or payment status does not contribute to financial totals. Review exposes server-defined allowed decisions and candidate records. A receipt can attach to an existing purchase without adding a second expense. A bill remains a bill until a payment is linked. Manual confirmation of an undated image is separate from automatic scanning.

## Known reference limitation

The active extraction contract has a single untyped bank_ref. Two printed identifiers on one slip may represent different fields. REF-GAP-1 can admit a duplicate when different fields are extracted; REF-GAP-2 can merge different payments when an untyped identifier and amount coincide. Both remain strict expected failures. A typed multi-reference contract is proposed in design document 14, not implemented. General duplicate safety is not claimed [E5].

## Diagnosis on the phone

Scan monitor separates metadata census, already uploaded/filtered records, consent exclusions, unreadable images, candidate matches and server acceptance. PocketPalScan logs contain fixed stages and aggregate counters rather than OCR or image content. Activity shows processing outcomes; upload counts alone do not establish completed OCR or import.

# Financial algorithms and conversation

## Balance and cash flow

All monetary records use integer satang. The starting balance is an observation at a specified date or timestamp. Only subsequent eligible transactions adjust its projection; earlier imported history remains available for analysis without subtracting spending already reflected in that balance. A date-only item on the balance date is treated as already reflected under the recorded product policy.

For the interval from today to, but excluding, the next income date: reserved funds equal eligible unpaid bills plus essentials not already represented by those bills, savings commitments and the buffer. Discretionary funds equal projected available balance minus reserved funds and any simulated purchase. Shortage is the positive magnitude of a negative discretionary balance.

For positive discretionary funds D and N days, daily allowance is floor(D/N) satang with the remainder recorded; weekly allowance is daily allowance multiplied by min(7,N). Negative discretionary funds display a shortage, never a positive available amount. Percentage buffers identify next income as their base; allocation percentages identify the distributable base.

## Pockets and goals

Pocket spending is counted within the active plan’s period using category-to-pocket mapping. Categorizing an older transaction changes historical reporting without necessarily changing current-period spending. A pocket transfer redistributes unspent allocations; it neither creates money nor becomes an expense. Budget checks run at proposal creation and again at approval. Bill-linked essentials are reserved once and internal transfer legs remain paired.

Goal functions use the target, saved amount, deadline, income events and available capacity to calculate required contributions and feasibility. Simulations do not create purchases or alter plans. Proposed plan or goal changes must pass the same approval boundary as chat-generated reallocations.

## Conversation and controlled actions

The agent can retrieve overview, spending, bills, reviews and insights; simulate a purchase or goal; and propose a budget, goal or reallocation. It uses at most eight tool calls across six model turns. Financial values come from current tools rather than remembered prose. Responses render restricted Markdown and approval cards.

Tab switching retains owner-bound UI conversation state. With explicit history consent, the server supplies bounded recent context: at most twelve messages and 12000 characters, with a stored-history cap of 200 messages. New chat clears conversation history, not financial records. No embedding database or vector RAG is used. Account changes, stale results and revocation are handled separately from financial data persistence [E1, E2].

Innovation is the combination of local filtering, uncertainty-aware review, deterministic finance tools and human-approved action. This is an implementation contribution; no research novelty or measured superiority over other assistants is claimed.

# Reproduction and operational workflow

## Local demonstration setup

Use a Mac with the repository dependencies, Android SDK, Java 17 or later compatible with the project, and an authorized USB-connected S22. Configure the Anthropic secret only in the backend environment. There is no seeded login; create a demonstration account. The gallery profile is separate from dev, e2e, test and realeval.

cd ~/Development/case/shenzen/backend
uv run --with pixeltable-pgserver python scripts/dev_server.py --profile gallery --provider anthropic

In a separate terminal, build the web once after source changes, then start it:

cd ~/Development/case/shenzen/web
npm ci
npm run build
FINASSIST_BACKEND_URL=http://127.0.0.1:8002 npm run start -- --hostname 127.0.0.1 --port 3002

Build and install the current APK while retaining its data:

cd ~/Development/case/shenzen/android
export ANDROID_HOME="$HOME/Library/Android/sdk"
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
export PATH="$ANDROID_HOME/platform-tools:$PATH"
./gradlew :pocketpal:testDebugUnitTest :pocketpal:assembleDebug
adb install --user 0 -r pocketpal/build/outputs/apk/debug/pocketpal-debug.apk
adb reverse tcp:3002 tcp:3002

## Demonstration sequence

Sign in, set balance and income, grant processing and optional auto-import consent, then open Settings → Slips from the last 30 days. Grant photo access, explicitly enable scanning and select Scan now. Observe the monitor and refresh Activity. Resolve uncertain fields, inspect totals, ask Chat about spending and approve a clearly explained budget proposal only if desired.

For test copies pushed by adb, MediaStore may require a rescan before the app can discover them. The owner’s device used: adb shell content call --method scan_volume --uri content://media --arg external_primary. This is device test preparation, not a production app requirement or permission bypass. Confirm capture metadata without inventing dates.

Do not use --reset against gallery or dev, clear app data, or remove original photos. Unit and integration tests must use disposable isolated profiles. Background scheduling depends on Android; a force-stopped app must be opened again. A standalone release requires hosted HTTPS services and deployment verification not provided by this runbook.

# Requirements and evidence register

| Product feature | Current evidence boundary |
| --- | --- |
| 1 Account and setup | Implemented; automated identity/ownership coverage. Final onboarding completeness needs team review. |
| 2 Automatic scanning | Owner reports successful dated-image flow; undated slips excluded, mixed-gallery accuracy and full device acceptance open. |
| 3 Manual transactions | Backend CRUD and validation coverage; complete current web/mobile flow acceptance not established here. |
| 4 Pockets | Allocation/spending and approval-backed changes implemented; complete CRUD and arbitrary editing coverage requires review. |
| 5 Everyday budgeting | Deterministic calculations and proposal checks tested; recommendation quality not generally benchmarked. |
| 6 Goals | Backend feasibility and proposals implemented; complete device interaction acceptance pending. |
| 7 Bills and insights | Backend linking and reporting tested; real gallery-to-insight reconciliation pending. |
| 8 Chat | Connected tools and consented context; scripted tests establish controls, not broad model quality. |
| 9 Security and privacy | Controls implemented with gaps; see companion self-assessment. Deployed encryption not evidenced. |
| 10 Storage and backend | Relational records, jobs and calculation services implemented; reference gaps remain open. |
| 11 Gamification | Optional; not claimed as delivered. |

## Evidence identifiers

All paths below are relative to evidence/runs/. Counts apply to the recorded source snapshot, not automatically to later edits.

E1 20261017T012325Z-conversation-gallery-backend/manifest.json: 300 passed; two strict reference xfails serialized as skipped. Real PostgreSQL and storage; fake extraction and scripted chat. E2 20261017T012328Z-conversation-browser/manifest.json: five mocked conversation checks.

E3 20261017T020449Z-pocketpal-scanpolicy-v2-cloud/: eight synthetic-string policy tests reported by Claude. E4 20261017T040000Z-pocketpal-gallery-dated-scan-owner/summary.md: owner report only, approximate timestamp, no successful-scan logcat captured. E5 20261016T122231Z-reference-contract-regressions/: 57 passed and two open strict xfails.

E6 20261016T120301Z-real-slip-r2-score/manifest.json: five-image unseen pilot; core fields 5/5 but bank_ref exact match 0/5 with later owner-reported field ambiguity. This is not a general OCR accuracy estimate. E7 20261017T015252Z-native-controls-browser/: pre-v2 mocked monitor checks and APK install record; does not validate the later v2 monitor.

## Submission completion

Original sources: docs/We go shenzhen case (1).docx and the supplied International Track competition PDF, pages 2–3. The team must still finalize the source revision and GitHub link, presentation, sanitized sandbox execution logs and demonstration video. No competition score is inferred from test counts. This document does not close CP3b.
