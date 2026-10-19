# Pocket Pal submission review documents

Current English deliverables are `Pocket_Pal_Technical_Documentation_v2.docx` and `Pocket_Pal_Security_Self_Assessment.docx`. Author: Pocket Pal Project Team. These are team-review documents, not production or compliance acceptance. Original documents in the docs root are immutable sources.

## Technical specification

The v2 DOCX contains manual owner edits, professional equations, code formatting and source-checked orchestration sections 7.4–7.6. It is authoritative for the current revision. The older Markdown and `build_technical_v2.py` do not contain every subsequent edit: do not rebuild the current DOCX from them. Pagination depends on the owner's layout changes.

## Security self assessment

The existing security DOCX was updated on 18 October 2026; the latest rendered revision has 21 pages. Its current source is `Pocket_Pal_Security_Self_Assessment.md`. The dedicated `build_security_report.py` reads the current technical DOCX as a formatting template and writes only the security DOCX. It does not modify the technical file. Use the configured Codex Python runtime with python-docx, then render and inspect the output. QA intermediates are under `.sync/security-report-qa/`, not submission artifacts. If the owner subsequently edits the security DOCX manually, reconcile those changes before rebuilding.

The report covers permission-tier implementation, threats, privacy, AI/financial integrity, 18 open risks, evidence limits and proposed hardening. No new application tests were run for authoring. Existing tests, fake/scripted providers and owner-reported device observations are distinguished. No personal images or transaction-level personal data are included.

## Legacy generator warning

`build_documents.py` is retained for historical provenance only. It embeds the earlier drafts and would overwrite the expanded security report. Do not use it to regenerate current deliverables.

The owner accepted the observed S22 scan as sufficient to proceed with POC documentation and deferred latency optimization. This does not establish complete CP3b acceptance or per-slip accuracy. Final team review and version-bound demonstration evidence remain required.

## Final Chat review update — 18 October 2026

Both current DOCX files were edited in place after saving the open Word document. The technical DOCX retains its user formatting, native equations and header. Do not rebuild it from the historical technical Markdown/builder. The security Markdown has been synchronized to the current security document text. Final Chat regression evidence: `20261018T125457Z-chat-final-review-full` (326 passes, two existing strict reference xfails); real-model pilot `20261018T124452Z-chat-eval-live` is separately scoped and predates the final review guard/wording changes. Latest reports include score denominators and the post-hoc narrative heuristic correction. A live mobile restart/smoke check remains pending.

### Provider and deployment-security update — 18 October 2026

The existing Technical v2 DOCX now contains sections 3.5 and 9.13 for neutral provider contracts and enterprise admission. Security sections 7.2.1 and 11.4–11.7 cover no-training commitments, network segmentation, approved routing, ingress and orchestration controls with explicit implementation/evidence limits. Offline adapter evidence is 329 passes plus two known reference xfails; no post-refactor live compatibility is claimed. Security Markdown is synchronized; Technical DOCX remains the authoritative manually formatted artifact.
