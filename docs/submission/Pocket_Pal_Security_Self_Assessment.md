POCKET PAL

SECURITY SELF ASSESSMENT REPORT

Pocket Pal Project Team

Permission tiers, threat analysis and residual risk

Assessment edition 18 October 2026 | Implementation evidence through 18 October 2026

Abstract

Pocket Pal processes sensitive financial images and provides model-assisted personal finance support. This report assesses the security boundaries of its web interface, Android gallery host, API, worker, database and external model integration. The assessment emphasizes implemented permission tiers, owner isolation, approval integrity, consent transitions, asynchronous execution and data lifecycle controls. Findings are based on source inspection and recorded execution evidence, with explicit distinctions between deterministic application tests, mocked client tests and owner-reported observations. The architecture limits the conversational model to reading, simulation and proposal creation; user approval and server-side revalidation govern committed planning changes. Material residual risks remain in transaction-reference interpretation, gallery filtering, native lifecycle verification, operational hardening and external data handling. The report supports a controlled proof of concept and a prioritized remediation plan. It does not establish production readiness, independent penetration-test coverage or regulatory compliance.

Keywords: permission tiers; agent security; financial integrity; tenant isolation; consent; mobile privacy; residual risk; security assurance.

1 ASSESSMENT CONCLUSION AND SCOPE

1.1 Executive security conclusion

Pocket Pal has implemented useful defense-in-depth controls for a personal financial assistant: session-derived ownership, application and database isolation, bounded model tools, exact-proposal approval checks, consent-gated extraction and durable deletion retries. The strongest evidence concerns deterministic application boundaries and database behavior. Model correctness, mobile lifecycle behavior and production infrastructure have narrower or incomplete evidence.

The recommended disposition is controlled POC use under explicit owner consent and supervised local operation. Unrestricted public deployment is not recommended on this evidence. The team must close or explicitly accept identified risks within a documented deployment scope. Owner acceptance of the observed gallery demonstration is a product decision to proceed with documentation; it is not a blanket security-risk acceptance or closure of CP3b.

1.2 Assessed system and exclusions

The active implementation consists of the Pocket Pal Next.js web application and backend-for-frontend (BFF), the android/pocketpal WebView host, FastAPI services, asynchronous extraction and purge workers, PostgreSQL, local image storage and configured external model services. The API is the financial authority; neither browser presentation nor model output can bypass service checks. The earlier Compose client in android/app is a separate implementation lineage. Its Keystore and token-epoch tests must not be attributed automatically to the current WebView host.

The architecture separates financial services from operating-system integrations. Galaxy S22 Ultra, SM-S908E with Android 14, is the initial physical validation device, not an exclusive product target. Browser-based functionality provides a cross-platform foundation. Automatic gallery scanning currently relies on Android-specific permissions, MediaStore and WorkManager; equivalent functionality on another OS requires implementation and testing. Compatibility and security assurance are not inferred for untested platforms.

The scope excludes real payment initiation, bank settlement, custody, investment execution and bank-certified transaction verification. No independent penetration test, production cloud configuration assessment, forensic examination, legal opinion or certification was performed for this report. A correctly transcribed image is not evidence that a bank settled the depicted payment.

1.3 Assessment method and status vocabulary

Source inspection used the local implementation and recorded evidence. The 18 October follow-up added a capacity-availability guard, clarified proposal lifecycle wording and reran isolated regressions [E7]. Historical and live-model runs retain their separate scope [E1–E9]. No paid model requests, personal-image inspection or demo database resets were performed during this follow-up review. Source and document hashes identify the reviewed snapshot without claiming a Git revision.

| Status | Meaning |
| --- | --- |
| Implemented, recorded test evidence | A mechanism exists and named evidence exercises defined scenarios. Coverage is bounded by those scenarios. |
| Implemented, source reviewed | A mechanism is present in inspected source; this report does not establish deployed behavior or exhaustive tests. |
| Owner-reported | A human reported an observation; it is not an instrumented measurement or complete acceptance run. |
| Open finding | A reproduced defect, an incomplete control or an assurance gap remains unresolved. |
| Proposed production control | Recommended design; not implemented or verified by this assessment. |



Passing test counts are not a security score. Expected failures remain open findings even when the test runner displays them as skipped. False-positive and false-negative gallery performance cannot be inferred from text-rule unit tests. Evidence from a fake provider establishes application handling, not real-provider resistance to prompt injection.

2 ASSETS TRUST BOUNDARIES AND THREAT MODEL

2.1 Assets and security objectives

Financial records, images and conversation context are sensitive even when they do not enable money movement. They can reveal counterparties, spending habits, account fragments and personal circumstances. Security must preserve confidentiality, prevent incorrect or unauthorized ledger effects, maintain usable recovery paths and provide accountability for consequential actions.

| Asset | Objective and principal consequence of failure |
| --- | --- |
| Passwords and bearer sessions | Prevent account takeover; token possession enables authenticated operations within that session. |
| Slip images and extracted text | Prevent unintended disclosure, including information about third parties shown on an owner's slip. |
| Transactions, bills and balances | Preserve provenance and correct inclusion; a duplicate or missing record can mislead financial decisions. |
| Plans, pockets, goals and proposals | Preserve explicit intent, exact approval and current-state validation. |
| Model credentials and DB credentials | Prevent service compromise, unauthorized data access and uncontrolled provider expenditure. |
| Audit, test evidence and backups | Preserve accountability while preventing secondary disclosure and uncontrolled retention. |



2.2 Trust boundaries

The first boundary is between the device and the web/API services. OS photo permission governs accessible media, while application consent governs authorized processing. Neither permission establishes the truth of image content. The second boundary is the BFF: it mediates the HttpOnly session cookie and translates it into a backend bearer credential. The third is the service/database boundary, where owner context, SQL permissions and row-level security apply. A separate boundary exists when images or financial tool results are transmitted to the external model provider.

The worker is a privileged service relative to end users: it discovers pending jobs across owners and then processes data in the selected owner context. A model is not a trusted principal and receives no database credential. The operator, runtime host, migration authority and configured provider remain trusted dependencies; compromise of these components is not contained merely by prompt rules or row policies.

User or Android host → same-origin BFF → authenticated API → owner-scoped services and PostgreSQL

API or extraction worker → external model service → untrusted output → deterministic validation

2.3 Threat actors and assumptions

