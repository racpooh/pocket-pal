# Pocket Pal web integration

The original Pocket Pal Next.js UI is copied into this directory; the source repository at `../pocket-pal` is unchanged. The live pages use FinAssist APIs instead of demo records. This is a browser client, not the native Android APK or the background album scanner.

## Historical browser-only profile (dev, ports 8000/3000)

For the current reviewer setup and active APK, use the [root quickstart](../README.md): gallery profile on backend 8002 and web 3002. The commands below retain the earlier browser-only dev profile; do not mix its ports with the APK origin.

### Run the earlier browser profile

Restart the existing backend process with its original environment and command (`scripts/dev_server.py --profile dev --provider anthropic`) to load the latest plan/logging/review fixes, then keep it on loopback port 8000. Do not reset it. The server-side backend settings load the existing Anthropic key (`FINASSIST_MODEL_API_KEY`). Never put that key in a NEXT_PUBLIC variable or browser settings. The web only needs the backend origin.

```bash
cd ~/Development/case/shenzen/web
npm ci
npm run build
FINASSIST_BACKEND_URL=http://127.0.0.1:8000 npm run start -- --hostname 127.0.0.1 --port 3000
```

In another terminal:

```bash
~/Library/Android/sdk/platform-tools/adb reverse tcp:3000 tcp:3000
```

Open `http://localhost:3000/connect` in Chrome on the S22. Sign in using the same account as the backend/Android app, or create a separate demo account. There is no hardcoded email/password. Choose photo-processing consent, a starting date, and optional auto-import. Existing consent remains effective unless revoked in Settings. For a new account, open setup and enter balance/income, then review and approve the proposed pocket plan.

An existing server on port 3000 must be stopped before starting another. The USB connection and both server processes must stay running. Port 3012/8012 is used by isolated synthetic tests, not the owner's demo.

## Normal recording flow

1. Chat: attach one JPG/PNG slip (maximum 8 MiB), explicitly confirm the selected undated photo, then Upload photo.
2. Wait for processing. A valid import displays the recorded payee, amount, date, and status. An uncertain result opens Review; no success is fabricated.
3. Activity: inspect the imported record. Set its category if unclassified. Choosing the same image again must not add a second expense.
4. Pockets: see the current balance, daily guide, and allocations from the server. A current daily guide already accounts for recorded spending; it is not a fixed opening-day allowance.
5. Chat: ask a concrete question, e.g. “How much can I spend until my next income?” or “Show a proposal to move 100 baht from Shopping to Food.” A proposal is only applied after the human presses Approve.
6. Use synthetic records for shareable clips. Real slips and conversations remain private; do not add the recording to public evidence.

Real OCR/chat requests use the backend provider and incur API charges. This web client does not set a new billing cap or treat the owner's $5 balance as authorization to spend it. Fake backend mode shows TEST MODE and returns an honest unavailable error for chat.

## Security and test scope

A Next server proxy stores the backend session in an HttpOnly, SameSite=Strict cookie. State-changing requests require matching Origin and Host. API keys and bearer tokens are not returned in browser JSON. Backend RLS and ownership checks remain authoritative. The loopback HTTP setup is for USB development; deployment requires HTTPS and further hardening.

`python ../web/scripts/smoke.py` (use the backend Python environment, from repo root as `backend/.venv/bin/python web/scripts/smoke.py`) targets only isolated test ports 3012/8012 and refuses a non-fake backend. `scripts/browser-smoke.cjs` currently uses the Codex bundled Playwright and macOS Chrome paths; adjust those paths on another machine. Evidence and limitations are in `docs/design/15-web-integration.md`.

Use npm and `package-lock.json`; the copied pnpm lock is retained as `pnpm-lock.original.yaml` for source provenance, not for installation.
