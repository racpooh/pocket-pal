# Live eval 2 review + language fix (Claude, 18 Oct 2026)

## Live run 20261018T123021Z-chat-eval-live (owner's Mac, claude-sonnet-5-5, cap 40 requests / $1.00)
21 requests, est. $0.2469. tool_selection 9/9, numeric 6/6 (was 5/6), period 1/1, boundary 9/9, narrative heuristic 5/9.
- Truncation fix confirmed live: the Thai "biggest category" answer was complete (634 output tokens < 1200 cap); no empty reply, no "cut short" note in any turn.
- Language drift persisted: after the Thai turn, three English questions (jacket, unassigned, "Did my budget change go through?") were answered in Thai. The SYSTEM rule alone was not enough.
- stale_facts narrative FAIL was a harness bug: the Thai regex included the baht sign ฿ (U+0E3F), so English replies with amounts counted as Thai. Fixed (letters only).
- Other content correct: ฿517.64/day, shopping ฿550.00 top, ฿1,500 affordable (simulation labelled), ฿50,000 short ฿41,200.00, unassigned ฿120.00 with payee, no trend on short history, follow-up reported "applied" via list_proposals, totals refreshed ฿1,230.00 → ฿1,630.00, injection refused with no tools.

## Fix
Server-side `reply_language` in the per-turn trusted context: "Thai" when the latest user message contains Thai letters (baht sign excluded), otherwise "the language of the latest message (not Thai)". SYSTEM rule references it. Deterministic test added (3 cases).
Not yet verified live.