Assessed adversaries include an unauthenticated remote caller, a malicious authenticated tenant, a person with a stolen session, a hostile image or chat author, and a compromised browser dependency. Accidental failures include stale proposals, duplicate requests, worker crashes, incomplete uploads, invalid OCR, permission revocation and environmental misconfiguration. Operator misuse and compromised dependencies are relevant production threats but have not been comprehensively tested.

The controlled POC assumes a trusted development host, controlled USB forwarding and an uncompromised device OS. These assumptions must not migrate silently into a public deployment. An attacker controlling the runtime process can potentially set database owner context, read provider secrets or alter application checks. Row-level security is a second isolation layer against application mistakes, not a sandbox against arbitrary execution within a trusted service.

2.4 Abuse cases

| Abuse case | Boundary and current assessment |
| --- | --- |
| Substitute another owner's object ID | Session scoping, owner filters and forced RLS; negative API and runtime-role tests exist [E1]. |
| Put approval instructions in a slip or chat | Structured extraction and a restricted tool registry limit actions; semantic correctness remains uncertain. |
| Replay an approved budget change | Idempotency and proposal state prevent repeated business application in covered tests [E1]. |
| Approve after a concurrent expense | Owner locks and watermark/version revalidation reject stale state in covered tests [E1]. |
| Upload unrelated private photographs | Local filter and consent reduce exposure; mixed-gallery false-positive rate is unmeasured. |
| Reuse an ambiguous printed reference | Known reference-contract gaps can duplicate or merge records [E2]. |
| Exhaust model budget or worker capacity | Local work limits and bounded tool loops exist; global abuse and distributed cost control are not established. |



3 PERMISSION TIER IMPLEMENTATION

3.1 Authority model

T0–T5 are application operation categories, not a role hierarchy and not an external security standard. A higher tier does not imply inheritance of lower-tier privileges. The labels do not by themselves authorize requests. Effective authority is enforced through the caller identity, route exposure, service validation, current consent and transaction state. There is no independent universal policy engine that interprets a tier tag and grants access.

A single conversational agent can select registered T0–T2 tools. The server maps the requested tool name to a validated input schema and implementation. T3–T5 are absent from that registry. An authenticated user can invoke permitted API operations directly; the model's conversational statement that an operation is approved has no authority. Worker automation uses specific service paths under consent, not the conversational tool interface.

| Tier | Actor and allowed effect | Enforcement and limitation |
| --- | --- | --- |
| T0 Read | Authenticated user or model-mediated service reads scoped financial information. | Owner from session; service queries and RLS. Returned data can still disclose sensitive facts to the configured provider. |
| T1 Simulate | User or model evaluates affordability and goal scenarios. | Deterministic services; no purchase or plan is committed. Chat/audit metadata may still be persisted under applicable rules. |
| T2 Propose | User or model creates a pending plan, reallocation, tradeoff or goal proposal. | Validated payload, current applicability and server card. Proposal persistence is a write, but not application of the proposed financial change. |
| T3 Commit | User approves an exact pending proposal. | Authenticated route, idempotency, locks, status/expiry, hashes, versions, watermark and funding checks. No real payment execution. |
| T4 Consented automation | Worker extracts and imports eligible financial evidence. | Current processing grant, import grant where required, owner/lease checks and deterministic validation. Ambiguity is routed to review. |
| T5 Account and data control | User manages supported consent, history and image-deletion actions. | Authenticated lifecycle endpoints; absent from model registry. This does not imply a complete account-erasure or regulatory rights platform. |



3.2 T0 and T1 tool implementation

services/agent.py defines six read tools: get_overview, get_spending, list_bills, list_proposals, list_review_items and get_insights. Two simulation tools, simulate_purchase and check_goal, delegate to financial services. The owner parameter is supplied by the authenticated application context, not exposed as a model-selected tool argument. Pydantic schemas reject extra arguments; unknown tools produce an error.

list_proposals exposes only the five latest owner-scoped lifecycle summaries and identifiers, without approval hashes or actions. Derived expiry is included, but pending status does not certify current applicability; stale-state rejection remains an approval-time control. A model-visible proposal identifier is not an authorization credential and does not expand the model to T3.

Amounts are parsed into integer satang before financial calculations. Date ranges and required inputs are validated. Simulation can support a user decision but cannot prove that all financial obligations have been captured. Tool results and cards are computed by the backend; the model-generated prose is not subject to a complete numerical-verification layer. This difference is a residual integrity risk, not a reason to treat model instructions as an enforced arithmetic guarantee.

3.3 T2 proposal implementation

The four proposal tools are propose_tradeoff, propose_reallocation, propose_budget_plan and propose_goal. They create pending proposal records and return a server-derived summary, changes, warnings and uncertainty. services/cards.py constructs the approval card; the model does not supply authoritative card numbers. A T2 operation can create a misleading or unwanted proposal, so the user must inspect it. Restricting commit authority does not eliminate persuasion, poor recommendations or proposal spam.

The registry contains no approve, apply, delete, change-consent or real-transfer tool. test_sec_tools_registry_has_no_write_authority and test_sec_agent_proposes_user_approves exercise the restricted registry and proposal-to-user boundary [E1]. The test's name uses 'write authority'; the precise distinction is absence of financial commit authority, because T2 does persist proposals.

3.4 T3 approval transaction

The approval route derives owner identity and executes within the idempotency transaction. The service first obtains an owner ledger advisory lock and a locked owner-watermark row, then locks the proposal. It validates pending status, expiry, payload hash and card hash. Applicability and funding are checked again. Plan/goal versions and the recorded data watermark are compared with current state before the effect is applied and audited.

A hash mismatch is rejected. Expiry yields an expired response. A stale or no-longer-applicable proposal is rejected; an applicable stale proposal can produce a replacement requiring a fresh review. Applied proposals cannot be applied again. Hashes bind the exact stored payload and card; they are not digital signatures, proof of identity or protection against a compromised database administrator.

User approval → idempotency transaction → owner locks → proposal lock → state and hash checks

Invalid or stale → reject or replacement; valid → apply once → update state and audit → commit

The concurrency protection depends on financial writers maintaining the watermark within their own transactions. New write paths must preserve this invariant. Two-connection tests are more informative for this boundary than a sequential UI test. Existing tests cover concurrent approval, stale data and relevant writer/approval interleavings; they do not establish correctness of every future mutation path.

3.5 T4 automation and consent

