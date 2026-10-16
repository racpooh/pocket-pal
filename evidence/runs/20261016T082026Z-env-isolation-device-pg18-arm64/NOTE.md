# NOTE — invalid run (kept, not deleted)

Stopped at step 2: `dev_server.py --profile dev --reset` failed while clearing its upload storage
(`backend/var/dev_uploads`): the owner's Cowork VM may not delete files inside the mounted repo folder
(`PermissionError: Operation not permitted`). No check after "legacy FINASSIST_PGDATA refused" ran; there is no manifest.
Fix: the server profiles' upload storage moved out of the repo, next to their clusters under FINASSIST_PGDATA_ROOT
(`dev-uploads`, `e2e-uploads`). Re-run: the next `*-env-isolation-device-pg18-arm64` run.
