# 00 — Requirements baseline

Status: **Draft for Codex and team review** (Claude, 15 Oct 2026, 13:00 ICT).
This file does not change scope. It classifies what the sources say and flags conflicts.

## Sources and how they were read

| # | Source (in `docs/`) | Read? | Authority |
|---|---|---|---|
| 1 | `We go shenzhen case (1).docx` | Yes, full text via pandoc. No images or tables in the file. | Product requirements (Features 1–11, delivery checks) |
| 2 | `633650123934793767_PBCSF…International Track (2).pdf` | Yes, 4 pages, text via `pdftotext -layout`. Graphic layout not visually inspected. | Competition rules and submission checklist |
| 3 | `backend-security-review-plan.md` | Yes, full | Codex proposal — **not approved architecture** |

No `AGENTS.md`, code, git history, tests or evidence existed in the repository before this checkpoint.

## Decisions recorded 15 Oct 2026 14:00 ICT (team answers)

| ID | Decision | By |
|---|---|---|
| D1 | Python 3.12 + FastAPI + Postgres 16 accepted | team |
| D2 | Anthropic API: extraction `claude-haiku-5-5` (compare `claude-sonnet-5-5` on the eval set), chat `claude-sonnet-5-5`; Pooh holds the API key (local `.env`, never committed) | Claude chose; team accepted delegation |
| D3 | Demo device: Android (Samsung S23). App framework not decided yet | team |
| D4 | Deployment service delegated to Claude → proposed Google Cloud (Cloud Run, Cloud SQL Postgres 16, private GCS, Secret Manager, asia-southeast1); pending account availability | Claude proposal |
| D5 | Category → pocket mapping, no per-transaction override in v1 | team |
| D6 | Date-only slip on the balance date = already reflected in the balance | team |
| D7 | Redacted real slips may be sent to the provider for evaluation | team |
| D8 | Self-hosted auth (argon2id + opaque session tokens) | team |
| — | **Internal acceptance deadline: 16 Oct 2026** (team review). Official submission remains 20 Oct 22:59 ICT | team |

## Time reality (checked, not assumed)

- Now: Thu 15 Oct 2026, ~13:00 ICT (UTC+7).
- Internal target in the brief: backend prototype ready for acceptance by 15–16 Oct.
- **Official submission deadline (PDF): 20 Oct 2026 23:59 Beijing = 22:59 ICT.** Submissions may be updated until then.
- Assessment: ~1.5 working days remain for the internal target, ~5.4 days to the real deadline. A backend that genuinely satisfies Features 1–10 with real extraction, agent workflow, evidence and docs is **not realistic by end of 16 Oct**. A reviewable core (identity, ownership, money semantics, transactions/bills/pockets, proposal→approval→commit, upload-based import with a real extraction call, minimal agent tools) is plausible by end of 16 Oct if decisions in §5 are answered today. See `07-checkpoints.md`. Nothing is removed from scope; items not reached are reported as not done.

## 1. Product understanding (from the Word file)

A Gen Z personal finance assistant delivered as a standalone mobile app with an AI chatbot as the main interface. The main input is automatic detection of bills/receipts/payment slips from the user's permitted photo library; manual entry is the backup. The backend keeps a ledger of detected/entered transactions, unpaid bills, budget pockets, goals and a cash-flow forecast. Deterministic backend functions compute budgets, allowances, goal feasibility, duplicates and spending analysis; the LLM calls them and explains results. The AI may read and propose; budget/goal changes need user approval; automatic import has its own revocable consent.

## 2. Confirmed requirements (R-IDs used for traceability)

Confirmed = stated in the Word file and/or confirmed in the brief. Wording condensed; the Word file prevails.

