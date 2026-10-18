# Submission preflight and demo refresh

The owner authorized clearing the demo backend. Only the active gallery database and its upload storage were reset. Users, owner data and jobs are zero; ten shared categories are migration seed data. Dev/test/e2e/realeval, source photos, private evaluation inputs and usage ledger were preserved. No paid calls or new application tests.

Initial post-reset verification incorrectly expected shared categories to be empty and stopped before restart; corrected verification retained the ten required seeded categories. The first restart used a temporary uv interpreter that was cleaned up when its wrapper exited; it was replaced with a persistent direct uv server session without another reset. Final health and web-connect checks succeeded. Phone app/cache/scan state remains uncleared because ADB is unauthorized; no phone data was deleted.

Workspace scan checks three high-confidence secret patterns in selected text paths only. It does not certify personal-data absence, binaries, staged changes, Git history or remote contents. No Git commands were executed. Documentation commands were source-reviewed, not freshly replayed in a clean checkout. Known application failures remain unchanged.
