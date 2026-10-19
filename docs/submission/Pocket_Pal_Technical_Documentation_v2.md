# POCKET PAL
# SYSTEM ARCHITECTURE AND TECHNICAL SPECIFICATION
@author Pocket Pal Project Team
@subtitle Algorithms, data flows and security design
@version Version 2.0 | Implementation baseline 17 October 2026

## Abstract
@abstract Pocket Pal is a personal financial assistant that converts user-authorized financial images into a reviewable ledger and answers financial questions through constrained tools. Its architecture combines a mobile gallery scanner, a web interface, an authenticated API, a transactional relational database and asynchronous model-assisted extraction. Financial arithmetic and authorization remain deterministic: the language model may retrieve, simulate and propose, while the user approves changes to plans and goals. This specification describes the implemented topology, document processing state machines, duplicate detection, budget and cash-flow algorithms, conversation orchestration, and security boundaries. It also defines the relationship between transport acceptance, extraction completion and ledger inclusion, which is essential for interpreting scan results. Verification comprises synthetic automated tests, a small real-image extraction pilot, and separately identified owner-reported device observations. The current deployment is a local proof of concept with an Android WebView host; production hosting, comprehensive gallery classification evaluation and several lifecycle controls remain open. The document therefore provides an implementation-grounded engineering specification and identifies the additional verification and controls required before production release.

@keywords Keywords: personal finance; document extraction; transactional integrity; constrained agents; consent; Android gallery scanning; human approval.

## 1 INTRODUCTION AND SCOPE
### 1.1 Purpose and intended audience
This specification enables engineers, security reviewers and competition evaluators to understand how Pocket Pal derives financial information, where authority resides, and which claims are supported by execution evidence. It describes the source baseline of 17 October 2026. The design is sufficiently explicit to support implementation review and operational planning; it does not certify production readiness or regulatory compliance.

The primary product requirement is the original case document [S1]. Competition rules and submission requirements [S2] follow it in authority, followed by approved design decisions. Features 1–10 remain required and feature 11 is optional. LINE integration is excluded. Pocket Pal records and plans finances; it does not initiate real bank transfers, settle payments, or establish that an uploaded image represents an authentic bank transaction.

### 1.2 System boundary and implementation status
The active mobile experience is the Pocket Pal web interface hosted by the Android module android/pocketpal. The earlier Compose application under android/app is a separate implementation and evidence lineage. Authentication and upload queue tests from that earlier client do not automatically prove equivalent behavior in the WebView application.

The implemented backend supports manual and imported records, review decisions, pockets, budgets, bills, goals, deterministic simulations, proposals and conversational tools. The current phone deployment depends on local services and USB port forwarding. Automatic scanning has been observed by the owner on a Galaxy S22 Ultra, but complete device acceptance remains open. No overall completion percentage is inferred from test counts.

### 1.3 Interpretation of evidence
Implemented means a control or feature exists in source. Automated verification means a named execution run exercised a defined scenario. Owner-reported means a person observed behavior without equivalent machine-captured evidence. A production target is a future requirement, not a deployed control. Sections 13 and 14 preserve these distinctions. All examples in this specification are illustrative synthetic values, not customer records.

## 2 DESIGN PRINCIPLES AND DECISIONS
### 2.1 Separation of prediction from financial authority
Model output is an untrusted interpretation of an image or a request. It cannot directly authorize a ledger mutation, approve a proposal, delete data, or change consent. Deterministic validation decides whether extracted data is eligible for import. User-approved proposals are applied by transactional services, which revalidate their preconditions at commit time.

This separation addresses two different error classes. Extraction can produce a plausible but incorrect amount, date or reference. Conversation can produce persuasive but unsupported advice or an inappropriate tool request. Schema restrictions constrain the structure of output; financial invariants and authorization checks constrain its effect. Neither mechanism guarantees that the original image is genuine.

### 2.2 Modular boundaries
The domain package imports only the Python standard library. It contains money, cash-flow, allocation, classification, validation and duplicate rules. Services coordinate these rules with SQL, storage and providers. HTTP adapters validate requests and derive the owner from the authenticated session. Database and external-service dependencies remain outside the domain layer. Services currently issue SQL directly; there is no independent repository abstraction to imply additional isolation.

### 2.3 Determinism and conservative uncertainty
All financial values use integer satang. Percentage inputs carry a named base and are represented in basis points where applicable. Unknown or invalid critical fields enter review instead of receiving invented defaults. Exact image hashing and request idempotency address different repeat mechanisms. Ambiguous transaction identity remains an explicit open problem rather than a reason to silently merge records.

## 3 SYSTEM ARCHITECTURE
### 3.1 Deployment topology
The web application uses Next.js, React and TypeScript. Its backend-for-frontend route translates an HttpOnly web session cookie into a bearer token for the FastAPI service. PostgreSQL stores owner-scoped records, jobs, proposals and audit events. A local private file store holds uploaded images. Extraction and chat providers run outside the trusted application boundary. The API key is configured on the backend only.

@figure topology|Figure 1. Implemented topology and external model boundary. Arrows show requests or data dependencies, not equivalent privilege.

The Android host supplies the native capabilities unavailable to an ordinary browser tab: MediaStore access, local OCR filtering and WorkManager scheduling. Manual upload remains available through the web interface. The native HTTP client snapshots the WebView cookie and submits through the same-origin BFF. Both routes converge on the same server validation and owner-scoped ingestion services. The external extraction provider receives selected image content; the chat provider receives permitted conversational context and tool results.