Photo processing consent and auto-import consent are distinct. Processing permission allows the extraction path; it does not automatically authorize ledger inclusion. The worker validates extracted structure and critical fields and routes uncertain items to review. Bills also require applicable auto-import consent. Review resolution is an authenticated user operation whose allowed decisions and candidate IDs are validated by the server.

Job leases and tokens guard persistence by stale workers. Consent is checked again when extraction results are persisted. Revocation before processing can cancel work; revocation during an external request prevents applicable persistence but cannot recall bytes already sent to the provider. Automatic imports are not equivalent to model-authorized money movement: they record interpreted evidence under policy and remain exposed to OCR and reference-selection errors.

3.6 T5 lifecycle boundaries and prohibition rules

Users can revoke supported consent, clear retained chat history and request upload deletion through authenticated routes. Deletion immediately denies image access and schedules durable physical removal. Neither a model tool nor text embedded in an image can call these controls. Deletion of an uploaded copy does not delete the original photo from the user's phone or guarantee removal from provider infrastructure.

Unsupported authority includes initiating bank transfers, settling bills through a bank, granting new consent via model output and overriding ownership. Privileged operator actions, schema migrations and credential rotation are administrative functions outside these user tiers. Their production approval and audit procedures remain to be defined.

4 IDENTITY AUTHENTICATION AND TENANT ISOLATION

4.1 Password and session controls

infra.py uses Argon2id through PasswordHasher with library-default parameters. signup enforces a minimum password length of ten characters. The report does not claim that defaults have been calibrated against a production hardware threat model. Session tokens use secrets.token_urlsafe(32), providing 256 bits of random input; only their SHA-256 digests are stored in the session table. Sessions have a seven-day expiry and logout marks the token revoked.

owner_from_token verifies expiry and revocation before binding the owner. A password hash is not reversible encryption; hashing a session token limits direct use of a stolen database digest but does not protect a plaintext token stolen from the client or runtime. MFA, verified recovery, breached-password screening, adaptive login throttling and step-up authentication are not established by the current evidence. Seven-day bearer sessions require review before public exposure.

4.2 Object authorization and RLS

Service queries constrain owner identity and database owner tables use ENABLE and FORCE ROW LEVEL SECURITY policies. app.owner_id is bound from verified context. The runtime uses separate connections rather than sharing an owner-bound connection across requests. Introducing a pool requires explicit owner reset and leakage tests. Without a bound owner, tested runtime queries return no tenant rows.

The worker role has a job-discovery exception so it can claim jobs across owners. This is a service privilege that must be narrowly managed, not an entitlement for users. Superuser or BYPASSRLS credentials invalidate the expected isolation boundary. The deployed role configuration must be verified independently; schema policies alone do not prove the production process uses the correct role.

Object-level negative tests cover another user's records and owner injection. Composite constraints supplement application checks where implemented. expected_owner_id on uploads is a consistency assertion against the session, never a source of authenticated ownership. UUID unpredictability and hidden UI controls are not substitutes for authorization.

4.3 Account switching and client generations

The active web interface uses owner/request-generation guards to hide old state and reject late responses from another account. Native scan status is associated with session identity. These mechanisms must be evaluated separately from legacy Compose token compare-and-clear controls. The full matrix of logout, account change, token expiry, process death and background work on the current APK remains an acceptance gap.

5 WEB API AND NATIVE CLIENT SECURITY

5.1 Cookie mediation and CSRF boundary

The web session cookie is HttpOnly and SameSite Strict, with Secure set for HTTPS. HttpOnly limits JavaScript access to the cookie; it does not prevent injected same-origin code from issuing authenticated requests. The BFF checks Origin on mutating requests against the request host and protocol and rejects absent or mismatched origins. This is an origin-based CSRF control, not evidence that every browser attack class is closed.

Deployment must define trusted Host and forwarded-header handling, TLS termination and allowed origins. An origin comparison against incorrectly trusted proxy metadata can be weaker than intended. Reverse-proxy behavior and the release cookie configuration require a deployed test, not only local-loopback testing.

5.2 BFF forwarding and resource bounds

backend-server.ts constrains the upstream base to HTTPS or loopback HTTP and rejects credentials, query strings, fragments and non-root paths in that base. Forwarding rejects redirects. The backend proxy restricts path segment characters, excludes the auth path, forwards only selected headers and attaches the bearer token from the cookie. It bounds streamed request bodies to 9 MiB, including requests without Content-Length, while the backend image cap is 8 MiB.

These controls reduce open-proxy and request-size risks but are not a complete SSRF or denial-of-service assessment. The proxy can hold a request for up to 120 seconds. Application timeouts and single-request caps do not establish safe concurrency under load. Production ingress limits, authenticated rate controls, worker admission and provider quotas need coordinated design.

5.3 Browser rendering and dependency exposure

Chat uses restricted Markdown handling without raw HTML or model-supplied images. Model-generated text remains untrusted. Restricting rendering reduces injection paths but does not establish a comprehensive XSS assessment, Content Security Policy rollout or absence of dependency vulnerabilities. Links, copied content, filenames and error messages require output-context validation. CSP, dependency scanning and browser security-header verification are proposed production work unless separately evidenced.

5.4 Android WebView and native bridge

MainActivity permits the configured HTTPS origin, with a debug-only loopback exception. WebView file and content access are disabled, mixed content is disallowed, and third-party cookies are disabled. The bridge uses WebMessageListener with the configured origin and checks the main frame. Its exposed functions concern status, permission and scanning controls; it must not become a generic command executor or unrestricted file reader.

The application manifest disables backup and cleartext traffic for the main configuration; a separate debug network-security configuration permits the local demonstration path. Release artifacts must be inspected to confirm the debug exception is absent and that signing, origin configuration and WebView behavior match the intended environment. The current host uses native CookieManager for authenticated operations; this report does not claim application-level Keystore encryption of that cookie or certificate pinning.

5.5 Gallery permission and privacy boundary

OS permissions can be full, selected or denied. The scanner also checks application consent and capture-date scope. DATE_TAKEN is used for the last-30-day window; DATE_ADDED is not silently substituted. Undated images are skipped automatically, while manual undated selection requires explicit confirmation. This conservative rule reduces accidental historical uploads but can exclude legitimate downloaded bank slips.

