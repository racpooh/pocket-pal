# NOTE — r1 baseline score (extraction + routing only)
Run by Codex with `--skip-pipeline` on extraction run 20261016T110123Z (5 real slips, owner-approved). Code before the
date-parser fix (extraction_validation.py sha256 aa5ad466…). Labels = frozen v1. Aggregate only.
Known label defects in v1 (private log LABEL-ISSUES-v1.md): Thai text lost at entry; bank_ref column used for the app
name; one time typo. So counterparty and bank_ref counts here are NOT model accuracy. See docs/design/12 §4.