### 3.2 Component responsibilities
| Component | Primary responsibility | Authority boundary |
| Web interface and BFF | Chat, pockets, activity, review and cookie mediation | Cannot establish financial truth or bypass API checks |
| Android gallery host | Permission checks, dated-photo selection, local candidate filter, bounded upload | May submit only under owner and consent gates |
| API and services | Authentication, validation, transactions and deterministic tool execution | Derive owner from session; enforce operations |
| Domain package | Pure financial and document rules | No network, database or provider access |
| PostgreSQL | Durable state, constraints, row isolation, leases and watermarks | Privileged administration remains trusted |
| Worker | Claim jobs, call extraction, persist validated results, retry purges | Cross-owner job discovery is a limited exception |
| External model provider | Structured extraction and constrained conversational generation | No database credentials or approval capability |

### 3.3 Interaction patterns
Read operations resolve a session, bind owner context, query current data and calculate a response. Write operations additionally validate request intent and apply changes within a database transaction. Long-running image extraction is asynchronous: an upload response acknowledges receipt, then the worker advances the image to an imported, rejected, failed or review state. The interface must not interpret a successful HTTP upload as a completed financial record.

The active gallery profile exposes the backend on local port 8002 and the web application on 3002. Older dev flows use 8000 and 3000. The dev, e2e, test, realeval and gallery profiles separate database and storage resources. This separation was introduced after an automated test reset affected a device-testing database; future execution must retain profile boundaries.

### 3.4 Trust boundaries
The first boundary separates user-controlled images, text and browser requests from the API. The second separates the web/native client from backend session and database authority. The third separates the application from the external model provider. A fourth separates ordinary owner-scoped database access from administrative and worker privileges. Security controls are described against these boundaries in Section 9, rather than assuming all traffic inside a local machine is equally trusted.

## 4 DATA AND DOMAIN MODEL
### 4.1 Principal entities
| Entity | Essential information | Integrity purpose |
| User and session | Owner identity, token digest, expiry and revocation | Resolve authenticated authority |
| Account and balance observation | Account identity, observed balance and effective time | Anchor projected balances |
| Transaction | Amount, kind, payment status, occurrence, category, provenance | Count only eligible financial effects |
| Upload and extraction | Content hash, capture metadata, state, parsed fields, model metadata | Trace an image through validation |
| Review item and evidence link | Permitted decisions, candidate records, resolution | Preserve ambiguous evidence without double counting |
| Pocket and plan | Category mapping, allocation, period and version | Separate intended budgets from actual spending |
| Bill and goal | Due dates, commitments, targets and progress | Reserve or simulate future needs |
| Proposal | Payload, card, hashes, base versions, status and expiry | Bind user approval to a particular plan change |
| Job and owner watermark | Lease token, attempts, schedule; owner revision | Coordinate retries and stale-state detection |
| Consent and audit | Scope, dates, status; event metadata | Record permission and consequential actions |

@figure entities|Figure 2. Selected ownership and evidence relationships. An upload can supply a transaction evidence link as well as extraction and review records.

### 4.2 Units and temporal semantics
One baht equals 100 satang. Financial APIs and domain functions carry integer satang; formatting to a decimal currency string occurs at the presentation boundary. A negative available amount must remain negative or be described as a shortfall. Displaying an absolute magnitude is appropriate only when an explicit direction label supplies the sign.

Capture time, transaction occurrence time, upload time and processing time are distinct. The native rolling window concerns capture metadata. Ledger periods concern interpreted transaction dates in the user's time context. A copied image may have a recent filesystem time but no original capture date; substituting that filesystem time would change consent semantics. A bill due date is likewise distinct from its document date.

### 4.3 Provenance and correction
Transactions retain their source relationship so that imported evidence, manual records and later receipt attachments can be distinguished. Predicted categories are separate from confirmed choices. Review corrections must be explicit and restricted to fields the API accepts. A receipt attached to an existing purchase adds evidence; it must not create another expense. Corrections and deletions update the owner watermark so previously calculated proposals can be rejected as stale.

## 5 DOCUMENT INGESTION AND REVIEW
### 5.1 Gallery eligibility and bounded scanning
The Android scanner uses MediaStore DATE_TAKEN. It classifies visible metadata into UNDATED, OLDER, FUTURE and IN_WINDOW. The eligible interval is the last 30 days; unknown capture dates are excluded from automatic submission. DATE_ADDED is not a substitute. Selected-photo permission limits the accessible set even if more images exist on the device.

Each run performs at most 100 local checks and 10 upload attempts. The daily owner limit is 20 attempts, reserved before transmission. Supported files are JPEG or PNG with a maximum size of 8 MiB. These are application safeguards, not a promise about the provider's total billing across all clients. WorkManager schedules periodic work at a nominal 15-minute interval and supports a manual Scan now action; operating-system scheduling does not guarantee an exact completion time.

### 5.2 Local candidate filtering
Filter version 2 combines the existing English slip rule with a layout rule. The English branch requires payment-related vocabulary, a decimal amount and supporting banking or transaction terms. The layout branch requires all three of the following: an amount with two decimal digits; a masked account or a long alphanumeric reference containing sufficient digits; and either an HH:MM time using a colon or a Buddhist Era year in the configured range. A long reference is at least 12 characters with at least six digits.

These rules operate on locally recognized text. They are heuristic candidate selection, not a trained expense-purpose classifier. A receipt or another document with the same structure can pass. A genuine slip with weak local OCR or a different layout can fail. The moneyOnly counter is diagnostic and does not itself authorize upload. No mixed-gallery image benchmark currently establishes filter precision or recall.

### 5.3 Cache migration and repeat handling
The local cache distinguishes accepted content, server-refused content and versioned filter rejection. The corresponding markers are acc:, rej: and flt:v2:. Legacy seen: metadata entries are eligible for one local recheck under the new filter; an accepted content hash prevents retransmission of an already accepted image. A prior refusal may consume one additional attempt before receiving its new refusal marker. Metadata outside the consent window can be revisited cheaply without decoding an image.

The cache is an optimization, not the authoritative duplicate ledger. Clearing or migrating client state must not bypass server-side image and transaction checks. Conversely, a cache hit cannot prove successful extraction because receipt by the API and ledger import are separate outcomes.

