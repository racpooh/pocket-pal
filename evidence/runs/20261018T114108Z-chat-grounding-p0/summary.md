# Chat grounding P0 items 1–3 (Claude, 18 Oct 2026)

Scope chosen by owner: items 1–3 of `docs/submission/CLAUDE_CHAT_POLISH_PROMPT.md`. Items 4–5 (answer style, context follow-up tests) and the live-model evaluation set were NOT done.

Result: 313 passed, 2 xfailed (REF-GAP-1/2, unchanged), 0 skipped, 0 failed. 13 new tests (5 unit, 8 integration). Chat model is SCRIPTED: these tests prove the server-side facts and prompt content, not real-model answer quality. No paid calls. No live service restarted; no dev/gallery data touched.

## 1. Temporal grounding
- `agent.time_context()` builds per-turn server facts from `app_user.timezone` and the server clock: `today`, `weekday`, `timezone`, named periods (`today`, `this_month_to_date`, `last_month`, `last_7_days`, `last_30_days`; local dates, end_exclusive) and the period rules. No email, owner id or name.
- `agent.system_prompt()` appends it to SYSTEM as a labelled trusted block; SYSTEM gains rules to use these dates and never assume a date.
- Pure helper `domain.periods.reporting_periods(today)`; tests cover mid-month, Jan 1, leap-year Mar 1, Dec 31, and Bangkok midnight (16:59Z vs 17:30Z on 31 Oct).

## 2. get_spending facts (backward compatible — old fields unchanged)
Added: `period{start,end_exclusive,days}`, `counted_records`, `ranked_categories[{category,total_satang,confirmed_satang,predicted_satang,display}]` (largest first, ties by code; unassigned NOT ranked), `unlinked_refunds_satang`, `display{total,unassigned,unlinked_refunds}`, `totals_rule`, and `empty_note` when no counted records. `end_exclusive <= start` now returns `{"error":"invalid_range"}` (previously an empty result).

Before (synthetic, 1–15 Oct): `{"total_satang":80000,"by_category":{"food":{"confirmed":30000,"predicted":5000},"shopping":{"confirmed":33000,"predicted":0}},"unassigned_satang":12000,...}` — the model had to add 30000+5000 and rank itself; the 70.00 unlinked refund was invisible.
After: same fields plus `ranked_categories[0] = food 35000 ("350.00", 30000 confirmed / 5000 predicted)`, `shopping 33000`, `unlinked_refunds_satang 7000`, `display.total "800.00"`, `counted_records 6`.
Empty period after: `counted_records 0`, `empty_note "...not proof that nothing was spent."`

## 3. Insights goal-impact units (bug fixed)
Before: `cap + estimated_savings_per_month_satang` was passed as capacity PER INCOME EVENT. With weekly income a 1,000 THB/month saving was treated as 1,000 THB per week (4.33× overstated); biweekly 2.17×.
After: `domain.goals.monthly_to_per_event` (12 months = 26 biweekly = 52 weekly; floor). 1,000 THB/month → monthly 1,000.00, biweekly 461.53, weekly 230.76 per event; irregular income → `goal_impact_unavailable: true` with a reason, no numeric claim. Each impact now states `income_frequency`, `added_capacity_per_income_event_satang` and the `conversion` rule.

## Not done / limitations
- Items 4–5 (answer structure rules beyond the date/empty-period lines; follow-up after proposal/approval/new spending/memory-off tests) and the synthetic novel-prompt live evaluation set.
- Real-model behaviour unverified; the model may still ignore the context. Live services must be restarted by the owner to load this code.
- `this_month_to_date` ends today; full-month totals for the current month are not offered (future days have no records).
