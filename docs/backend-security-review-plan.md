# Backend and security review plan

Date: 15 October 2026 (Asia/Bangkok)

Status: Proposed scope and acceptance criteria for team review. This is not an implementation report or a claim of competition readiness.

## Authority and observed state

Product authority: `We go shenzhen case (1).docx`, Features 1–10 and required delivery checks. Feature 11 is optional; LINE is out of scope. Competition authority: the supplied International Track PDF. Earlier shared-chat proposals are exploratory, including bank embedding, autonomous pocket mandates, and framework choices.

The inspected workspace contains the two source documents and no application code or execution evidence. Implementation elsewhere has not been assessed. No competition score can be substantiated from this evidence. The published rubric supplies three weights, not a detailed marking scheme.

Preserve the Word permission model: read/propose is allowed; AI budget and goal changes require explicit approval. Automatic transaction import has separate, revocable consent. Do not introduce autonomous budget reallocations from the earlier chat without a product decision.

## Score readiness

| Axis | Requirements coverage | Evidence still needed |
| --- | --- | --- |
| Task completion, 40% | Strong conceptual fit: imports, budgets, goals, bills, insights and chat | Actual image extraction, review and import; reconciled calculations; completed approved changes; recovery from missing data and failures |
| Security and compliance, 30% | Good stated controls; implementation details remain open | Threat model; enforced ownership; consent and approval tests; runtime/deployment controls; deletion/retention behavior; known risks and applicable privacy obligations |
| Innovation and interaction, 30% | Useful combined workflow; uniqueness and usability unproven | Evidence that uncertainty-aware import and constraint-aware planning reduce effort or improve outcomes versus simpler baselines; user comprehension of proposals and corrections |

An illustrative internal ambition is 34/40 + 25/30 + 24/30 = 83/100. These are planning targets, not predicted marks or organizer subcriteria. Passing a percentage of tests does not imply the same competition score. Critical ownership, money integrity and approval failures are release blockers regardless of aggregate test results.

## Proposed backend shape

Use a modular backend plus worker and a relational database. Keep framework selection dependent on the team's existing competence and Claude's implementation environment. Modules: identity, consent, imports, transactions, bills, budget/cash-flow calculations, goals, proposals/approvals, agent tools, jobs and audit. Private object storage holds retained financial images.

Normal flow: authenticated request → owner-scoped service → deterministic calculation or validated extraction → proposal → explicit approval when required → atomic commit → audit and updated insights. The model can select permitted tools and explain their results; it cannot supply authoritative identity, approve its own changes or directly write financial state.

Interaction contracts must be designed now even if visual UI is deferred: review missing fields, approve/edit/cancel, show proposal before/after and assumptions, indicate stale proposals, show import status and provide clear error/recovery states.

### Financial invariants

- Money uses integer satang, with explicit currency, timezone and rounding rules. Percentages identify their denominator; rounding remainders reconcile.
- The balance at its effective date is a separate observation from historical transactions. Old imports must not subtract spending already reflected in that balance. Same-day cutoffs and late corrections need an explicit rule.
- Internal transfers and pocket reallocations conserve total money. Refunds link to their source where possible. An unpaid bill is a commitment, not a completed payment; matching its payment must not count it twice.
- Unresolved amount, direction or payment status is excluded from relevant financial totals. Missing information is visible; uncertain income is not treated as cash already available.
- Budget and goal calculations share one cash-flow model so bills, savings and buffers are not reserved twice. Affordability scenarios have no purchase side effect.
- Exact duplicates and ambiguous possible duplicates require different handling. Same amount/date alone is insufficient to discard a transaction automatically. Duplicate protection includes concurrent manual and imported records.

### Security invariants

- Derive identity from verified sessions; enforce ownership for API, tools, jobs and object storage. Test with actual runtime database roles.
- Bind approval to owner, exact proposal content/version, expiry and relevant state. Editing a proposal invalidates its old approval. Recheck dependencies at commit, with atomic concurrency control.
- Apply idempotency and database uniqueness at the business-operation boundary. Reusing a key with a different payload fails; concurrent retries cannot apply twice.
- Consent is scoped and versioned. Workers recheck it before processing and persistence. Revocation prevents queued work from importing; deletion cannot be undone by a retry. Already completed processing has an explicit retention/deletion policy.
- Validate uploaded size/type and parsed fields. Image text is data, never authorization. Tool access is allowlisted; secrets remain server-side; logs redact sensitive content.
- Specify TLS, encryption at rest, key custody, retention and backup deletion behavior for the actual deployment. A local database alone does not demonstrate these controls.
- Bound model/tool calls, request rates, timeouts and job retries. Record failures and recover without silently losing or duplicating work.

## Methods worth implementing

1. **Explicit consent and runtime action controls.** Separate import consent from per-proposal approval, and enforce them outside the model. FDX's April 2026 initiative identifies agent identity, consent delegation and security as active open-finance issues. OWASP ACS describes runtime middleware hooks and declarative enforcement. Our scoped service-layer controls can apply these ideas without claiming ACS conformance or implementing an entire new framework.
2. **Deterministic financial calculations with evidence-linked explanations.** Return calculation inputs, assumptions, version, result and source references alongside each proposal. This supports inspectable explanations; it is not proof that the data or formula is correct.
3. **Reliable execution using idempotency and atomic writes.** Use database transactions and version checks for changes; use a transactional outbox if committed changes must reliably enqueue downstream jobs. Idempotency is established financial API practice, not a novelty claim.
4. **Risk-based security verification.** Map relevant ASVS controls and agent risks to actual tests and evidence. Keep pass/fail/not-tested/not-applicable distinct. References to standards are not certification.

