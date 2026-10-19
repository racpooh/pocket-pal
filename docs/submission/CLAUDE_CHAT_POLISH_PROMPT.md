# Claude task — final Chat grounding and demonstration readiness

Work in `/Users/POOH/Development/case/shenzen`. The active client is `web/` hosted by `android/pocketpal`, not the legacy Compose UI. Read AGENTS.md, HANDOFF.md, the current README, `services/agent.py`, and the current technical/security reports before changing behavior. Preserve the Pocket Pal UI and existing security boundaries. This task is to improve grounded, useful conversational responses tonight, not to add architectural novelty.

## Non-negotiable boundaries

- Run no Git commands of any kind. Give the owner explicit commands with no inline shell comments when ready.
- Do not reset any database, clear app data, touch private slips/labels, overwrite .env, or restart the owner's live demo services without coordinating. Codex has refreshed the gallery demo data; do not seed that profile automatically.
- Use isolated test/e2e profiles and synthetic fixtures. No paid model calls without a separately approved budget. Scripted-provider tests must be labeled as such and do not establish real-model answer quality.
- Keep money calculations in deterministic server logic using integer satang. Do not introduce floats into money paths, make the LLM do arithmetic, or weaken owner checks, consent, proposal approval/freshness or dedup rules.
- No RAG/vector DB, multi-agent framework, new provider, UI redesign, or broad schema migration. Preserve T0–T2 model authority; approval remains user-only. Do not claim the two reference gaps are fixed.

## P0: inspect and implement narrowly

1. Temporal grounding: the current static SYSTEM prompt has no explicit server-generated current date/timezone; get_overview returns today, but a first call to get_spending can still choose a relative range without first fetching it. Add trusted current-date/timezone context from the signed-in user's server profile, without personal identifiers. Define today, this calendar month, last calendar month and rolling last-30-days explicitly. Keep end_exclusive semantics; test timezone/month boundaries. Do not use the provider's assumed date or history as authoritative time.

2. Grounded financial facts: inspect the actual tool payloads before changing them. get_spending currently returns total_satang plus category confirmed/predicted amounts. The prompt says “never do arithmetic”, yet the model may need to combine categories or convert money. Add backward-compatible server-computed display facts and, where useful, deterministic ranked category totals and period metadata. Reuse existing money/ledger functions. Preserve refund, excluded-status, unassigned and confirmed/predicted distinctions. Avoid broad financial algorithm changes. An empty history is absence of detected/entered records, not proof of no spending.

3. Check a concrete unit-risk before polishing prose: in services/budget.py::insights, estimated_savings_per_month_satang is added to cap and then passed to goal feasibility as capacity per income event, even when income frequency is not monthly. Verify the units with weekly/biweekly/monthly synthetic cases. Normalize using an explicitly documented deterministic period rule if feasible; otherwise return an explicit unavailable goal-impact explanation for unsupported conversions instead of a misleading numeric claim, and report the feature limitation. Do not silently treat monthly savings as weekly savings.

4. Answer quality: lead with a direct answer, followed by up to three useful facts and one actionable next step when supported. Name the period and assumptions. Distinguish current balance, historical spend, simulation and pending/applied proposal. Explain insufficient history without inventing monthly patterns. Use one focused clarification only when necessary. Preserve Markdown rendering and the user's language. Do not invent capabilities such as bank settlement verification or transferring money.

5. Context: preserve explicit memory consent and freshness rules. Test a follow-up after a proposal, after approval, after new spending, and with memory disabled. A previous answer or proposal is not current financial state. Do not make every simple greeting trigger all financial tools.

## Validation and stopping point

Add meaningful deterministic tests for date boundaries, ranked totals including refunds/unassigned/predicted records, zero history, pending vs applied state and stale history. Run affected tests and the relevant security/approval regressions; record evidence under evidence/runs with exact counts including xfails/skips. Update traceability/HANDOFF and describe changed tool fields for compatibility. Do not report scripted tests as real-model evaluations.

Prepare, but do not execute paid calls for, a small synthetic novel-prompt evaluation: overview, biggest category, affordability, insufficient funds, unassigned spending, insufficient history, follow-up after approval, stale facts and a prompt-injection attempt. Separate tool-selection correctness, numeric correctness, scope/period correctness, narrative usefulness and refusal/approval boundaries. Have expected numeric results come from deterministic fixture calculations. Let the owner approve a hard request/dollar cap before any live-model run; stop rather than retrying beyond the cap.

Deliver: focused code changes, evidence, before/after synthetic examples, remaining limitations, and precise owner commands to test/restart. If there is not enough time, prioritize items 1–3 and regression safety over stylistic expansion. Do not change reports to claim new controls until their implementation and evidence exist.
