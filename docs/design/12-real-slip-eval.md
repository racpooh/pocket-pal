# 12 — Real-slip OCR evaluation (round 1: 5 images) and local environment isolation

Status 16 Oct 2026: harness built and self-tested on synthetic slips; round 1 **prepared, not run**. No real image has
been sent anywhere. The model call waits for the owner's explicit approval (sending the 5 images to Anthropic, budget).

## 1. Environment isolation (follow-up to the 16 Oct device-DB reset)

Problem found: every local script used **one** pgserver cluster and the cluster-wide roles `finassist_app` /
`finassist_worker`; each script rotated their passwords. So pytest or an E2E run could break a running phone server even
without `--reset`. The E2E also defaulted to port 8000 (the phone's) — with the phone server up, it could have run
against the phone's database. Uploads of all profiles shared `backend/var/dev_uploads` in the repo folder.

Fix (`backend/scripts/local_envs.py`): four profiles, each with its own cluster under `FINASSIST_PGDATA_ROOT`
(default `~/.cache/finassist`), database, login roles, storage and port:

| profile | user | cluster | database | roles | storage | port |
|---|---|---|---|---|---|---|
| dev | phone (owner) | pgdata-dev | finassist_dev | finassist_{app,worker}_dev | dev-uploads | 8000 |
| e2e | `cp3a_e2e.py` | pgdata-e2e | finassist_e2e | finassist_{app,worker}_e2e | e2e-uploads | 8001 |
| test | pytest (`local_pg.py`) | pgdata-test | finassist_test | finassist_app/worker (conftest) | temp | — |
| realeval | real-slip replay | pgdata-realeval | finassist_realeval_test | finassist_app/worker (conftest) | temp, deleted after | — |

Refusals (fail closed): `dev_server.py` without `--profile`; legacy `FINASSIST_PGDATA`; a port in use; a port of another
profile; a `--database-url` whose database is not the profile's; a cluster marked for another profile; `cp3a_e2e.py` on
port 8000 or on a port already in use; the E2E continuing when the healthy server is not the one it started.
Per-profile worker roles are members of `finassist_worker` (the job-claim policy applies to members).

Evidence (owner's Linux ARM64 VM, PG 18.4): `20261016T082236Z-env-isolation-device-pg18-arm64` — 15/15 checks: the
refusals above; with the dev server running, pytest (test profile) and a full `cp3a_e2e.py` (`--reset`, 27/27 + 27/27,
`20261016T082245Z-env-isolation-device-pg18-arm64-e2e`) ran; afterwards the dev account's token, records, and new
imports (fresh API and worker connections) still worked. Invalid first attempt kept with NOTE.md
(`20261016T082026Z-…`: the VM may not delete inside the repo mount → storage moved out of the repo).
Not shown: a negative control with the old code (the shared-role failure is reasoned from the code, not reproduced).

Owner impact: the phone's data now lives in the new `pgdata-dev` cluster; start once with
`dev_server.py --profile dev --provider fake --reset`. The old cluster `~/.cache/finassist/pgdata` and
`backend/var/dev_uploads/` (synthetic only, gitignored) can be deleted by the owner.

Also fixed: `record_evidence.py` and `eval_extraction.py` ran `git rev-parse` / `git status` themselves. Under the
owner's no-git rule they now record "not queried" plus the content hash. Earlier manifests contain git fields produced
that way (disclosed here, not rewritten).

## 2. Real-slip evaluation protocol (`backend/scripts/eval_real_slips.py`)

Privacy (enforced in code): images stay in `backend/fixtures/real/` (gitignored, checked before reading); every
identifying output — file names, model output, names, account and reference numbers, labels, per-image results —
only under `eval/private/real-<round>/` (gitignored). Images are never staged to the cloud workspace or viewed by
Claude. Public evidence = aggregate counts only; the writer refuses a manifest containing an id, a file name or Thai text.
The only external recipient is the extraction provider, in `run`, with `--confirm-send-to-anthropic`.

Ground truth: the owner's labels from the images (`labels.csv`: doc_type, amount, Gregorian date, time, direction,
counterparty, status, optional reference, same_payment_as). `run` refuses until the labels are complete and records
their sha256 **before** the first call; `score` reports if they changed afterwards. Model output is never truth.

Round 1: 5 images sampled at random (seed 20261016) from 31 unique; none carries GPS metadata; sent as the exact bytes
the upload API would receive. Caps hard-coded: $0.10, 5 requests, 0 retries, a per-round private usage ledger (re-runs of
the round share the budget), Models-API access check first, stop on the first non-retryable error. Worst-case estimate
at the configured Haiku price: $0.0023 (so the $0.10 cap is a ceiling, not an expectation). Each call is also added to
`evidence/usage_ledger.jsonl` as one aggregate line (no ids or content).

Scoring (`score`, offline, $0, repeatable) — three results, reported separately:
- **(a) extraction**: per field, model reading vs label (amount/date/time through the production parsers; counterparty
  normalised, plus a "contains" variant for masked names; reference only if labelled).
- **(b) validation / review routing**: production `validate()` on the recorded output (capture date from EXIF);
  auto-import with a wrong critical field (= unsafe) vs caught by review vs unnecessary review.
- **(c) pipeline + dedup**: recorded outputs through the real worker pipeline in the `realeval` database (RLS roles);
  payments counted once / held in review / double counted / wrong value / missed silently; exact re-upload; one
  SIMULATED re-encoded copy (labelled).
On errors: fix logic, re-run `score` on the same recorded outputs; a new model call only after that, within the cap.

Harness self-test (synthetic, fabricated outputs with one planted amount error, $0):
`20261016T083101Z-real-slip-harness-selftest` — PASS 10/10 (error found on exactly the planted image; routing reports it
as auto-import with a wrong critical field; receipt+slip pair and duplicates counted once; bill created).

Limits: 5 images give counts, not rates; one owner's banks only; nothing here is a competition score.