The local ML Kit filter is a heuristic candidate selector, not a security classifier with measured privacy guarantees. A non-slip can match its layout rules, exposing unrelated content if uploaded under broad processing consent. The implemented caps are 100 local checks and ten upload attempts per scan, and twenty attempts per owner/day. They limit work but do not prove image relevance or enforce an organization-wide monetary budget.

6 FINANCIAL AND AI INTEGRITY

6.1 Deterministic financial authority

Money paths use integer satang and validated financial rules. Transfer-group constraints protect paired effects; internal transfer totals should remain conserved. Proposal funding checks prevent allocation of unavailable funds within the modeled state. These controls address internal consistency. They cannot detect unrecorded external spending or prove the authenticity of an image.

Chat grounding now supplies a trusted local date/timezone and half-open reporting periods on every request. Spending totals, category ranks and display amounts are computed by the server. Monthly estimated savings are converted to capacity per income event using an explicit annualized integer ratio; irregular conversion and unavailable current plans return an unavailable goal impact. These changes reduce particular interpretation and unit errors, not the risk of incomplete source records or incorrect generated prose.

Idempotency prevents repeated execution of a covered request; duplicate detection decides whether evidence describes an existing business event. These are different problems. A request with a fresh key can still describe the same purchase, and a dedup rule can incorrectly merge two separate purchases. Financial correctness requires both mechanisms plus evidence-quality validation.

6.2 Reference ambiguity and unsafe certainty

REF-GAP-1 concerns one payment represented by different printed reference fields. REF-GAP-2 concerns equal untyped values that do not identify the same payment. The proposed multi-reference contract is not active. Its two strict expected failures remain open and must not be reported as passing security controls. Similar-character heuristics nominate review cases; they do not establish bank-wide identifier equivalence.

A safe remediation must preserve printed label/value provenance, identify namespace semantics only where justified and test conflicting references, repeated same-value purchases, retrieval windows and cross-owner isolation through the actual pipeline. Arbitrary O/0 normalization or accepting every printed number as a transaction identity would conceal the issue.

6.3 Prompt injection and constrained orchestration

The agent exposes only registered read, simulate and propose operations, with six model turns and eight dispatched tool requests per chat. Unknown names and invalid arguments return errors. Extracted image text and tool results are treated as data, not authority. A hostile prompt can still influence explanations, tool selection or the content of a pending proposal within the allowed boundary.

Prompt instructions to ignore injected content or use tools for every number are behavioral mitigations. The reliable boundary is the absence of privileged model tools combined with server checks on every consequential operation. There is no demonstrated universal prompt-injection immunity, formal proof of model alignment or comprehensive numerical verifier. Scripted model tests establish what the application does with specified tool calls, not how often a real model will choose those calls under attack.

Provider stop_reason is retained; truncated responses are visibly marked and empty answers receive a fallback. The default model-call output limit is 1,200 tokens, with the existing six-turn/eight-tool-request limits unchanged. A visible partial response can still omit a material qualification. English-default/Thai-script language selection is a usability rule, not a security boundary, and fallback notices currently remain English.

6.4 Memory, retention and misleading context

Retained conversation requires chat_history_retention consent. Stored history is bounded to 200 messages; model context uses at most twelve recent messages and 12,000 characters, with per-message clipping. A per-owner lock serializes turns and deletion. Persistence checks the applicable grant again so revocation during generation cannot silently restore history.

Conversation history is context rather than current financial truth. Structured tools retrieve current values, but a model can still repeat old prose or omit a relevant tool. No vector database or RAG index exists in this baseline. Any future retrieval layer must enforce tenant isolation and deletion at ingestion, indexing, retrieval and caching, and must separate stale retrieved material from authoritative financial state.

7 DATA PROTECTION CRYPTOGRAPHY AND LIFECYCLE

7.1 Cryptographic claims and boundaries

| Mechanism | Current claim and limitation |
| --- | --- |
| Argon2id password hashing | Implemented with library defaults; production parameter calibration and rehash lifecycle not evidenced. |
| Random opaque session and SHA-256 digest | Implemented; digest storage does not protect a stolen live bearer token. |
| Proposal/card SHA-256 binding | Implemented integrity comparison; not a digital signature or non-repudiation service. |
| TLS | Required by release-origin policies; local debug uses loopback HTTP. No hosted TLS deployment was assessed. |
| At-rest encryption and KMS/HSM | Not established for database volumes, local images or backups. Proposed for production. |
| Tamper-evident audit | Not established. Database audit records are not cryptographically sealed or independently immutable. |



Do not describe the system as end-to-end encrypted: the backend and configured model service need plaintext content to perform processing. A future encryption-at-rest design should use managed keys, separated key and data access, rotation and recovery procedures. Merely naming AES-256 does not prove encryption is enabled, keys are separated or backups can be recovered securely.

7.2 External processing and minimization

Images sent for extraction can include account fragments and counterparty information. Chat requests can include conversation text and financial tool results. These cross the provider boundary. The account's applicable service terms, retention settings, region, subcontractors and deletion capabilities were not verified by this report. Do not infer zero retention, no training use or a fixed data residency from product branding.

Data minimization should be evaluated against extraction quality: on-device filtering, omission of unnecessary context, bounded history and selective upload help, but full image redaction before external extraction is not established. A proposed redaction pipeline must preserve financial fields, avoid irreversible false masking, and measure both residual sensitive content and OCR degradation before claiming benefit.

7.2.1 Provider admission and prohibition of training use

Proposed mandatory enterprise admission policy. An approved service must have documented commitments prohibiting training and model improvement using customer inputs, images, outputs and tool results. Optional data-sharing and feedback paths must be reviewed and disabled where they would conflict with that commitment. Approval is specific to the service, organization/account, endpoint, model and configuration; a vendor name or API key alone is insufficient. This report does not attest that the POC account has completed that review.

The proposed approval record identifies the accountable approver, permitted data classes and purposes, contract or terms revision, processing region, retention duration and exceptions, deletion process, subprocessors, configuration evidence, review date and expiry. Retention for safety or legal purposes must be assessed independently of training use. Where organizational policy forbids external processing, use a separately assessed internal deployment and restrict its telemetry and outbound traffic; internal hosting alone does not prove secure operation.

The proposed admission gate evaluates the selected route before each external dispatch against a versioned approved record. Missing, expired or incompatible approval blocks dispatch; it does not silently fall back to another destination. The application can enforce destination selection and permitted payload construction, but it cannot inspect or technically guarantee a third-party provider’s internal training pipeline. Contractual assurance, settings review and periodic reassessment are therefore necessary alongside technical controls. No such automated approval registry or gate is implemented in this baseline.