### 5.4 Server admission
The API derives owner_id from the session. expected_owner_id is an additional assertion to detect a mismatched client queue; it never grants authority. Admission checks consent, content size, JPEG/PNG signature and capture metadata. Missing capture time requires explicit confirmed_undated for manual submission. Automatic scanning never sets this confirmation. The manual path records the confirmation in audit.

The current upload boundary checks the lower consent-date bound. Extracted transaction validation later considers the configured consent date range, while the native scanner applies its own capture window. This layered behavior is not a claim that both capture bounds are centrally enforced at admission. Consolidating date policy and timezone semantics is a release-hardening task.

For an existing non-deleted image with the same owner and SHA-256 digest, the API returns the existing upload rather than another ingestion. Otherwise it stores the object and inserts an upload and extraction job. The object write precedes the database commit; these operations are not a distributed atomic transaction. Orphan reconciliation after a database failure remains an operational gap.

### 5.5 Extraction state machine
@figure ingestion|Figure 3. Main upload states. Review resolution, consent cancellation and deletion add guarded transitions; accepted transport is only the received state.

A worker claims a queued job, marks the image extracting, and requests structured extraction outside the database transaction. The provider result is restricted to the extraction schema. Persistence reacquires the relevant locks, validates the current lease and consent, and verifies that the upload still permits processing. A stale worker result cannot overwrite the result of a newer lease.

Validation normalizes dates and amounts without treating model confidence as financial authority. A model indication that the image is unreadable blocks automatic import. Implausibly distant dates are routed to review; the 400-day guard prevented a known synthetic year-reading error from becoming an automatic import. English-month date parsing was added after the real-slip pilot exposed parser rejection of otherwise correct extracted dates. This improves accepted syntax; it does not prove universal date-reading accuracy.

### 5.6 Routing and review decisions
A non-financial document is rejected. Invalid critical fields enter review. Bills require their mandatory fields and auto-import consent; they create bills rather than ordinary transactions. Financial records undergo duplicate analysis before consent-controlled import. Without auto-import consent, otherwise valid data still requires confirmation.

The server returns allowed_decisions and candidate records. The client renders only those decisions and requires a candidate choice when necessary. The server independently validates the submitted choice and candidate identifier. Accepted decisions may include accept, not_a_transaction, duplicate_of, link_receipt and distinct, depending on the item. Bills may require a due date; an unknown document type or payment status has no default selection.

A resolved item is not a successful second resolution. HTTP 404 means it is no longer available for that action, and a network failure means the result may be unknown. The interface refreshes authoritative data instead of declaring an unconfirmed success. An idempotent retry contract for every review action is not assumed.

### 5.7 Duplicate decision algorithm
Candidates contain record identity, document type, amount, occurrence time/date, payee key and bank reference. The service retrieves owner-scoped candidates using reference equality or temporal proximity. The domain algorithm applies ordered rules; the first applicable result controls routing.

| Priority | Condition | Result |
| 1 | Normalized reference and amount both equal | Treat as the same payment |
| 2 | Reference equal but amount differs | Review |
| 3 | References at least eight characters, length difference at most two, edit distance at most two, amount equal | Review |
| 4 | Receipt and slip, amount equal, close time or matching date, compatible payee | Review as possible purchase evidence |
| 5 | Missing reference, same amount/day and compatible or unknown payee | Review |
| 6 | No applicable match | New transaction candidate |

Reference normalization uppercases and retains alphanumeric characters. It does not resolve the semantic difference between Transaction ID, Transaction No. and another printed reference. The real pilot demonstrated this ambiguity. Two known gaps remain: alternate reference fields may fail to identify the same payment, and an untyped reused reference with the same amount may cause a false merge. Typed multi-reference storage is proposed, not implemented. Image perceptual hashes are not used by the import matcher because template similarity is not reliable transaction identity.

For candidate count k and reference lengths m and n, approximate-reference matching costs O(kmn) in the worst case with O(n) edit-distance working memory. Database candidate narrowing reduces typical work but does not improve the semantic validity of the reference. Case or glyph ambiguity must not be silently equated to successful identity verification.

### 5.8 Category suggestions
Category suggestion precedence is an explicit user default, then dominant confirmed history, then a seed mapping, then unclassified. The historical rule requires at least two confirmed observations and a dominant share of at least 80 percent of that payee's confirmed observations. The current service has no populated seed mapping. Payee normalization handles Unicode, case, honorifics, masked account fragments and punctuation; intermediary patterns may trigger abstention unless the user supplied a default.

The same merchant can serve different purposes. Consequently, historical agreement is a convenience signal, not evidence that a new purchase has the same purpose. Unclassified spending remains visible and contributes to the appropriate totals without fabricating a category. Future model-based categorization would require independently evaluated labels and calibrated abstention.

## 6 FINANCIAL ALGORITHMS AND INVARIANTS
### 6.1 Eligibility and projected balances
Let a transaction's signed effect be negative for expense and transfer_out, and positive for income, refund and transfer_in. A transaction contributes only when its payment status is completed and its amount and direction are confirmed. Pending, failed, scheduled and unresolved records do not contribute to the financial totals.

@equation (1) B(a,t) = O(a,t₀) + Σ eligible signed effects for account a after t₀ through t

O is a balance observation for one account at its effective time. The implementation distinguishes timestamped and date-only transactions. A timestamped transaction is reflected if it occurred at or before the observation; a date-only transaction on or before the observation's local date is assumed already reflected. An observation for one account does not replace another account's balance.

An internal transfer has one out leg and one in leg of equal amount and aligned status/time. The group changes account distribution but has zero aggregate effect. Deferred database constraints validate the completed pair at commit, including hard deletion and movement between groups. A single external transfer_out without a group is permitted. Internal transfer legs must not be reported as ordinary spending merely because one leg is negative.