FAPI 2.0 is relevant to a future high-security partner integration. Full FAPI implementation, real bank transfers, multi-bank connectors, blockchain and multi-agent infrastructure are not prerequisites for this Word-scoped prototype and should not consume the two-day core build.

## Two-day execution proposal

| Checkpoint | Claude implementation responsibility | Codex design/review responsibility | Exit evidence |
| --- | --- | --- | --- |
| 15 Oct, first block | Implement agreed schema, identity and service skeleton | Freeze financial semantics, permission model, API contracts and expected test outputs | Versioned contracts; ownership negative tests; deterministic fixtures |
| 15 Oct, second block | Transactions, bill linking, calculation core, proposal/approval commit | Review balance boundaries, duplicate paths, formula reconciliation and concurrency | One complete backend scenario with independent expected outputs |
| 16 Oct, first block | Extraction/import review flow, agent tools, goals, recalculation, revoke/delete | Adversarial tests, prompt-injection boundaries, stale approval and retry review | End-to-end API flow using real extraction on representative images, not only stub OCR |
| 16 Oct, second block | Fix findings; reproducible setup and evidence runner | Rerun affected cases, review docs, identify remaining risks and release blockers | Tested backend candidate, documented limitations and evidence bundle |

This is an aggressive target conditional on available engineering time, a familiar stack and model/deployment access. A failed checkpoint triggers a candid scope/status decision; it does not silently remove required Word features. Mobile album discovery, permission behavior, on-device filtering and background scheduling require an OS decision and device testing. An API image-upload test does not satisfy the full album delivery check. Visual design can wait; this integration spike should not.

## Acceptance suite

Use independently calculated expected outputs and versioned synthetic fixtures. Include clear images, unreadable fields, pending/unpaid bills, receipts plus slips for one purchase, exact duplicates and distinct purchases with matching amounts.

Required cases: user A cannot read/change B's records or images; revoked consent blocks a queued import; uncertain direction/amount/status is not totaled; receipt/slip duplicates count once; manual/import races count once; old slips do not reduce opening balance again; bill settlement counts once; transfers conserve money; refund accounting reconciles; savings and bills are not double reserved; income dates affect feasibility; impossible goals return alternatives; purchase simulations have no mutation; unapproved or altered proposals fail; stale proposals require refresh; concurrent/repeated approvals apply once; deletion survives retries; malicious image text cannot grant tools or mutate budgets; model failure leaves saved records intact.

Evaluate actual agent runs separately from deterministic core tests. Compare the same held-out cases against a fixed budgeting rule and a plain LLM baseline. Report arithmetic/constraint errors, task completion, correction burden, clarification count, latency and cost. A small team usability review is formative evidence, not a population-wide validation. Do not invent success rates before running the suite.

## Four deliverables

| Deliverable | Minimum contents | Completion criterion |
| --- | --- | --- |
| Technical documentation | Scope, architecture/trust boundaries, data model, financial semantics, workflows, API contracts, core algorithms, tradeoffs and limitations | Describes the implemented version and links requirements to evidence |
| Source code | Backend and worker, migrations, tests, fixtures, README, environment template and reproducible startup | Clean setup reproduces the documented run without embedded secrets |
| Security self-assessment | Assets, threats, roles/permissions, controls, test evidence, deployment configuration, data lifecycle and known risks | Every claimed control is evidenced or marked pending; no unsupported compliance assertion |
| Execution evidence | Sanitized scenario inputs, expected/actual results, action/consent/proposal identifiers, before/after state and demo recording | Traceable to code version, configuration, model identifier and run timestamp; clearly marks mocks |

Use one traceability chain: requirement → design decision → code → test → execution artifact. Each scenario run should produce a manifest, sanitized event log and summary. Do not store chain-of-thought, secrets or raw personal images in evidence.

The PDF calls the standalone demo video optional but mentions a demo video under non-on-chain execution evidence. Plan to include a video of at most five minutes. Presentation deck remains a separate competition submission even though this workstream focuses on four deliverables.

## Coordination

Proposed roles: Codex owns design contracts, independent expected results and review findings; Claude owns implementation and fixes; team members review product assumptions, scenarios and submission clarity. Review at checkpoints rather than waiting for the entire backend to finish. This document has not been sent to Claude; no direct Claude connection has been established in this chat.

Before implementation, resolve the implementation workspace/handoff channel, familiar stack and model access, supported mobile OS, demo currency/timezone, and balance cutoff semantics. These decisions can be made without final visual designs.

## Sources checked on 15 October 2026

- Product DOCX and competition PDF in this directory, read in full in the preceding review.
- [FDX agentic financial data sharing initiative, 14 April 2026](https://financialdataexchange.org/fdx-feed/as-ai-agents-get-involved-in-financial-data-sharing-leading-standards-body-launches-initiative-to-stay-ahead/): industry direction, not a claim of finalized agent delegation standards.
- [OWASP Agent Control Standard](https://genai.owasp.org/resource/agent-control-standard-acs/): runtime enforcement and transparency principles.
- [OWASP Agentic Applications Top 10](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/): risk framing.
- [OWASP ASVS](https://owasp.org/projects/asvs): testable application security requirements; pin the version when mapping controls.
- [Stripe idempotent requests](https://docs.stripe.com/api/idempotent_requests): established retry behavior and payload consistency.
- [OpenID FAPI 2.0 Security Profile](https://openid.net/specs/fapi-security-profile-2_0.html): future partner API security context.
