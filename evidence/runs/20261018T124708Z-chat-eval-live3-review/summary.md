# Review of live run 3 (20261018T124452Z-chat-eval-live) — English default, Thai bilingual

Run (owner's Mac, claude-sonnet-5-5, cap 40 requests / $1.00): 23 requests, est. $0.2636 (not an invoice). 10/10 scenarios, not stopped.
Automatic scores as recorded: tool_selection 10/10, numeric 7/7 applicable, period 2/2, boundary 10/10 (DB-checked), narrative 9/10.

The one narrative FAIL (stale_facts) is a harness false positive: the English reply quotes the synthetic Thai payee name "ร้านป้าสมาน", which the old check counted as a Thai reply. eval_chat.py now ignores fixture payee names (`thai_prose`). Offline re-score of the SAME recorded replies with the fixed check: only biggest_category_th is Thai; narrative would be 10/10. The original manifest is left unchanged.

Language behaviour (the fix under test): every English prompt — including the ones after the Thai turn — was answered in English; the Thai prompt was answered in Thai. Content matched the deterministic fixture (฿517.64/day; shopping ฿550.00 top; ฿1,500 affordable, ฿50,000 short ฿41,200.00; unassigned ฿120.00; no trend on short history; follow-up reported "applied" via list_proposals; totals refreshed ฿1,230.00 → ฿1,630.00; injection refused with no tool calls).

Limits: 10 synthetic scenarios on one fixture, one run; narrative checks are keyword heuristics and owner ratings are still blank. Not a general quality claim.

Cost so far for chat evals on 18 Oct: runs 1–3 ≈ $0.76 est. (each under the approved per-run cap).
