# Extraction and classification evaluation

Protocol: `docs/design/06-acceptance-and-traceability.md §4` and `docs/design/04-import-and-classification.md`.

- `eval/private/` (gitignored): consented, redacted real samples and labels — only after decision D7.
- Synthetic sets will be committed under `eval/synthetic/` (CP2).
- Splits: by payee_key group (new-merchant condition) and chronological replay (seen-merchant condition). Thresholds tuned on dev only and frozen before the test run.
- Reports go to `evidence/runs/` with the model identifier, prompt/schema version, cost and latency.

Nothing has been evaluated yet.