### 6.2 Cash available before the next income
The planning interval runs from today to, but excludes, the next income date. Reservations include unpaid bills due before that income, including overdue bills, eligible essential costs not already represented by a bill, savings commitments and a buffer. The buffer can include a fixed amount plus an integer fraction of the next income. Double reservation of a bill and its corresponding essential cost must be avoided.

@equation (2) buffer = fixed buffer + floor(next income × buffer basis points / 10 000)
@equation (3) D = projected balance − reserved obligations − hypothetical purchase
@equation (4) shortfall = max(0, −D)

D is discretionary cash under the configured inputs, not a bank-certified available balance. For N days until the next income, a nonnegative D yields daily allowance floor(D/N) with remainder D mod N. A nonpositive D produces zero suggested daily spending and a separately displayed shortfall. Weekly allowance uses the daily value multiplied by min(7,N). Domain validation handles invalid planning inputs before division.

For an illustrative D of 100,003 satang over seven days, the daily allowance is 14,286 satang with one satang left over. Reporting THB 142.86 per day preserves the integer calculation; distributing seven rounded decimal estimates without tracking the remainder would lose precision.

### 6.3 Proportional pocket allocation
Let B be the nonnegative allocation base and wᵢ be a pocket weight in basis points. Each weight is between zero and 10,000 and their sum is at most 10,000. The base must be named in the user-facing plan, because a percentage without a base is ambiguous.

@equation (5) qᵢ = floor(B × wᵢ / 10 000)
@equation (6) T = floor(B × Σwᵢ / 10 000)

The algorithm assigns the remaining T − Σqᵢ satang to the largest fractional remainders, using stable input order for ties. The unallocated amount is B minus the final sum. Thus total allocated plus unallocated equals B exactly. For B = 10,001 and weights 5,000/3,000/2,000, final allocations are 5,001/3,000/2,000 satang.

```text
allocate(B, weights):
  validate B >= 0 and sum(weights) <= 10000
  q[i], r[i] = divmod(B * weights[i], 10000)
  target = floor(B * sum(weights) / 10000)
  distribute target - sum(q) units by descending r
  return q, B - sum(q)
```

### 6.4 Reallocation and funding checks
A reallocation requires distinct known pockets and a positive amount. It transfers only unused allocation; it does not create income or an expense. Total allocation remains conserved. If a pocket is already overspent, it cannot supply fictitious unused funds.

The funding invariant compares aggregate unused allocation against current discretionary cash under the proposed buffer. For allocations Aᵢ and relevant spending Sᵢ, define U = Σ max(0,Aᵢ − Sᵢ). A new or expanded funding requirement must satisfy U ≤ max(0,D). A limited shortcut permits an existing plan to reduce or preserve U only in the same period without increasing the buffer. Changing the period or increasing the buffer forces full revalidation. Both proposal creation and approval enforce the applicable rule.

### 6.5 Goal feasibility
For target G and saved amount S, remaining need is max(0,G−S). Income events are enumerated up to the goal deadline using the selected weekly, fortnightly, monthly or limited irregular schedule. Monthly enumeration preserves the intended day with month-end clamping. With n eligible events, the required contribution is ceil(remaining/n); no-event cases must remain explicitly infeasible unless the goal is already met.

Feasibility compares the required contribution to the supplied capacity. Progress is capped at 10,000 basis points and uses integer division. Alternatives can compute a smaller feasible target, additional required capacity or a later date within the search horizon. These results are deterministic scenarios based on entered assumptions, not predictions of future earnings or investment returns.

### 6.6 Transactional proposal approval
Every proposal stores a canonical payload hash, an approval-card hash and the base plan, goal and owner revisions on which it depends. Reading the owner watermark before calculating the card makes subsequent ledger changes detectable. The card communicates consequences; it is not authority to commit by itself.

@figure approval|Figure 4. Approval transaction. All financial checks and the resulting write occur while the relevant locks remain held.

Approval first acquires the owner ledger advisory lock and then locks the owner watermark row. It locks the proposal, validates state and expiry, compares the submitted hashes, rechecks applicability and funding, and compares base revisions. A stale proposal is rejected with a replacement card when applicable. An expired, superseded, cancelled or already applied proposal cannot be treated as a fresh approval. Successful application updates the financial plan, proposal state, watermark and audit in one transaction.

Idempotency keys bind an owner and key to a request scope and canonical body digest. Reuse with a different body is rejected. A successful response is stored with the mutation so an identical retry can return the same outcome. Concurrent retries serialize through the database constraint. This is protection against repeated requests, not a general claim of exactly-once processing across every external system.

## 7 CONVERSATIONAL ASSISTANT
### 7.1 Tool authority and orchestration
The assistant resolves financial questions through a bounded tool loop. Read tools obtain overview, spending, bills, review items and insights. Simulation tools evaluate purchases and goals. Proposal tools prepare tradeoffs, reallocations, budgets or goals. No model-facing tool approves a proposal, changes consent or deletes user data.

| Tier | Allowed operation | Executing authority |
| T0 | Read financial state | Owner-scoped service |
| T1 | Simulate without persistence of a financial change | Deterministic domain function |
| T2 | Create a proposed change | Proposal service |
| T3 | Commit a proposed change | Authenticated user approval |
| T4 | Import validated documents | Worker under current consent |
| T5 | Consent and data lifecycle controls | Authenticated user action |

The loop permits at most six model turns and eight tool calls per request. Tool arguments are validated before execution. Current financial values come from tools rather than the model's memory. Tool failures and missing data must be described as uncertainty, not filled with fabricated balances. The provider is replaceable behind an adapter; the configured model names are deployment configuration, not an availability guarantee.

### 7.2 Conversation continuity without vector retrieval
Tab switching preserves the current conversation in owner-scoped client state. Persistent history requires chat_history_retention consent. Backend context is bounded to 12 messages and 12,000 characters, with a 4,000-character per-message limit; retained history is capped at 200 messages. New chat clears conversation history without deleting transactions or plans.