7.3 Image deletion and worker resilience

Upload deletion immediately removes API visibility while retaining sufficient internal state to retry physical removal. Purge failures remain pending, retry with bounded backoff and emit overdue audit events. Unlike extraction jobs, purge jobs are not abandoned solely because five attempts failed. Job lease expiry permits recovery after a crash, and token checks prevent a stale worker from writing a result after ownership of the job changes.

Logical access denial and physical deletion are separate outcomes. Backups, provider-held copies, mobile originals and operator exports require their own lifecycle. The system does not currently establish a maximum end-to-end deletion completion time across these locations. A purge retry mechanism without monitoring can leave inaccessible but retained data indefinitely.

7.4 Retention, logs and evidence

The project keeps real slips and private labels out of public fixtures and repository evidence. Published execution artifacts should contain synthetic values, aggregate results and sanitized metadata. Error logging avoids exception messages where they may contain private data; native scan logs use stage codes and counters rather than OCR text or file paths. This reduces exposure, but business identifiers and metadata still require access control and retention policy.

No complete timed-retention enforcement is established for all images, audit events, idempotency responses, backups and provider data. Production policy must define purpose, owner, retention trigger, deletion method, legal exceptions and verification for each data class. Privacy compliance requires a separate legal and operational assessment; this report makes no PDPA, GDPR or PCI DSS compliance assertion.

8 AVAILABILITY OPERATIONS AND SUPPLY CHAIN

8.1 Failure handling and resource control

Extraction retries are bounded, crash-loop jobs reach a failed state, and purge retries persist. Lease recovery is designed to restore progress without permitting stale writes. These are application resilience mechanisms, not a high-availability service guarantee. Provider latency, connection occupancy, storage errors and background scheduling remain operational dependencies. A single local host and database are failure domains.

Local model usage accounting and scan attempts are not equivalent to distributed spending enforcement. Public exposure requires quotas at the service boundary, reservation of anticipated cost, reconciliation with actual usage, abuse detection and controlled retry budgets. Timeout, cancellation and partial-failure behavior should be measured under concurrent requests before defining a service-level objective.

8.2 Environment and operator isolation

The dev, e2e, test, realeval and gallery profiles separate databases and storage. This separation followed an incident where automated testing reset the device-trial database. The event demonstrates why destructive test operations need explicit environment binding. Production should use distinct identities, secrets, network access and independently protected backups; a naming convention alone is insufficient.

Runtime secrets must remain server-side and excluded from client bundles, repositories and evidence. Secret rotation, emergency revocation and access review are proposed operational requirements. Administrator access should use MFA, least privilege and auditable elevation. The current submission does not establish a deployed privileged-access management system or dual-control administration.

8.3 Software supply chain

A production release should inventory dependencies, generate an SBOM, pin resolved versions, run dependency and secret scanning, review licenses and sign release artifacts. CI should separate build and deployment credentials and retain provenance. These controls are recommended, not reported as completed audits. Passing application tests cannot rule out a vulnerable image decoder, WebView, JavaScript package or compromised build dependency.

Threat-specific hardening such as certificate pinning or device integrity checks requires lifecycle planning. Pinning can create outages during rotation; integrity signals are not proof that a device is safe. They should supplement server authorization and risk decisions rather than become the sole access-control basis. No pinning or device-attestation deployment is claimed here.

9 KNOWN RISK REGISTER

9.1 Rating and ownership method

Ratings are qualitative engineering judgments for the contemplated public deployment, not CVSS scores or measured probabilities. High indicates a plausible material confidentiality/integrity impact or a release-critical assurance gap. Medium indicates bounded impact, operational uncertainty or a significant usability/availability concern. Exposure under a supervised local POC differs from public deployment. Proposed accountable roles below must be assigned to named people by the team; they are not accepted ownership commitments.

Each risk remains open unless a separately recorded acceptance or closure decision is cited. A remediation is closed only after implementation, negative testing and evidence review. An accepted risk requires scope, rationale, compensating controls, accountable approver and a review date. No acceptance is created by this report.

9.2 High-priority risks

| ID and rating | Scenario and current mitigation | Required closure evidence and proposed owner |
| --- | --- | --- |
| R01 High — reference ambiguity | Untyped identifiers duplicate a payment or merge separate payments. Review heuristics exist; REF-GAP-1/2 remain open. | Typed evidence policy and pipeline tests closing both strict xfails, including collisions and repeated purchases. Backend owner. |
| R02 High — irrelevant gallery upload | Local filter selects an unrelated private image. Consent, date bounds and caps limit scope, not relevance. | Frozen mixed-image benchmark with FP/FN and privacy-focused review; documented user controls. Mobile/ML owner. |
| R03 High — native lifecycle gaps | Late callbacks or background work cross session/consent transitions. Guards exist, full current-client evidence incomplete. | Physical-device race matrix for logout, account change, revocation, restart and expiry. Mobile/security owner. |
| R04 High — public deployment configuration | Debug transport or incorrect proxy/role configuration exposes sessions or data. Local-origin restrictions exist. | Deployed TLS/cookie/Host tests, release APK inspection and least-privilege role verification. Platform owner. |
| R05 High — account takeover controls | Password guessing, stolen sessions or recovery abuse. Argon2id and expiry exist; broader abuse controls not established. | Rate-limit/lockout abuse tests, recovery design and step-up/MFA decision with usability review. Identity owner. |
| R06 High — storage and backup protection | Host or backup compromise reveals images and financial records. Owner-scoped API does not encrypt disks. | Verified volume/object/backup encryption, access policies, key separation and restore drill. Platform owner. |
| R07 High — provider data handling | External retention or transfer exceeds user expectations. Explicit processing consent exists. | Approved service/account terms, no-training commitment, retention exceptions and route-policy evidence (7.2.1, 11.5). Privacy/platform owner. Risk remains open. |
| R08 High — unbounded abuse or spend | Multiple clients exhaust provider budget, connections or workers. Per-run limits do not enforce global quotas. | Ingress admission/load tests, distributed quota and cost reservations, retry reconciliation (11.6–11.7). Backend/platform owner. Risk remains open. |
| R09 High — dependency and release assurance | Vulnerable dependency or altered build compromises sensitive data. No independent audit claimed. | SBOM, SCA/secret scans, reviewed findings, signed build and provenance. Release owner. |
| R10 High — incomplete data lifecycle | Images or identifiers remain after logical deletion or beyond intended retention. Durable purge exists. | Deletion reconciliation, overdue alerts, per-class schedules and backup/provider procedures. Privacy/platform owner. |



