# Pocket Pal — Personal Finance Assistant

FinTechathon 2026 International Track, Topic A. Pocket Pal turns user-consented financial images into reviewable records and uses a bounded conversational agent to explain spending, simulate purchases and propose budget changes. The user approves changes; the system does not execute real payments.

**Submission snapshot: 19 October 2026. Working POC, not a production-ready financial service.** The active UI is `web/`, hosted in a browser or the `android/pocketpal` WebView APK. The initial physical-device validation used a Galaxy S22 Ultra (Android 14). Browser portability does not imply that Android gallery automation is implemented on other operating systems.

## Start here

- [Reviewer guide and submission checklist](docs/submission/REVIEWER_GUIDE.md)
- [Technical specification](docs/submission/Pocket_Pal_Technical_Documentation_v2.docx)
- [Security self-assessment](docs/submission/Pocket_Pal_Security_Self_Assessment.docx)
- [Requirement and evidence traceability](docs/design/06-acceptance-and-traceability.md)
- [Current engineering handoff](HANDOFF.md)

The documents distinguish implemented controls, automated tests with fake/scripted models, small real-model pilots, and owner-reported device observations. Test counts are not an accuracy or competition score.

## Implemented and remaining scope

Implemented paths include session authentication and owner isolation; consent; image upload, extraction, review and ledger import; integer-satang financial calculations; spending and pockets; affordability and goal simulations; proposal cards with explicit approval; and consented conversation history. Android adds a consented last-30-day gallery candidate scan with local filtering and bounded upload attempts.

Material limitations remain: ambiguous transaction reference types have two strict expected-failure regressions; gallery filter precision/recall is not established; undated images are skipped automatically; extended native lifecycle testing is incomplete; generated narrative fidelity is not guaranteed; public deployment/security hardening is not complete. See the security report and traceability rather than assuming feature-wide acceptance from a successful demo.

## Repository map

| Path | Purpose |
| --- | --- |
| `backend/src/finassist/domain/` | Deterministic money/ledger/financial logic; stdlib only |
| `backend/src/finassist/services/` | Owner-scoped business workflows, agent tools, proposals and imports |
| `backend/src/finassist/api/` | FastAPI endpoints and error contracts |
| `backend/db/migrations/` | Ordered schema, RLS, lease and transfer-integrity migrations |
| `backend/tests/` | Unit, API, database and integration tests |
| `backend/fixtures/synthetic/` | Synthetic images and test variants; no private slips |
| `web/` | API-connected Pocket Pal Next.js interface and server-side session proxy |
| `android/pocketpal/` | Active WebView host, native bridge and gallery scanner |
| `android/app/`, `android/core/` | Earlier Compose client and its reusable/tested core; distinct client lineage |
| `docs/design/`, `docs/submission/` | Decisions, acceptance matrix and reviewer documents |
| `evidence/runs/` | Historical run evidence; failed/invalid runs retain explanatory notes |
| `deploy/` | Deployment design/legacy scaffolding; not a verified production recipe |

## Local reviewer setup

Use Python >=3.12 with uv, Node.js/npm, and a platform capable of running local Postgres. Android additionally needs JDK 17+, Android SDK 35 and device tools. Use the committed backend and web lockfiles. The optional local Postgres bootstrap uses `pixeltable-pgserver` through `uv --with`; that additional package is not pinned by `backend/uv.lock`.

From a fresh checkout, create a local configuration only if it does not exist:

```bash
test -e .env || cp .env.example .env
cd backend
uv sync --locked
uv run --with pixeltable-pgserver python scripts/dev_server.py --profile gallery --provider fake
```

This applies **all** numbered migrations on an empty profile and creates restricted per-profile runtime roles. It binds to loopback port 8002. Existing profile data is preserved. Do not add `--reset` unless deliberately erasing that profile's accounts, records and uploaded-image storage.

In a second terminal, from the repository root:

```bash
cd web
npm ci
npm run build
FINASSIST_BACKEND_URL=http://127.0.0.1:8002 npm run start -- --hostname 127.0.0.1 --port 3002
```

