# Chat polish items 4–5 + live-eval harness (Claude, 18 Oct 2026)

Result: 317 passed, 2 xfailed (REF-GAP-1/2 unchanged), 0 skipped. Chat model SCRIPTED: no claim about real-model answers. No paid calls.

## Item 4 — answer quality (SYSTEM rules)
Direct answer first naming the period/assumption; ≤3 supporting facts; ≤1 app-supported next step. Keep four fact kinds separate and labelled (balance projection, historical spending, what-if simulation, proposal). Short history → say so, no trends. Greetings → no tools. Cannot verify settlement, contact banks, transfer or pay. Existing language/Markdown/brevity rules kept.

## Item 5 — context freshness
New read-only T0 tool `list_proposals` (5 newest; proposal_id, kind, CURRENT status incl. expired, created_by, created_at, decided_at, summary). It deliberately omits payload/card hashes and approval actions. SYSTEM: call it before stating a proposal's status. Tests: pending → applied after user approval (history still contains the stale "pending" text; the tool returns applied), cancelled, fresh totals after new spending (300.00 → 350.00 with ranking), rule presence. Memory-disabled behaviour was already covered by test_chat_continuity (unchanged, passing). The approval test uses a budget_plan trade-off because test_security asserts globally that no agent-created reallocation is ever applied.

## Live evaluation harness (prepared, NOT run live)
`backend/scripts/eval_chat.py`: 9 synthetic scenarios (overview, biggest category in Thai, affordable, insufficient funds, unassigned, insufficient history, follow-up after approval, stale facts, prompt injection). Expected numbers from deterministic server functions on the fixture (daily allowance 517.64; month total 1,230.00; top category shopping 550.00 after a linked refund; unassigned 120.00; ฿1,500 affordable; ฿50,000 not). Dimensions scored separately: tool_selection, numeric, period, boundary (automatic, DB-checked for boundary) and narrative (keyword heuristic + blank owner rating). Caps: --max-requests 40, --max-usd 1.00 on top of the usage ledger; max_retries=0; stops at cap. Owner approved 40 requests / $1.00 on 18 Oct 2026.