There is no vector database or retrieval-augmented document index in this baseline. It is not required merely to retain recent chat. Structured tool queries already retrieve authoritative financial state. A future retrieval layer would need a defined corpus, owner isolation, retention policy and evaluation of retrieved evidence; it should not turn old conversation text into current financial truth.

### 7.3 Isolation and safe rendering
Owner and request-generation guards prevent a late response from a previous account from updating the current interface. History operations serialize by owner and recheck retention consent so revocation does not silently restore messages. The earlier native client also has token compare-and-clear and session-epoch tests; those are evidence for that client, not a substitute for evaluating WebView session handling.

Chat renders Markdown with restricted handling. Raw HTML and model-provided images are not rendered, and link handling is constrained. Formatting is a presentation concern: rendering a table correctly does not make its numbers correct. For financial answers, the server's current tool results and the user's explicit approval remain the authoritative path.

## 8 API INTERFACES
### 8.1 Authentication and response conventions
The backend exposes /v1 routes. Authenticated requests use a bearer session token. Browser clients send the HttpOnly session cookie to the same-origin BFF, which forwards the token to the backend. Mutation requests undergo an exact-origin check at the BFF. The BFF constrains paths, forwarded headers and request size; the backend independently enforces its stricter image limit.

Application errors contain a stable code, message, field issues, retryable flag, request identifier and optional details. X-Request-Id supports correlation. Invalid request schemas are mapped by the application rather than assuming all validation errors use framework defaults. A client must distinguish consent failure, stale state, permanent input error and temporary network uncertainty.

### 8.2 Principal endpoint contracts
| API group | Representative operations | Contract emphasis |
| Identity | POST auth/signup, auth/login, auth/logout; GET me | Session-derived owner |
| Setup | GET/PUT me/profile; account balance observations | Explicit financial anchors |
| Consent | GET/POST consents; DELETE consents/{scope} | Separate scopes and revocation |
| Ledger | GET/POST transactions; PATCH/DELETE transactions/{id} | Confirmed values and owner isolation |
| Categories | POST transactions/{id}/category | Explicit user classification |
| Bills and pockets | GET/POST bills; bill link-payment; GET/POST pockets | No duplicate expense for bill evidence |
| Planning | GET plan; POST plan/suggest and plan/tradeoff | Proposal creation, not implicit approval |
| Goals | POST goals/feasibility; GET goals | Scenario calculation and confirmed goals |
| Proposals | Create, read, edit, cancel and approve | Hashes, versions, expiry and idempotency |
| Images | POST/GET uploads; image, retry and DELETE by id | Consent, type, size and owner checks |
| Review | GET review-items; POST {id}/resolve | Server-authorized decisions and candidates |
| Conversation | POST chat; GET/DELETE chat/messages | Bounded tools and history consent |
| Operations | GET scan-status, health and audit | Safe metadata and explicit test mode |

All paths in the table are relative to /v1. The table is an architectural index; request models and route definitions remain the executable schema. Unknown or unsupported operations must not be inferred from a UI label.

### 8.3 Upload and approval envelopes
An upload is multipart data with an image and optional captured_at, confirmed_undated and expected_owner_id fields. A new admission returns an accepted upload identifier/state; an exact duplicate can return the existing object. OWNER_MISMATCH is a conflict, while CAPTURE_DATE_REQUIRED requests explicit manual confirmation. Retries are limited to supported failed or cancelled states and recheck consent.

Approval sends payload_hash and card_hash with an Idempotency-Key. The server compares these with persisted values and checks current applicability inside the transaction. Review resolution uses decision, changed fields and an optional candidate txn_id. The client must not copy a proposal approval guarantee onto review resolution where the contract differs.

## 9 SECURITY DESIGN
### 9.1 Security objectives and assets
The principal assets are session credentials, private images, extracted financial records, chat history, consent state, provider credentials and audit evidence. Confidentiality requires owner isolation and controlled external disclosure. Integrity requires accurate attribution, deterministic arithmetic and user authority over plan changes. Availability requires bounded work and recoverable jobs without silently dropping required deletion work.

The threat model includes a malicious authenticated user, a forged or adversarial image, prompt injection inside documents or conversation, repeated requests, stale clients, a stolen session, and accidental operator cross-environment actions. Compromised operating-system administrators, database superusers and the external provider's internal systems are not controlled by application row policies; they remain distinct trust assumptions and deployment risks.

### 9.2 Threat and control matrix
| Threat | Implemented mitigation | Residual limitation |
| Cross-owner object access | Session owner, service filters, forced RLS | Privileged database roles remain trusted |
| Model-induced unauthorized change | Tool tiers, no approval tool, server validation | Proposal quality can still be poor |
| Prompt injection in image text | Structured extraction and deterministic routing | Valid-shaped incorrect output remains possible |
| Replay or double approval | Request digest, idempotency, locks and proposal state | Not a universal duplicate-payment guarantee |
| Stale financial decision | Owner watermark, versions, hash-bound card | Uncaptured external financial changes are unknown |
| Private data in logs | Safe event codes and exception frame logging | Operational log access/retention needs deployment policy |
| Excess gallery disclosure | Permission, dated window, local filter and caps | False-positive candidate uploads remain possible |
| Orphan or undeleted image | Logical denial and durable purge retry | Storage reconciliation and physical deletion monitoring needed |
| Resource exhaustion | File caps, bounded tools, scan and model limits | Comprehensive ingress rate limiting not established |

### 9.3 Authentication lifecycle
Passwords are hashed using the configured Argon2 library rather than stored or encrypted reversibly. The service creates a random 32-byte session token, stores its SHA-256 digest and uses a seven-day expiry. Logout records revocation. Possession of a valid token grants session authority, so transport and client storage remain material security boundaries. Parameter benchmarking, MFA, account recovery and comprehensive credential-abuse controls are not claimed as complete.

