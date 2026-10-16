"""Start (or reuse) a throwaway local Postgres for tests without Docker, and print TEST_DATABASE_URL.

  uv run --with pixeltable-pgserver python scripts/local_pg.py                     # pytest  → finassist_test
  uv run --with pixeltable-pgserver python scripts/local_pg.py --profile realeval  # private real-slip replay

Each profile has its own cluster under FINASSIST_PGDATA_ROOT (default ~/.cache/finassist), outside the repo and synced
folders, separate from the phone's (`dev`) and the automated E2E (`e2e`) clusters — see scripts/local_envs.py. The
test suite rotates the shared role passwords `finassist_app` / `finassist_worker`; in its own cluster that cannot
affect a running dev or e2e server. Uses a unix socket.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from local_envs import PROFILES, local_admin_url  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--profile", choices=["test", "realeval"], default="test")
print(local_admin_url(PROFILES[ap.parse_args().profile]))