| ID | Requirement | Source |
|---|---|---|
| R1.1 | Sign up, log in, per-user data separation | W§1 |
| R1.2 | Onboarding: income amount, frequency, next income date, current balance **and its date**, essential expenses, savings preferences | W§1 |
| R1.3 | Photo-access and automatic-processing consent; user chooses scope and scan date range | W§1 |
| R2.1 | Identify bills/receipts/slips among permitted photos | W§2 |
| R2.2 | Extract amount, date, merchant/payee, reference, category, direction *when identifiable* | W§2 |
| R2.3 | New-photo detection on open/refresh; background scans within OS limits; scan status + last success | W§2 |
| R2.4 | Detect duplicate images and duplicate payments, incl. receipt + slip for one purchase | W§2 |
| R2.5 | Auto-save validated records under auto-import consent, marked auto-imported, correctable/removable | W§2 |
| R2.6 | Review queue for unclear records; ask only for missing/uncertain details; exclude unresolved amount/direction/payment status from totals | W§2 |
| R2.7 | Pause scanning, change access, delete imported data | W§2 |
| R3.1 | Manual income/expense/transfer/refund with date, amount, description, category | W§3 |
| R3.2 | Edit/remove any record incl. auto-imported | W§3 |
| R3.3 | Check for matching imported transaction before creating a manual duplicate | W§3 |
| R4.1 | CRUD pockets; show allocation, spending, remaining | W§4 |
| R4.2 | Move budget between pockets directly or via chat; AI reallocations need approval | W§4 |
| R4.3 | Pockets are allocations; reallocation is not an expense and creates no money | W§4 |
| R5.1 | Analyse income/expenses/history (ideally 3 months) | W§5 |
| R5.2 | Propose allocations + daily/weekly allowance after bills, essentials, savings, buffer | W§5 |
| R5.3 | Customise amounts/percentages; label each percentage's base | W§5 |
| R5.4 | Trade-off calculation when one pocket increases | W§5 |
| R5.5 | Detect overspending and upcoming cash shortage; suggest revised plan | W§5 |
| R5.6 | Recalculate forecasts as records change; apply allocation changes after approval | W§5 |
| R6.1 | Goal: name, target, current savings, deadline | W§6 |
| R6.2 | Feasibility using income dates, expenses, available money, commitments | W§6 |
| R6.3 | Required contributions, progress | W§6 |
| R6.4 | Alternatives: later deadline, smaller target, spending changes | W§6 |
| R6.5 | Recalculate on change; approval before changing saved plan | W§6 |
| R7.1 | Unpaid bills vs completed payments; amount, due date, status | W§7 |
| R7.2 | Link paid bill to its transaction; count once | W§7 |
| R7.3 | Recurring charges and changes in comparable bills *when evidence exists* | W§7 |
| R7.4 | Spending by category, merchant, period; budget vs actual | W§7 |
| R7.5 | Specific recommendations with estimated savings and goal impact | W§7 |
| R7.6 | Label history as detected/entered; photos do not prove completeness or settlement | W§7 |
| R8.1 | Chat answers from saved records and conversation context | W§8 |
| R8.2 | Budget creation, allocation negotiation, goal planning, bill questions, spending explanations | W§8 |
| R8.3 | "Can I afford this?" with impact on bills, available spending, goals; no record created | W§8 |
| R8.4 | Short explanations + cards with Approve / Edit / Cancel | W§8 |
| R8.5 | Focused questions when info missing; never invent records | W§8 |
| R9.1 | Ownership enforced on every DB, file and assistant-tool request | W§9 |
| R9.2 | TLS and encryption at rest for financial data and images | W§9 |
| R9.3 | Model keys and DB secrets backend-only | W§9 |
| R9.4 | On-device album filtering where feasible; upload only relevant consented images | W§9 |
| R9.5 | Explain processing/retention; revoke access; delete data | W§9 |
| R9.6 | Read/propose only for AI; approval for budget/goal changes; separate revocable import consent | W§9 + brief |
| R9.7 | Validate extracted fields and tool requests; image text is untrusted | W§9 |
| R9.8 | Prevent duplicate operations; reject stale proposals; log imports/corrections/approvals without sensitive image content | W§9 |
| R10.1 | Relational DB for users, income schedules, transactions, pockets, budgets, goals, bills, import status, chat history, approvals, audit | W§10 |
| R10.2 | Private owner-restricted image storage | W§10 |
| R10.3 | Integer satang; keep source image/reference and review status | W§10 |
| R10.4 | Backend functions: cash flow, allocation, goal feasibility, duplicates, spending analysis; LLM calls and explains | W§10 |
| R10.5 | Current balance separate from history; old slips do not subtract again | W§10 |
| R10.6 | Bill payments and internal transfers linked; no double counting | W§10 |
| R11 | Gamification (quest, badge, no repeat rewards from moving funds back and forth) — **optional** | W§11 |
| DC1–DC4 | Delivery checks: album → import/review → insights end-to-end; reconciliation; unauthorized access / unapproved change / repeated approval blocked; deliverables | W "Required delivery checks" |
| S1–S6 | Submission: technical documentation, deck (≤10 min), demo video (≤5 min), source code with README + **GitHub link** + deployment + tests, security self-assessment (**permission tiers** + known risks), execution evidence (sandbox logs + video) | PDF |
| X1 | LINE out of scope; no real bank transfer | brief + Word |

## 3. Proposals (not approved — need a decision or Codex review)

| ID | Proposal | From | Claude's position |
|---|---|---|---|
| P1 | Modular backend + worker + relational DB, private object storage | Codex | Agree. Single deployable + one worker process using the same codebase. |
| P2 | Transactional outbox for downstream jobs | Codex | Simplify: a Postgres `job` table written in the same transaction **is** the outbox; no broker. |
| P3 | Test with actual runtime DB roles (implies RLS) | Codex | Agree as second layer, after app-layer scoping works; see `03`. |
| P4 | Four-stage classification pipeline (extraction → merchant identification → purpose → pocket) | Codex | Keep the four **data fields**, not four pipeline stages. See `04`. |
| P5 | Compare agent against fixed budget rule and plain LLM baseline | Codex | Agree, but limited to a small held-out scenario set; formative only. |
| P6 | Illustrative 83/100 internal ambition | Codex | **Not adopted.** No basis for a numeric score; see §6. |
| P7 | Category → pocket mapping, no per-transaction pocket override in v1 | Claude | Needs team decision (D5). |
| P8 | Decode the slip QR locally for a deterministic payment reference | Claude | Hypothesis; verify on redacted samples before relying on it. |

