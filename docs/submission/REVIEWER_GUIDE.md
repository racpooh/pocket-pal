# Submission and demonstration guide

Updated 19 October 2026. This guide indexes the supplied competition rules and the current POC; it is not an organizer interpretation or a claim of complete acceptance.

## What the supplied rules require

The International Track asks teams to design and build an AI agent that completes real tasks in a financial scenario. Topic A covers budgeting, bill analysis, spending insights and actionable recommendations from income and expenses. The weighting is task completion 40%, security/compliance 30%, innovation/interaction 30% (rules page 2). The supplied rules do not state a production deployment requirement. A working, reproducible POC with evidence is the appropriate engineering target; a design-only presentation would leave task-completion evidence missing.

Page 3 requests technical documentation, a presentation of at most ten minutes, source with README/GitHub link/deployment instructions/test cases, a security assessment with permission tiers and known risks, and execution evidence. The separate demo-video entry says optional and at most five minutes, while the non-on-chain execution-evidence entry explicitly includes sandbox logs and a demo video. Prepare the video to satisfy both rather than relying on the word optional. Use English narration/captions. The PDF states 20 October 2026 23:59 Beijing time; the corresponding Thailand time is 22:59. Check any organizer updates separately.

## Submission inventory

| Item | Current location / remaining action |
| --- | --- |
| Technical document | `Pocket_Pal_Technical_Documentation_v2.docx`; manually edited authoritative file |
| Security report | `Pocket_Pal_Security_Self_Assessment.docx`; team review draft with implemented/proposed distinctions |
| Source and tests | Backend, web, Android source, migrations, test files and committed dependency lockfiles |
| Local deployment | Root README; `android/POCKETPAL_GALLERY.md`; public hosting not claimed |
| Evidence index | `docs/design/06-acceptance-and-traceability.md`; evidence folders retain original status/limitations |
| Presentation | Team must provide/confirm final English deck and ten-minute timing |
| Video | Team must record, review for private information and provide accessible submission link; at most five minutes |
| Repository link/revision | Team must confirm judge access and exact final commit after manually running Git |
| IP/provenance | Team must confirm permission for contributed UI/assets and select a repository license; font OFL is retained |

Do not submit original private financial images as reproducibility fixtures. Use the synthetic fixtures for public replay. The rules supplied here ask for a GitHub repository link, not explicitly a public repository; private access must still allow the judges to review it under the submission portal's instructions.

## Representative evidence, with limits

- `20261017T012325Z-conversation-gallery-backend`: 300 passes, two known reference expected failures; fake/scripted provider coverage.
- `20261016T122231Z-reference-contract-regressions`: known alternate-reference/collision gaps reproduced, not fixed.
- `20261017T012328Z-conversation-browser`: mocked conversation UI checks.
- `20261017T020449Z-pocketpal-scanpolicy-v2-cloud`: eight synthetic-string filter-policy tests, not an image FP/FN benchmark.
- `20261017T040000Z-pocketpal-gallery-dated-scan-owner`: owner-reported physical scan; do not promote it to per-slip accuracy evidence.

After recording, add a separate sanitized demo record identifying code revision, client version, fake/real provider, environment, scenario, actual outcomes and any cuts/time compression. Do not rewrite historical evidence or include keys, sessions, bank identifiers or private chat transcripts.

## Repository hygiene before push

Keep source, all ordered migrations, unit/integration tests, synthetic fixtures, lockfiles, Gradle wrapper, environment examples, current documents and genuine sanitized evidence. Historical failed/invalid evidence retains its NOTE.

Exclude `.env` and environment variants, real-slip/private-eval directories, runtime uploads/databases, `.sync`, dependency/build caches, APK signing keys, Word `~$` lock files and unreviewed recordings. The initial technical draft remains historical; the root README points judges to v2. Do not delete historical material merely to hide limitations.

The 18 October review did not run any Git commands and therefore cannot certify tracked files, staging, commit history or remote contents. The owner must inspect those with Git, scan the resulting submission for secrets/personal data, and confirm repository access. Ignore rules do not remove already tracked content. If a secret is found in history, revoke/rotate it and handle history cleanup deliberately before publication; do not just add an ignore rule.

## Chat-focused demo: target 4 minutes 30 seconds

Use one fictional/synthetic scenario consistently. Start with a newly created account on the refreshed gallery profile. Enter a clearly labeled balance snapshot and next-income date, and grant processing/auto-import/history consent explicitly. Explain the snapshot date: importing earlier historical transactions is not equivalent to subtracting them again from a current balance. Record known inputs before testing, and compare tool results rather than inventing expected values.

| Time | Show | Suggested question / observation |
| --- | --- | --- |
| 0:00–0:25 | Pain point and current data scope | Financial images are scattered; the user wants an actionable plan, not another manual spreadsheet. Label POC and synthetic demo account. |
| 0:25–0:55 | One synthetic slip imported; Activity and category | Show actual extraction/import outcome, then the category. If processing is time-compressed, label the cut. |
| 0:55–1:35 | Grounded overview | “How much can I safely spend until my next income, and which commitments are reserved?” Answer should name the period and data limitations. |
| 1:35–2:15 | What-if reasoning | “Can I spend 800 baht on headphones today? Show the impact on my daily allowance.” Simulation must not create an expense. |
| 2:15–2:55 | Action with approval | “Propose moving 200 baht from Shopping to Food.” Show the pending card, approve explicitly, then verify pockets. Use an amount the scenario can fund. |
| 2:55–3:35 | Follow-up and changed facts | With memory enabled: “What changed after that?” The agent must refresh current facts and distinguish a proposal from an applied change. |
| 3:35–4:05 | Honest limitation | Ask for a historical trend with insufficient history. The assistant should explain the limit and offer a supported next step. |
| 4:05–4:30 | Security and implementation | Show that asking the model to approve cannot bypass the human card. State T0–T2, deterministic calculations, known risks and source availability. |

Do not claim that this fixed demo validates arbitrary prompts. Include at least one genuinely unseen question in rehearsal and retain its actual outcome. Pause gallery scanning while recording a curated scenario so background imports do not silently change its balances. No payment is executed by Pocket Pal.

## Last-night change boundary

Prefer improved temporal grounding, precomputed/displayed financial facts, explicit missing-data handling and regression evidence. Avoid a new RAG stack, multi-agent architecture, database redesign or permission relaxation before the submission. See `CLAUDE_CHAT_POLISH_PROMPT.md`. Any late code change must be reflected in evidence and the report's actual implementation boundary.

## Latest publication review

See [PUBLIC_RELEASE_CHECKLIST.md](PUBLIC_RELEASE_CHECKLIST.md) for inclusion/exclusion decisions and owner-run Git checks. Latest full offline suite: `20261018T163840Z-provider-neutral-contract-final` (329 passed, two known strict reference xfails). Earlier representative evidence remains historical. No new live-provider or clean-checkout verification was performed during publication preparation.
