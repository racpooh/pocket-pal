# Security policy

Pocket Pal is a competition proof of concept. It is not approved for production financial data or real money movement. No supported production release or response-time SLA is established.

## Reporting a vulnerability

Do not publish API keys, personal slips, account identifiers, exploit payloads containing personal data, or production logs in a public issue. Contact the Pocket Pal Project Team through the private competition/team channel. If GitHub displays a **Report a vulnerability** option, that private reporting channel may also be used; its availability must be configured by the repository owner. No dedicated public security mailbox is currently designated.

Provide the affected component/revision, a minimal synthetic reproduction, expected versus observed behavior, and impact. Use disposable accounts and isolated test databases. Do not test against another person's account or incur provider charges without permission.

## Security boundaries and known limitations

- Session-derived ownership and database isolation remain authoritative; model output is untrusted.
- The assistant can read, simulate and propose (T0–T2). Human approval is required for authorized application changes. No real money transfers occur.
- Photo permission, processing consent, auto-import consent and conversation-memory consent are distinct controls.
- Provider-neutral interfaces are implemented; external adapters beyond the implemented provider are not qualified. No-training admission and deployment network hardening are proposed controls, not guarantees enforced by the interface.
- Local HTTP/USB demonstration settings are not a production deployment architecture.
- Known risks, permission tiers and evidence boundaries are documented in the [Security Self-Assessment](docs/submission/Pocket_Pal_Security_Self_Assessment.docx) and [acceptance record](docs/design/06-acceptance-and-traceability.md).

A discovered exposed credential must be revoked/rotated. Removing a file or adding an ignore rule does not remove earlier commits or copies. The owner must assess history and downstream exposure before making the repository public.