## 4. Assumptions (Claude; each must be confirmed or rejected)

- A1 Single currency THB; amounts in integer satang; no FX.
- A2 Business timezone per user, default `Asia/Bangkok`; stored timestamps are UTC.
- A3 One tracked "spendable" account in v1 (multiple accounts modelled, but balance projection only for accounts with an opening-balance observation).
- A4 Demo users and data are synthetic; team members' own slips are used only with their explicit consent, redacted, and never committed to Git.
- A5 Album scanning runs on the phone; the backend receives only candidate images the client filtered and the user consented to. Backend tests can prove the upload/import path, **not** album discovery, OS permission behaviour or background scheduling.
- A6 The prototype is demonstrated in a sandbox (no real bank connection, no money movement).

## 5. Unresolved decisions (owner: team unless noted)

| ID | Decision | Why it matters | Claude's default if no answer |
|---|---|---|---|
| D1 | Backend language/stack | Everything | Python 3.12 + FastAPI + Postgres 16 (see `01`) |
| D2 | Vision/LLM provider and model for extraction and chat; who holds the API key and budget | Real extraction evidence; privacy disclosure | Provider-agnostic interface; fake provider in tests; real provider blocked until answered |
| D3 | Mobile OS for the demo and app framework | Album permission + background behaviour; R2.1/R2.3/R9.4 | Android first (APK sideload) — not decided |
| D4 | Deployment target for the demo (cloud/region, managed Postgres, object storage) | R9.2 encryption-at-rest claim must match reality | Local Docker for dev; claims limited to what is deployed |
| D5 | Category vs pocket model | Data model, UX of corrections | Category on transaction; pocket derived from category mapping |
| D6 | Same-day opening-balance cutoff when a slip has date but no time | R10.5 | Treat as already reflected (not subtracted), flag on the card |
| D7 | Can team members' redacted slips be sent to the chosen provider for evaluation? | Real-OCR evidence vs privacy | No; synthetic slip images only |
| D8 | Auth: self-hosted email/password vs managed (e.g., Supabase/Firebase) | Security evidence, time | Self-hosted, argon2id, opaque hashed session tokens |

## 6. Conflicts and tensions between documents (not resolved here)

1. **Deadline**: the brief's 15–16 Oct target vs PDF deadline 20 Oct 22:59 ICT. Not a contradiction, but it changes what "done" means for each checkpoint.
2. **Language**: PDF says all submissions are in English. The design docs and code are therefore in English; team discussion can stay Thai.
3. **GitHub link required** (PDF S4) but the folder is not a git repository. Someone on the team must create the repo.
4. **Demo video**: PDF lists it as optional (item 03) but also lists a demo video under execution evidence for non-on-chain topics (item 06). Plan for one ≤5 min video (Codex noted this too).
5. **Permission tiers**: PDF requires "permission-tier implementation" in the self-assessment. Neither the Word file nor Codex's plan names tiers. `03` proposes explicit tiers.
6. **Category extraction**: Word lists "category" among fields extracted from photos "when identifiable". The brief correctly notes that purpose is usually *not* on a slip. Resolution proposal: extraction may return a document-level hint (e.g., an electricity bill), but transaction purpose is suggested from history/merchant knowledge and labelled as predicted.
7. **"Standalone mobile app"** in Word vs "not fully locked" in the brief. Backend is designed client-agnostic; album scanning still requires D3.
8. **Real extraction by 16 Oct** (Codex exit evidence) vs **no personal slips sent externally** (brief). Requires either synthetic slip images or D7.
9. **Encryption at rest** (R9.2) cannot be evidenced on a laptop Postgres. Depends on D4.
10. **Codex's numeric score target** vs the brief's instruction not to exceed 80% because features exist. Dropped.

## 7. Gap assessment per scoring axis (qualitative; no score predicted)

The organiser publishes weights only, not sub-criteria. Test pass rate is not a proxy for judges' marks.

| Axis | What exists today | Biggest gaps | What would move it |
|---|---|---|---|
| Task completion 40% | Requirements and a reviewable design; money/time/allocation core with unit tests (this checkpoint) | No ledger, import, cash-flow, goals, bills, agent or mobile client yet; album scanning unproven | End-to-end scenario: slip upload → validated import or review → updated pockets/allowance → chat proposal → approval → recalculation, on a real model call |
| Security & compliance 30% | Invariants, threat list, permission tiers on paper; draft schema with DB-level constraints | No running auth, ownership tests, consent enforcement, deletion, deployment controls | Negative tests that actually run (cross-user, stale/replayed approval, revoked consent, injected image text) + an honest self-assessment with known risks |
| Innovation & interaction 30% | An idea worth testing: ask only when the answer changes the decision; uncertainty-aware pockets | No evidence it reduces effort; no UI | Measured questions-per-decision and correction burden vs a baseline on a held-out set; clear approval cards |

Release blockers regardless of other progress: any cross-user read/write, any double-counted money path, any budget/goal change without a matching approval, any queued job that imports after revocation.