Open `http://127.0.0.1:3002/connect`. Create a test account with a password of at least ten characters; there is no seeded login. Grant the desired consent and configure balance/income before asking budget questions. Use images from `backend/fixtures/synthetic/slips/` in fake mode. Review fixtures before selecting a consent date window.

**Fake mode is explicitly marked TEST MODE.** Extraction works only for registered synthetic fixtures; other images fail honestly. Live conversational responses require the real provider: fake mode returns `MODEL_UNAVAILABLE` for chat rather than fabricating a demonstration response.

### Real-model demonstration

Set `FINASSIST_MODEL_API_KEY` in the repository-root `.env` locally. Confirm that the extraction/chat model identifiers in `.env.example` are available to your provider account; the defaults reflect this project's recorded runs and are not a promise of provider availability. Stop the fake backend, then run:

```bash
cd backend
uv run --with pixeltable-pgserver python scripts/dev_server.py --profile gallery --provider anthropic
```

This uses the same gallery data without resetting it. Calls incur provider charges. Use synthetic data for shareable recordings, obtain consent before sending personal data, and monitor provider billing. Local evaluation budgets and gallery attempt caps are **not** a global hard cap on live chat spending. Never expose the API key through a `NEXT_PUBLIC_` variable.

### Android demonstration

See [APK/gallery instructions](android/POCKETPAL_GALLERY.md). The active module is `:pocketpal`, not the earlier `:app` Compose client. Its debug origin is loopback port 3002; forward that port over USB. The Mac, backend, web service and USB connection must remain running. Gallery automation is Android-specific; ordinary browser use supports manual upload.

## Tests and evidence

From `backend/`:

```bash
uv run pytest tests/unit
```

For the full suite against the isolated, disposable test profile:

```bash
TEST_DATABASE_URL="$(uv run --with pixeltable-pgserver python scripts/local_pg.py --profile test)" uv run python scripts/record_evidence.py --slug reviewer-backend
```

Database tests recreate the target schema. Use the test profile only, never the gallery/dev profile. Review the resulting manifest, including skips and expected failures; known reference gaps must not be counted as passing controls.

Web compilation and Android policy tests:

```bash
cd web
npm ci
npm run build
```

```bash
cd android
./gradlew :pocketpal:testDebugUnitTest :pocketpal:assembleDebug
```

Run each block from the repository root as indicated. Browser smoke scripts have local runtime assumptions; consult `web/README.md` before adapting them. Compilation or policy tests alone do not establish real-device acceptance. These instructions were source-checked for this submission update; a new clean-checkout replay has not been performed.

## Deployment and data boundaries

The documented demo is a local deployment. `deploy/docker-compose.yml` is older scaffolding that initializes only migration 0001 and is **not** the current complete setup. Do not treat it or the GCP design as a verified hosted release. A public release needs HTTPS, restricted roles, protected storage, quotas, operational controls and the release gates in the security report.

Exclude secrets, personal slips, private labels, runtime databases/uploads, caches, build products and private demo videos from Git. `.gitignore` protects new untracked files only; it cannot remove already tracked files or prior commits. Inspect the submission history before publishing. Retain genuine synthetic fixtures and sanitized evidence, including invalid-run notes. Do not remove known failures to improve the appearance of results.

Third-party code/assets retain their licenses. Team ownership, permission to redistribute the contributed Pocket Pal UI, and the repository license must be confirmed before publication; no license is silently selected here. The bundled Noto Sans Thai font license is at `backend/tools/fonts/OFL.txt`.

Submissions and reviewer-facing documents are in English.

## Public submission preparation

Start with the [public release checklist](docs/submission/PUBLIC_RELEASE_CHECKLIST.md). See [security reporting](SECURITY.md) and [contribution rules](CONTRIBUTING.md). Run `python3 tools/public_preflight.py` for a redacted, selected-text working-tree check; tracked files and history require separate owner review.

Latest full offline backend regression: `20261018T163840Z-provider-neutral-contract-final` — **329 passed, two known strict reference xfails**. Other-provider compatibility, a post-refactor live smoke test and a clean-checkout replay remain unverified.
