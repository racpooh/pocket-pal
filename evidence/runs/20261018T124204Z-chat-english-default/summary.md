# English-default replies with Thai support (owner decision, 18 Oct 2026)

Owner decision: English is the primary language (international competition); Thai stays supported and its results are kept as bilingual evidence for the documents.

## Change
- `reply_language` server hint is now "Thai" only when the latest user message contains Thai letters (baht sign excluded); otherwise "English" (also for other languages).
- SYSTEM: English is the default; reply in Thai only when reply_language is Thai, regardless of earlier messages.
- eval_chat.py now has 10 scenarios: biggest_category in English (primary) and in Thai (bilingual check); English prompts after the Thai turn fail the narrative check if answered in Thai.

## Bilingual evidence already recorded (real model, synthetic account)
- 20261018T123021Z-chat-eval-live, scenario biggest_category (Thai prompt): complete Thai answer — "หมวดที่ใช้มากที่สุดคือ ช้อปปิ้ง ฿550.00 นับจาก 1 ถึง 15 ต.ค. 2026", with predicted/unassigned labelled and the period stated; numeric and period checks passed.
- 20261018T122238Z-chat-eval-live: the same Thai question exposed the empty-reply defect (max_tokens 700), since fixed and confirmed in the next live run.
- Known limitation before this change: English follow-ups after a Thai turn were answered in Thai (run 2). Fixed with the server hint; NOT yet verified live.

Tests: see manifest (scripted model). Dry run: 20261018T124146Z-chat-eval-scripted (10/10 scenarios executed; scores meaningless).
