# Public repository release checklist

Prepared 19 October 2026. Publication is an owner action. Working-tree review does not certify staging, commit history, remote contents, binary metadata or all personal data.

## Include

| Material | Purpose |
|---|---|
| `backend/src`, migrations, scripts, tests, synthetic fixtures | Inspectable implementation and reproducible regression coverage |
| `web/` source, `package-lock.json`; Android source and Gradle wrapper | Active UI, native gallery integration and reproducible dependency resolution |
| Root README, `.env.example`, AGENTS, HANDOFF, CONTRIBUTING and SECURITY | Setup, scope, ownership of decisions, security reporting and handoff |
| `docs/design/`, current submission DOCX and reviewer guide | Architecture, security, acceptance boundaries and current deliverables |
| Sanitized `evidence/runs/`, including failed runs and notes | Traceable claims; retain failures and mock labels |
| Bundled font OFL and existing third-party notices | Asset attribution and license provenance |

Keep the legacy Compose app and historical drafts clearly labeled; do not remove them just to make acceptance appear complete. Use npm's lockfile; `pnpm-lock.original.yaml` is historical provenance. `deploy/docker-compose.yml` is a legacy partial recipe, not the current deployment procedure.

## Exclude from public contents and history

- All actual `.env` files, tokens, credentials, private keys and signing stores.
- `backend/fixtures/real/`, all `private/` directories, private labels, extracted personal data and real-image exports.
- `backend/var/`, local databases, uploads, `.sync/`, caches and dependency directories.
- APK/AAB/build outputs, IDE files, Word lock files, and personal demo recordings.

Ignore rules prevent ordinary addition of untracked files; they do not remove tracked or historical files. Inspect archived/binary files and document properties separately. Images in evidence are intended to be synthetic: visually review those selected for publication, including failure screenshots.

## Owner decisions before making public

1. Confirm permission to redistribute the contributed Pocket Pal UI and all assets. Select a repository license only after rights are agreed; no license has been invented by the assistants.
2. Confirm whether the product brief and competition PDF directly under `docs/` may be redistributed. They are immutable local originals, not assumed public-domain documents. If permission is absent, exclude them from the published repository while preserving local originals and explain judge access separately.
3. Review public logs and document metadata for identities, local paths and personal material. Synthetic test accounts may be retained only when clearly synthetic and not usable against a live deployment.
4. Inspect tracked/staged files and full history. If a real credential was ever committed, rotate it and plan history cleanup before publication.
5. Confirm the final deck/demo link and judging access. Public source does not make the local-only demo publicly hosted.

## Local working-tree check

Run from the repository root:

```bash
python3 tools/public_preflight.py
```

The script uses only the standard library and never invokes Git. It checks selected text for a small set of credential patterns and flags selected private/generated artifacts. It deliberately skips private/runtime folders, binaries and environment secrets. An empty finding list means only that these checks found nothing; it is not a secret-scanner certification or penetration test.

## Owner-run Git inspection

The following commands are read-only. Run them yourself; assistants have not executed them. Empty output is expected for the second and third commands. A nonempty result requires review before publication.

```bash
cd ~/Development/case/shenzen
git status --short
git ls-files -- .env ':(glob)**/.env' ':(glob)**/.env.*' ':(glob)**/private/**' backend/fixtures/real backend/var .sync
git ls-files -- ':(glob)**/*.pem' ':(glob)**/*.key' ':(glob)**/*.jks' ':(glob)**/*.keystore' ':(glob)**/*.apk' ':(glob)**/node_modules/**'
git diff --cached --name-status
git diff --cached --check
git log --all --format= --name-only -- .env backend/fixtures/real eval/private backend/var .sync
```

`.env.example` is an intentional template if it appears in a broad environment-file query. The history command covers only selected paths, not all possible credential locations. Perform a full-history secret scan locally with your approved scanner as well; do not upload the repository to an unknown scanning service.

Stage explicitly reviewed paths, inspect the complete staged diff, and commit before pushing. Avoid `git add -A` for this release. Do not use automatic destructive history rewriting or remove originals to satisfy this checklist.

## Evidence and remaining verification

Latest full offline backend evidence: `20261018T163840Z-provider-neutral-contract-final`, 329 passed and two known strict reference xfails. Live Anthropic evidence predates the neutral-interface refactor. No new live test, clean-checkout replay or production deployment has been performed in this publication-preparation pass.