9.3 Additional integrity and operational risks

| ID and rating | Scenario and current mitigation | Required closure evidence and proposed owner |
| --- | --- | --- |
| R11 Medium — unsupported explanation | Model misstates values, coverage or applicability. Trusted date context, server rankings, output notices and a small synthetic live pilot reduce selected risks; complete calendar windows do not establish complete spending data. | Broader frozen novel-prompt evaluation, human narrative assessment and claim-level checks if adopted. Risk remains open. AI owner. |
| R12 Medium — undated slip coverage | Legitimate downloaded slips lack capture metadata and are excluded. Manual confirmation path exists. | Representative device/bank-app metadata study and explicit date-policy decision. Product/mobile owner. |
| R13 Medium — stale or incomplete user view | Scan results arrive slowly and the user mistakes acceptance for import. Stage monitor exists. | Correlated stage timings, terminal outcomes and measured latency distribution. Client/platform owner. |
| R14 Medium — audit integrity | Privileged actors alter or delete audit rows. Events exist but independent immutability is absent. | Restricted audit access, external retention and tamper-detection validation. Security/platform owner. |
| R15 Medium — recovery uncertainty | Storage loss or database failure prevents recovery. Job retry is not backup recovery. | Agreed recovery objectives, restore/reconciliation drills and incident exercise. Platform owner. |
| R16 Medium — incomplete client protection | Same-origin XSS or dependency compromise abuses an HttpOnly session. Restricted Markdown reduces one entry point. | Browser attack testing, CSP/header review and dependency remediation. Web/security owner. |
| R17 Medium — insufficient release evidence | Legacy tests are incorrectly generalized to the active APK or all OSs. Lineage is documented. | Version-bound acceptance matrix and reproducible sanitized evidence package. QA owner. |
| R18 Medium — malicious or forged financial image | Plausible forged slip is imported and affects advice. Schema/field checks do not verify bank settlement. | Clear authenticity disclosure and evaluated verification integration if required. Product/backend owner. |



10 CONTROL EVIDENCE AND ASSURANCE MATRIX

10.1 Evidence inventory

| ID | Recorded artifact | What it supports and does not support |
| --- | --- | --- |
| E1 | 20261017T012325Z-conversation-gallery-backend | 300 passed; two reference expected failures reported as skipped. Real DB/application with fake or scripted providers. Not a production penetration test. |
| E2 | 20261016T122231Z-reference-contract-regressions | 57 passed, two strict xfails; runxfail reproduces two failures. Known-reference gaps, not remediation. |
| E3 | 20261017T012328Z-conversation-browser | Five mocked conversation checks. Context/owner UI behavior under fixtures, not arbitrary real-provider behavior. |
| E4 | 20261017T015252Z-native-controls-browser | Four mocked native controls and installation record before filter v2. Not complete physical lifecycle assurance. |
| E5 | 20261017T020449Z-pocketpal-scanpolicy-v2-cloud | Eight synthetic-string policy tests. No measured image precision or recall. |
| E6 | 20261017T040000Z-pocketpal-gallery-dated-scan-owner | Owner-reported roughly ten submissions and results after about five minutes. No per-image reconciliation or successful-run logcat. |
| E7 | 20261018T125457Z-chat-final-review-full | 326 passed; two strict reference xfails; isolated DB with fake/scripted providers. Final capacity guard and owner-scoped regressions. |
| E8 | 20261018T124452Z-chat-eval-live | Ten real-model synthetic scenarios; limited predicates. No general numerical, injection or narrative guarantee. |
| E9 | 20261018T124708Z-chat-eval-live3-review | Post-hoc offline narrative heuristic correction; no new model calls or blind evaluation. |
| E10 | 20261018T163840Z-provider-neutral-contract-final | 329 passed; two strict reference xfails. Offline adapter contract and full isolated regressions. No live post-refactor Anthropic or other-vendor validation. |



All artifact identifiers resolve beneath evidence/runs/. Historical evidence retains its original scope. E7 records the final regression run; the document QA run is separate and is not additional application testing. The live pilot E8 and offline review E9 have the limitations below.

E8 completed ten scenarios on one synthetic account: tool predicates 10/10, numeric-labelled checks 7/7 applicable, period checks 2/2 applicable, boundary predicates 10/10 and narrative heuristics 9/10. Numeric-labelled checks include amount mentions and simulation arguments, not every generated claim. Boundary predicates use selected database checks and proposal-presence checks, not comprehensive attack coverage. An offline fixture-name correction gives 10/10 revised narrative heuristics on the same replies; the original manifest remains unchanged. Human narrative ratings are pending. The final review fixes were not subjected to another live-model run or a restarted-mobile test.

10.2 Permission and security tests traceability

| Boundary | Representative source test | Evidence interpretation |
| --- | --- | --- |
| Owner isolation | test_sec_own_cross_user_access_is_404_everywhere; test_sec_rls_blocks_cross_owner_even_without_app_filter | Negative object access and runtime-role isolation [E1]. |
| Identity binding | test_sec_own_cannot_inject_owner_or_unknown_fields; test_sec_auth_required_and_logout | Reject injected authority and revoked/absent session in exercised paths [E1]. |
| T2/T3 separation | test_sec_tools_registry_has_no_write_authority; test_sec_agent_proposes_user_approves | Pending proposal alone does not change allocation [E1]. |
| Exact approval | test_sec_apr_hash_mismatch_rejected; test_sec_apr_expired | Reject mismatched payload and expired proposal [E1]. |
| Replay and concurrency | test_sec_apr_replay_and_repeat; test_sec_apr_concurrent_approvals_apply_once | Covered duplicate/concurrent approvals apply once [E1]. |
| State freshness | test_sec_apr_stale_after_data_change_returns_replacement; test_cp2_review_fixes.py | Stale rejection and controlled connection interleavings [E1]. |
| Consent | test_sec_cons_upload_requires_consent; test_sec_cons_revoke_during_extraction_discards_result | Consent admission and persistence guard [E1]. |
| Injection boundary | test_sec_inj_image_text_cannot_act; test_sec_agent_hijack_attempt_and_tool_limit | Application response to scripted hostile outputs/tool calls [E1]. |
| Logging | test_sec_log_audit_has_no_sensitive_content | Listed sensitive values absent from exercised audit details [E1], not proof for every log sink. |