### 9.4 Authorization and row isolation
Each request obtains owner_id from the session and binds it to the database connection context. Owner-scoped tables use enabled and forced row-level security. The normal API role has no BYPASSRLS privilege. Current request connections are separately scoped; an eventual pool must reset owner context before reuse. RLS supplements service filters and is not a defense against a fully compromised privileged backend.

User identity, session lookup and shared category tables have different access requirements and are not all governed by owner RLS. The worker must discover queued jobs across owners, then bind the claimed job's owner before accessing owner data. This exception should remain minimal and explicit in database-role reviews. PostgreSQL's documented policy and privileged-role behavior must be considered when deploying migrations [R1].

### 9.5 Browser session and request security
The BFF cookie is HttpOnly and SameSite Strict; Secure is enabled on HTTPS. Exact-origin mutation checks complement cookie policy. Neither setting protects a token once a malicious same-origin application can act as the user, so rendering and origin restrictions remain necessary. The backend validates authorization independently of BFF routing. Production HTTPS termination and end-to-end transport policy require a deployment decision; the local USB/loopback configuration is development infrastructure.

### 9.6 Android host security
The WebView allows only the configured application origin and uses an origin-restricted main-frame messaging bridge. File and content access, mixed content, TLS-error bypass, backup and WebView debugging are disabled in the intended host configuration. Debug HTTP is limited to the local development origin. A release origin must be configured for HTTPS; a placeholder origin is not a deployed service.

Android photo access can be full, selected or denied. The application must inspect current permission rather than assuming a previous grant persists. Android 14 selected-photo behavior affects how many images a scan can see [R2]. The legacy Compose client's AES-GCM Keystore implementation does not establish that the new WebView cookie uses the same storage mechanism. The current host relies on the WebView and application sandbox for cookie storage.

### 9.7 Consent workflow
Photo processing, automatic import and history retention are separate consent scopes. Scanning requires OS photo permission and application consent; one does not replace the other. Manual undated-image confirmation is specific to selected images and must not become blanket permission for unknown-date background scanning.

Revocation prevents further authorized persistence and cancels applicable queued work. The worker rechecks consent when persisting extraction. A request already sent to a provider cannot be recalled by a local consent change. The specification therefore does not promise that an in-flight provider request disappears on revocation. User-facing wording and operational deletion procedures must reflect this boundary.

### 9.8 Encryption and secret handling
Provider credentials are backend environment secrets and are not embedded in web bundles, APK configuration, prompts or evidence. Session digests reduce the value of a direct session-table disclosure compared with plaintext tokens, but do not replace secure transport. Local image files use restrictive file permissions. Full-disk encryption, encrypted database backups and storage key rotation have not been established by the POC evidence.

For production, a documented TLS configuration, encrypted persistent storage and backups, secret rotation, least-privilege secret access and recovery procedures are required. These are release requirements, not retrospective claims about the local deployment. Password hashing, bearer-token hashing and data encryption solve different problems and must not be conflated.

### 9.9 Model and document security
The extraction provider receives image content only after the applicable user authorization path. Ground-truth labels are excluded from extraction prompts during evaluation. Text embedded in a slip is treated as document data, not application instructions. Model output cannot add arbitrary schema fields or assign owner identity. Invalid critical information is routed to review.

These controls reduce the effect of prompt injection but do not establish OCR correctness. The model may return a plausible wrong year, merchant or reference that satisfies syntax. Review gates, bounded date rules, provenance and ledger replay are necessary complementary controls. Bank authenticity verification is not implemented.

### 9.10 Deletion and retention
Image deletion first makes the resource inaccessible through the API. The key remains available to a durable purge job until physical deletion succeeds or absence is confirmed. Purge retries do not permanently die after the normal extraction attempt limit. Repeated deletion requests can recover pending work. Audit records distinguish failure and overdue deletion.

Deleting imported application data does not delete original photographs from the phone. The current imported-data deletion endpoint is not a comprehensive account erasure workflow. Provider retention, backups and logs require separately specified lifecycle agreements. Chat-history consent and clearing operate on conversation data without silently removing the financial ledger.

### 9.11 Audit and privacy
Audit events record consequential operations with owner attribution and bounded metadata. Operational exception logging records event identifiers, exception types and stack frames without exception messages that may contain user text. Native scan logs record fixed stages, timestamps, aggregate counts and HTTP status; they exclude filenames, image paths and OCR text.

Logs still require access control and retention limits. A support bundle should contain request identifiers, versions, profile and safe counters rather than images or secrets. A complete tamper-evident remote audit service is not established by the local append operations and database records alone.

### 9.12 Security assurance boundaries
The security evidence is composed of targeted control tests, concurrency tests and regression cases, not an independent penetration test or compliance certification. Permission tiers and threat mappings support review, but do not by themselves satisfy a regulatory framework. The separate Security Self Assessment should evaluate residual risks against these implementation details without converting proposed controls into completed ones.

## 10 RELIABILITY AND CONCURRENCY
### 10.1 Job leases and crash recovery
Jobs are claimed with FOR UPDATE SKIP LOCKED to avoid multiple workers holding the same claim. A claim assigns a new UUID lease token, increments attempts and sets a five-minute lease. Expired running jobs can be reclaimed. Writes from the older execution must match the current token; otherwise the result is discarded. This provides fencing of stale results, not proof that an external model request occurred only once.

Extraction attempts stop after five failures or crash claims and expose extract_failed. Retry delay grows exponentially. Purge jobs use a separate policy: indefinite retry with delay capped at one hour and an overdue audit signal every five failures. Separating these policies prevents an image-deletion obligation from disappearing after a transient outage.

### 10.2 Lock ordering and financial consistency
Ledger-sensitive approval obtains the owner advisory lock before the watermark row lock. Writers update the watermark in their own transaction. A writer already in flight forces approval to observe changed state after waiting; a writer arriving while approval holds the row must wait until commit. Consistent lock ordering reduces deadlock risk. Database constraints remain necessary because service conventions alone cannot prevent a future code path from creating an invalid transfer pair.

