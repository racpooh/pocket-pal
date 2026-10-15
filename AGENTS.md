# Rules for AI collaborators (Claude, Codex)

Roles: Claude = co-designer and main implementer. Codex = architecture/security co-designer and reviewer. The human team decides product scope and accepts deliverables.

1. **Authority order**: `docs/We go shenzhen case (1).docx` (product) > competition PDF (rules/submission) > approved items in `docs/design/` > proposals. Files in `docs/` root are originals: never edit, rename or move them.
2. **Scope**: Features 1–10 required, 11 optional, LINE out, no real money movement. Do not drop or weaken a requirement to make a checkpoint look complete; report it as not done.
3. **Disagree on the merits**. Neither agent's proposal is approved by default. Record disagreements in the relevant design doc with the trade-off.
4. **Evidence**: never claim a test passed without an evidence run in `evidence/runs/`. Mark mocks/fakes explicitly. Keep `not run / failed / env-limited / passed` distinct. Test pass rate is not a competition score.
5. **Data**: no real slips or personal data in Git, fixtures, prompts or evidence. Do not send personal images to external services without the owner's explicit consent (decision D7).
6. **Layering**: `backend/src/finassist/domain/` imports only the stdlib. HTTP, DB, model provider and storage stay outside it.
7. **Money**: integer satang only; no floats in money paths. Every percentage carries its base label.
8. **Security**: `owner_id` comes from the session only. The model can read, simulate and propose (T0–T2); it never commits, deletes, changes consent or moves money.
9. **Handoff**: end each checkpoint by updating `HANDOFF.md` (TL;DR first) and the status column in `docs/design/06-acceptance-and-traceability.md`.
10. **Language**: code, docs and submission material in English.