Representative test names above are in backend/tests/integration/test_security.py unless another file is specified. Further coverage resides in test_chat_continuity.py, test_cp2_cards.py, job-lease and deletion regressions. A reviewer should inspect assertions, setup, provider type and database role rather than judging assurance by names or pass counts alone.

10.3 Standards-informed review

OWASP ASVS provides a framework for web application and service verification [R1]. OWASP API Security Top 10 highlights API risk categories [R2]. OWASP MASVS structures mobile security review [R3]. They are used here as review lenses, not as a completed requirement-by-requirement assessment or certification claim.

| Review lens | Pocket Pal focus | Remaining assurance work |
| --- | --- | --- |
| ASVS | Authentication, session management, authorization, validation, cryptography and logging | Version-specific control mapping and independent validation of the deployed system. |
| API Security Top 10 | Object/function authorization, resource consumption, configuration and external API trust | Abuse, inventory and production-boundary testing. |
| MASVS | Mobile storage, authentication, network, platform interaction and privacy | Current APK/device lifecycle tests, release configuration and platform-specific verification. |



No standard level or compliance percentage is assigned. Legal obligations and payment-industry applicability depend on actual processing and deployment scope; they require specialist assessment beyond this technical report.

11 PROPOSED ADVANCED SECURITY DESIGN

11.1 Policy enforcement and contextual authorization

A future centralized policy layer could express action, actor, resource owner, consent state, purpose and risk context explicitly. The present checks are distributed across routes and services. An ABAC-style policy engine should be introduced only with fail-closed behavior, versioned policies and regression tests; a new abstraction that silently bypasses existing checks would weaken assurance.

For higher-risk future operations, step-up authentication can bind a recent authentication event to an exact action. Separation of duties and dual authorization may be appropriate for privileged administration or a future regulated payment scope. They are not currently implemented, and requiring two humans for ordinary POC pocket changes would impose unnecessary friction. The present user-approval boundary should remain explicit.

11.2 Cryptographic and operational hardening

Proposed production controls include managed key storage, envelope encryption where justified, separate key-administration privileges, authenticated service identities and secret rotation. Cryptographic erasure requires a proven key/data lifecycle and backup analysis; it cannot be claimed merely because a key was deleted. Independent audit export or append-only storage can improve tamper detection, but database event logging alone is not immutable evidence.

A zero-trust-inspired deployment would authenticate service access, minimize network reachability and verify authorization on each operation. This is a target architecture, not a claim that the current local environment implements a complete zero-trust program. Controls should address concrete threats and operational recovery rather than add terminology without enforcement.

11.3 AI assurance and privacy experiments

A future answer-verification layer could compare financial claims with typed tool results and require explicit uncertainty for missing data. An evidence-linked UI could show the contributing records and period without exposing chain-of-thought. Both need evaluation: omitted facts, stale references and falsely reassuring evidence links can mislead users even when the numbers displayed are correct.

The implemented eval_chat.py harness exercises a fixed synthetic fixture with per-run request/dollar caps and no automatic provider retry. Expected amounts come from deterministic fixture services, so it tests consistency with those services rather than independent financial correctness. A broader benchmark should freeze prompts, scoring rules and adversarial cases before execution, include human assessment and distinguish inappropriate proposals from unauthorized effects. Post-hoc heuristic fixes must retain original scores. Differential privacy, federated learning and secure computation are not implemented; each would require a defined use case and measured trade-off.

11.4 Network segmentation and controlled egress

Proposed topology. Expose only the intended ingress endpoint. Place API/BFF services, workers and PostgreSQL in separate network security zones, with explicit source, destination, port and purpose rules. PostgreSQL and private image storage should have no public route; administrative access should use a separately authenticated management path. Service identity and narrowly scoped credentials should accompany network rules, because a private address does not establish authorization. Existing session and row-level controls remain necessary after segmentation.

Outbound model requests should pass through an approved egress path that restricts destination services, validates TLS and handles redirects and DNS resolution without allowing access to private or metadata endpoints through untrusted routing input. A hostname list alone is insufficient if proxies or DNS behavior bypass it. Models and ordinary users must not select arbitrary base URLs. Verification should include denied direct database access, denied unapproved egress, redirect/private-address cases and proof that application processes cannot bypass the enforced path. This is a deployment target; the local POC provides no such network-enforcement evidence.

11.5 Routing and provider policy enforcement

Implemented boundary. The neutral adapter contract separates provider serialization from owner-bound tool dispatch; the current factory configuration selects only existing supported providers. There is no runtime third-party plugin loader or model-directed provider router. Offline adapter verification appears in E10. Adapters are trusted executable application code, not sandboxed extensions; a malicious adapter could disclose data regardless of message typing.

Proposed controls. Bind each approved route to a provider, model, endpoint, processing location, allowed data classes and policy revision. Keep credentials in a server-side secret store with separate scopes and rotation. Validate adapter capabilities before activation, including tool schemas, parallel-call identifiers, truncation semantics, errors and token accounting. A change in provider or endpoint requires compatibility tests and data-use review. Cross-provider fallback is disabled unless explicitly approved under equivalent conditions; failures must not select a consumer endpoint or weaker retention policy.

A router should log the approved route identifier, policy revision, decision and sanitized error category without recording credentials, images or full prompts. Review tests should cover expired approval, denied regions, unavailable policy service, credential rotation and attempted bypass. These gates are proposed; the current interface and provider factory do not implement an enterprise policy registry, credential broker or evidence-backed no-training enforcement.

11.6 Ingress and overload protection

Implemented application controls include BFF origin checks, constrained upstream routing, redirect rejection, a 9 MiB forwarding bound, the 8 MiB backend image limit and bounded request timeouts. They do not establish production TLS termination, trusted proxy configuration, authentication throttling or denial-of-service resilience.

Proposed ingress controls include TLS termination with reviewed certificate rotation, strict trusted-proxy and Host handling, route/method allowlists, content-type and streamed-body validation, authentication abuse limits, per-owner and global concurrency quotas, and queue admission with backpressure. A WAF can supplement these controls but cannot replace owner authorization or validate financial meaning. Forwarded headers from untrusted clients must not influence security decisions.