### 10.3 Recovery semantics
After a network loss, the client may not know whether the server committed. Idempotency protects supported mutations, and authoritative refresh resolves visible state. A worker crash after a provider call can lead to a new external call on recovery, which affects costs even when stale writes are fenced. The budget ledger therefore measures provider usage separately from imported transaction counts.

A safe operational response to a failed scan starts with stage and count inspection, not database reset. Profile isolation protects the device trial from automated test cleanup. Backup restore, object/database reconciliation and multi-host failover are future operational work; no high-availability service level is claimed.

## 11 OBSERVABILITY AND COST CONTROL
### 11.1 Scan funnel
The monitor distinguishes visible metadata, undated/old/future exclusions, eligible candidates, previously processed entries, local OCR attempts, filter rejection, unreadable images and upload attempts. Server acceptances are shown separately from ledger results. This funnel explains why zero submissions can be correct even when many photographs are visible.

A useful investigation follows the earliest zero or unexpected reduction: permission mode, capture dates, cache status, file support, local filter, consent refusal, network result, then server extraction and review. Uploaded files copied by adb may require MediaStore rescan during test preparation. That preparation step does not manufacture capture dates or alter production policy.

### 11.2 Processing results and latency
Activity and Review expose downstream outcomes. The current monitor is not a complete distributed trace from every device candidate through extraction to its final transaction. A production extension should correlate an opaque scan-run identifier and upload identifier, record stage durations, and present terminal failure reasons without exposing OCR text. The owner's approximately five-minute observation is not a measured p95 latency and cannot establish a service-level objective.

### 11.3 Provider budget accounting
The usage meter tracks request counts, token counts and estimated costs. Unknown cost fails closed for subsequent paid calls unless it can be recovered from known model pricing and token counts. Corrections identify the run they supersede so totals are not double counted. An estimate derived from list prices is not an invoice. Request caps, output-token limits and a configured budget constrain local execution but are not equivalent to provider-account-wide billing controls.

Financial satang arithmetic is separate from estimated API cost accounting. A floating-point USD estimate in cost monitoring must not enter user balance or pocket calculations. Pricing and provider availability are configuration that require verification at deployment time.

## 12 DEPLOYMENT AND OPERATIONS
### 12.1 Local execution model
Backend configuration selects an explicit provider; no provider default silently substitutes fake output. Fake extraction is restricted to dev/test environments, and health reports test_mode for the UI banner. The gallery profile uses independent persistent resources. Starting another test profile must not reset the user's gallery or dev database.

The web server points to the intended backend origin. On the S22 trial, USB port forwarding exposes the local web origin to the Android host. Building and installing an APK verifies compilation and packaging; it does not verify a real scan, financial correctness or release hosting. The Android package and version should be recorded with each device demonstration.

### 12.2 Configuration and release checklist
| Configuration area | Current concern | Release requirement |
| Origins and transport | Local loopback development route | Explicit HTTPS origin and certificate lifecycle |
| Database roles | API, migration and worker privileges | Reviewed least privilege and controlled migrations |
| Storage | Private local files | Durable storage, encryption, cleanup reconciliation |
| Provider | Explicit model/key/budget configuration | Secret rotation, billing alerts and failure procedures |
| Client permissions | Full/selected/denied photo access | Device acceptance including revocation and restart |
| Operations | Local logs and run artifacts | Monitoring, retention, backup and recovery validation |

### 12.3 Reproducibility and rollback
Evidence records must identify the environment, profile, test selection, mocks, results and known exclusions. Failed or environment-limited runs should remain with an explanation. A missing database must not be reported as a successful suite merely because database tests were skipped. Deployment rollback requires compatible application and schema versions; the POC does not yet provide an evaluated rollback and disaster-recovery procedure.

## 13 VERIFICATION AND EVALUATION
### 13.1 Evidence register
| ID | Evidence directory under evidence/runs | What it establishes |
| E1 | 20261017T012325Z-conversation-gallery-backend | 300 backend passes; two known reference xfails; fake/scripted providers |
| E2 | 20261017T012328Z-conversation-browser | Five mocked conversation UI checks |
| E3 | 20261017T020449Z-pocketpal-scanpolicy-v2-cloud | Eight synthetic-string policy tests; not full worker compilation |
| E4 | 20261017T040000Z-pocketpal-gallery-dated-scan-owner | Owner-reported approximately ten submissions and results after about five minutes |
| E5 | 20261016T120301Z-real-slip-r2-score | Five-image unseen pilot scored and replayed |
| E6 | 20261016T122231Z-reference-contract-regressions | 57 passes and two strict expected failures documenting reference gaps |
| E7 | 20261017T015252Z-native-controls-browser | Four mocked native-control checks before filter v2 |

E1 reports the two expected failures as skipped in its manifest representation; they are known strict xfails, not accepted controls. The evidence register is deliberately scoped: later native filter changes are not covered by an earlier backend or browser run. E4 is an owner observation without a successful-round logcat trace. No new application regression execution is implied by preparation of this document.

### 13.2 Real-image pilot interpretation
The R2 pilot used five previously unselected images with labels frozen before extraction. Document type, amount, date, time, direction, status and counterparty matched all five supplied labels. Exact bank reference agreement was zero of five. Owner review found that some differences reflected selecting different printed reference fields, so this metric cannot be interpreted simply as five OCR failures or five correct model outputs.

The replay counted five transactions once with no measured duplicate, amount error or silent loss in that sample. The result does not establish general duplicate accuracy, bank-reference accuracy or gallery-filter recall. R1 revised-label results must be reported separately because labels were amended after model output was visible. Image data and record-level comparisons remain private; public evidence contains only permitted aggregate information.

