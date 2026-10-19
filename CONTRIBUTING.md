# Contributing

This repository is a competition POC maintained by the Pocket Pal Project Team. Discuss scope with the team before making substantial changes. Contribution and redistribution rights remain subject to team confirmation; this file does not grant an open-source license.

## Development rules

Read [AGENTS.md](AGENTS.md), [HANDOFF.md](HANDOFF.md), and the relevant design decision before editing. Preserve original files directly under `docs/`. Keep code and documentation in English.

- Keep domain logic independent of HTTP, database and provider SDKs.
- Use integer satang for money and name the base of every percentage.
- Derive ownership from the authenticated session, never model/user-supplied ownership fields.
- Preserve human approval, consent, deduplication and freshness checks.
- Use synthetic fixtures and disposable `test`/`e2e` profiles. Never reset a demo or personal database as part of a test.
- Never commit secrets, personal slips, private labels, personal conversations, local databases, signing material or recordings with personal data.
- Keep failed/invalid evidence and explain limitations. Do not equate mocked tests with live-provider validation.

## Verification and handoff

Follow the [root README](README.md) for setup and tests. Add focused regression coverage for behavioral changes. Record test commands, environment, results, and mock/provider scope under `evidence/runs/`. Update acceptance status and HANDOFF when completing a checkpoint. The latest technical DOCX includes manual edits: do not overwrite it using historical generators.

Before publication, follow the [public release checklist](docs/submission/PUBLIC_RELEASE_CHECKLIST.md). The working-tree scanner is only a first pass, not a substitute for reviewing tracked files, history, binaries and provenance.