Qualification should test oversized and slowly streamed requests, spoofed proxy headers, burst and sustained load, queue saturation and recovery. Define explicit timeout and retry budgets across ingress, BFF, API, worker and provider so retries do not multiply cost or duplicate effects. Rate limits must distinguish accounts as well as network sources. Thresholds and availability objectives require measurement; this report assigns none without load evidence.

11.7 Orchestration controls and rollout gates

Implemented controls include owner context supplied by the session, validated tool arguments, a fixed T0–T2 registry, six model turns, eight dispatched tool requests, bounded conversation context and separate user approval for consequential plan changes. The adapter transports model requests and outputs; it does not acquire authority to run tools or commit financial changes. Provider output remains untrusted even when it conforms to the interface.

Proposed enterprise controls add centrally reserved request/cost budgets, cancellation and retry policies, concurrency admission, circuit breakers and policy checks before provider dispatch and consequential tool execution. Distributed reservations must be reconciled after timeouts, partial responses and worker crashes; per-process usage accounting is not a global spend guarantee. Prompt-injection defenses should be evaluated through adversarial outputs and unauthorized-effect checks rather than relying on instruction wording.

Layered rollout should first preserve existing service invariants, then validate denied and allowed routes in an isolated environment, measure latency and failure behavior, and activate enforcement with a tested rollback. Policy expiry or gate outage should deny new external sends while preserving recoverable jobs and available local functions. Gateway failure must not bypass authorization, prevent required local deletion jobs from progressing, or silently discard accepted work. Platform and security owners should approve deployment evidence before claiming these proposed layers as implemented.

12 RELEASE GATES AND REMEDIATION PLAN

12.1 Controlled demonstration gate

The demonstration should use an identified build, owner account, provider mode and profile with isolated storage. Permission and consent must be explicit. The operator should monitor stages and spending, retain synthetic evidence and stop on unexpected uploads or inconsistent ledger effects. Public video should use synthetic data. Private real-image demonstrations require owner authorization and controlled access; consent to a model call is not consent to publish the image.

Record outstanding risks alongside the demonstration. No UI success indicator should equate transport acceptance with verified extraction, settlement or final ledger correctness. Keep a manual recovery path and avoid destructive resets of the active trial profile.

12.2 Pre-public-release gate

Public release requires closure or scoped documented acceptance of the high risks in Section 9, with clear accountability. Required evidence includes deployed transport and cookie checks, least-privilege role verification, native race testing, mixed-gallery privacy evaluation, reference-gap remediation, abuse/cost enforcement, storage/backup protection and a restore exercise. Independent review should target negative authorization paths and active-client boundaries.

Retain a control-to-test matrix that names the source revision, test setup, dependencies, result and residual limitation. Failed and environment-limited runs remain visible. A change to provider, extraction schema, permission flow, database role or approval logic should trigger targeted regression and threat-model review. Security acceptance is a team decision, not an inference from build success.

12.3 Incident response and recovery

A proposed response playbook should distinguish credential exposure, cross-owner disclosure, unexpected image upload, ledger corruption and runaway provider expenditure. Initial actions may include pausing scan admission, revoking affected sessions, rotating compromised secrets, preserving access-controlled evidence and isolating the affected environment. Do not delete logs reflexively or reset the database before establishing scope.

Recovery requires validating restored data, reconciling images/jobs/ledger links, confirming key and session state, and verifying that the triggering condition is fixed. Communication and any notification obligations must be assessed by the responsible team with appropriate advice. No guaranteed recovery time or response service level is claimed; these must be set and tested for the intended deployment.

13 LIMITATIONS AND TEAM DECISIONS

This assessment is a source- and evidence-based self-review. It provides detailed permission implementation and known risks, but is not independent assurance. It does not prove authenticity of financial images, complete confidentiality against compromised hosts, correctness of every model answer, universal device support or regulatory compliance. The most important next step is measured closure of concrete risks rather than expanding unverified claims.

The team must assign named risk owners, approve the POC operating constraints, decide priorities, and authorize any residual-risk acceptance with an expiry/review condition. Security self-assessment should be revised when the shipped source or deployment changes. The companion Technical Documentation explains financial algorithms and topology; this report focuses on attack surfaces, enforced boundaries, assurance limitations and release decisions.

APPENDIX A SOURCE MAP

| Source location relative to repository root | Security relevance |
| --- | --- |
| backend/src/finassist/infra.py | Password/token primitives, owner binding, audit, idempotency and locks. |
| backend/src/finassist/services/core.py | Identity, sessions, consent and core financial operations. |
| backend/src/finassist/services/agent.py | Tool registry, schemas, loop limits, history and safe authority boundary. |
| backend/src/finassist/services/budget.py and cards.py | Proposal applicability, hashes, versions, funding and approval. |
| backend/src/finassist/services/imports.py and worker.py | File admission, extraction persistence, consent, leases, retries and purge. |
| backend/db/migrations/ | Ownership policies, constraints, transfer consistency and job schema. |
| web/src/lib/backend-server.ts and web/src/app/api/ | Origin enforcement, cookie mediation, forwarding and body limits. |
| web/src/components/ | Active-client owner isolation, rendering and scan controls. |
| android/pocketpal/src/main/ | WebView configuration, native bridge, scanner, state and manifest. |
| backend/tests/integration/test_security.py | Negative authorization, approval, consent, injection and audit tests. |
| docs/design/14-reference-contract.md | Open typed-reference design and known failing cases. |
| docs/design/16-conversation-gallery.md | Current-client lineage, gallery behavior and evidence boundaries. |
| backend/src/finassist/model_contracts.py; providers.py; tests/unit/test_provider_contracts.py | SDK-independent provider contracts and Anthropic wire conversion; offline qualification only. |



APPENDIX B EXTERNAL REVIEW REFERENCES

[R1] OWASP Application Security Verification Standard, version 5.0.0. https://github.com/OWASP/ASVS/tree/v5.0.0 — web and service verification reference; no conformance level claimed.

[R2] OWASP API Security Top 10, 2023 edition. https://api-security.owasp.org/editions/2023/en/0x00-header/ — API risk-awareness reference, not a certification checklist.

[R3] OWASP Mobile Application Security Verification Standard. https://mas.owasp.org/MASVS/ — mobile review framework; no completed MASVS assessment claimed.

External references were consulted on 18 October 2026. Their inclusion does not replace review of the actual source, configuration, dependencies and runtime behavior.