### 13.3 Required next evaluation
A representative gallery benchmark should separate genuine slips from receipts and ordinary photos, include supported banks and difficult layouts, and measure candidate precision/recall before provider extraction. An extraction benchmark should report per-field accuracy with explicit denominators, abstention and incorrect automatic import. Ledger replay should test same-image repeats, transformed copies, alternate reference fields, receipts and genuinely separate equal-amount payments.

Device acceptance should cover selected permission, revocation, session expiry, owner switching, restart, scheduling and daily limits. Chat evaluation should distinguish tool correctness, numerical fidelity, uncertainty communication and proposal appropriateness. Novel prompts should be tested against current tool data rather than judged only by fluency. Test pass rate is not a competition score.

## 14 LIMITATIONS AND ROADMAP
### 14.1 Open correctness and product risks
The most consequential known correctness gap is untyped transaction-reference matching. Its two expected failures require a typed reference model and end-to-end replay before closure. Automatic scanning excludes undated photos by policy; whether bank applications populate DATE_TAKEN remains a product compatibility question. The local filter has no image-level FP/FN benchmark. Receipt-like false positives can disclose unrelated images to the extraction provider if they satisfy the filter and consent path.

Actual per-slip correctness, duplicates and Chat use of the latest gallery imports remain unverified for the owner's observed scan. Approximately five minutes of reported latency is sufficient for the owner's POC decision but not a validated performance objective. UI feature presence and compilation do not close all mobile acceptance criteria.

### 14.2 Production engineering priorities
Before production release, complete hosting and transport configuration, centralize date-policy enforcement, validate resource limits and authentication abuse controls, and implement tested backup/recovery and object reconciliation. Define provider data-retention and deletion terms, operational log retention, and account erasure scope. Validate background behavior across supported Android versions and permission modes. Complete a security assessment with deployment-specific evidence and independent testing appropriate to risk.

Prioritization must preserve the original product requirements. A requirement that is deferred remains open; it must not be removed to produce an apparently complete checkpoint. The current documented architecture is a foundation for these tasks, not evidence that they have already run.

## 15 CONCLUSION
Pocket Pal places financial calculations, ownership checks and commit authority in deterministic services while using models for extraction and constrained conversation. Its transaction, proposal and job mechanisms address several important concurrency and replay failures, and its gallery monitor distinguishes candidate discovery from completed import. Existing evidence supports a local proof of concept and specific tested controls. Untyped references, undated-image compatibility, full device acceptance, gallery accuracy and production operations remain explicit work items. These boundaries define both the supported submission claims and the next engineering decisions.

## REFERENCES
[S1] We go shenzhen case (1).docx. Original product requirements in docs/. Authoritative product baseline; unchanged.

[S2] PBCSF Appendix 2 Problem Description and Competition Rules for International Track. Original competition PDF in docs/. Submission categories and evaluation weights; unchanged.

[S3] Pocket Pal design records 00–16, HANDOFF.md, and the implementation modules listed in Appendix A. Internal implementation and decision record, baseline 17 October 2026.

[R1] PostgreSQL Global Development Group. Row Security Policies. PostgreSQL documentation. https://www.postgresql.org/docs/current/ddl-rowsecurity.html. Consulted 17 October 2026.

[R2] Android Developers. Grant partial access to photos and videos. Android 14 behavior documentation. https://developer.android.com/about/versions/14/changes/partial-photo-video-access. Consulted 17 October 2026.

## APPENDIX A SOURCE MAP
| Topic | Source location relative to repository root |
| Financial rules | backend/src/finassist/domain/ |
| HTTP contracts | backend/src/finassist/api/routes.py |
| Authentication and ledger operations | backend/src/finassist/services/core.py |
| Imports and review | backend/src/finassist/services/imports.py |
| Budgets and approval | backend/src/finassist/services/budget.py and cards.py |
| Providers and cost accounting | backend/src/finassist/providers.py |
| Database constraints and isolation | backend/db/migrations/ |
| Web interface and BFF | web/src/app/ and web/src/components/ |
| Current Android host and scanner | android/pocketpal/ |
| Legacy Compose client | android/app/ and android/core/ |
| Gallery operating procedure | android/POCKETPAL_GALLERY.md |
| Acceptance and evidence mapping | docs/design/06-acceptance-and-traceability.md |
| Reference limitations | docs/design/14-reference-contract.md |
| Conversation and gallery design | docs/design/16-conversation-gallery.md |

## APPENDIX B STATE AND ERROR GLOSSARY
| Term | Interpretation |
| received | API accepted an image; extraction is not complete |
| extracting | A worker is processing the upload |
| needs_review | No automatic financial inclusion until required resolution |
| imported | Routed to a financial record according to server rules |
| merged_duplicate | Linked to existing financial evidence instead of another expense |
| extract_failed | Automatic extraction attempts ended; explicit retry may be available |
| cancelled_consent | Processing stopped under current consent state |
| deleted | Access denied; physical purge may still be pending |
| PROPOSAL_STALE | Current financial state differs from the proposal basis |
| OWNER_MISMATCH | Client owner assertion conflicts with authenticated session |
| CAPTURE_DATE_REQUIRED | Manual confirmation required for missing capture metadata |
| DECISION_NOT_ALLOWED | Submitted review action is not permitted for the item |

## APPENDIX C ACCEPTANCE RECORD TEMPLATE
A reproducible demonstration should record application version, package, device and Android version, backend profile, provider mode, consent settings and test-data provenance. For each step, record the action, expected state, observed state and evidence identifier. Use synthetic data for publicly shareable videos; private real-image testing requires owner authorization and controlled storage.

The minimum normal-flow record is sign in, inspect consent, scan or manually upload, observe admission, wait for extraction, resolve any review item, inspect the ledger and pocket effect, and ask Chat a question whose answer can be compared with current tool-derived values. Record duplicate behavior separately. A failed or pending step must remain visible in the record rather than being omitted from the demonstration's claimed coverage.
