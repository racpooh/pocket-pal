"""Local backend for the Android client (CP3). Real FastAPI app + real Postgres + embedded worker, RLS roles.

  # fake extraction preloaded with the SYNTHETIC slip fixtures (no model calls, no cost):
  uv run --with pixeltable-pgserver python scripts/dev_server.py --provider fake --reset
  # then, with the phone on USB:   adb reverse tcp:8000 tcp:8000   (the app's debug build uses http://127.0.0.1:8000)

Binds 127.0.0.1 only. Uses database `finassist_dev` (refuses any other name for --reset). The fake provider is
refused outside FINASSIST_ENV=dev|test by Settings (fail closed); /v1/health reports test_mode=true so the client
shows a TEST MODE banner. Unknown (non-fixture) images fail extraction with a provider error → extract_failed,
which is the honest result for a fake extractor.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "src"))
sys.path.insert(0, str(BACKEND))

DEV_DB = "finassist_dev"


def _psql_retry(srv, sql: str, tries: int = 30) -> str:
    """pgserver can return before the server accepts connections on a cold start (seen in the owner's VM)."""
    import subprocess
    import time

    for i in range(tries):
        try:
            return srv.psql(sql)
        except subprocess.CalledProcessError:
            if i == tries - 1:
                raise
            time.sleep(1)
    raise RuntimeError("unreachable")


def _local_pg() -> str:
    import pixeltable_pgserver as pgserver
    from psycopg.conninfo import make_conninfo

    data = Path(os.environ.get("FINASSIST_PGDATA", Path.home() / ".cache" / "finassist" / "pgdata"))
    data.mkdir(parents=True, exist_ok=True)
    srv = pgserver.get_server(str(data), cleanup_mode=None)
    names = _psql_retry(srv, "select datname from pg_database;")
    if DEV_DB not in names:
        _psql_retry(srv, f"create database {DEV_DB};")
    return make_conninfo(srv.get_uri(), dbname=DEV_DB)


def _prepare(url: str, reset: bool) -> dict[str, str]:
    """Apply migrations (on --reset or an empty DB) and (re)create the two runtime roles with fresh random passwords."""
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    with psycopg.connect(url, autocommit=True) as c:
        name = c.execute("select current_database()").fetchone()[0]
        empty = c.execute("select to_regclass('public.app_user') is null").fetchone()[0]
        if reset or empty:
            if name != DEV_DB:
                raise SystemExit(f"refusing to reset database {name!r}; only {DEV_DB!r}")
            c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
            for f in sorted((BACKEND / "db" / "migrations").glob("*.sql")):
                c.execute(f.read_text(encoding="utf-8"))
        urls = {}
        for role in ("finassist_app", "finassist_worker"):
            pw = secrets.token_urlsafe(18)
            c.execute(f"""DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                          CREATE ROLE {role} LOGIN NOSUPERUSER NOBYPASSRLS; END IF; END $$;""")
            c.execute(f"ALTER ROLE {role} LOGIN PASSWORD '{pw}'")
            c.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
            c.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}")
            c.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}")
            d = conninfo_to_dict(url)
            d.update(user=role, password=pw)
            urls[role] = make_conninfo(**d)
    return urls


def _fixture_provider():
    from finassist.providers import FakeExtractionProvider
    from tests.integration.conftest import SLIPS, fields_from_gt, gt_rows

    p = FakeExtractionProvider()
    for r in gt_rows():
        f = SLIPS / r["file"]
        if f.exists():
            p.by_sha[hashlib.sha256(f.read_bytes()).hexdigest()] = fields_from_gt(r)
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["fake", "anthropic"], required=True, help="explicit; no default")
    ap.add_argument("--database-url", default=None, help="admin URL of a database named finassist_dev (default: local pgserver)")
    ap.add_argument("--reset", action="store_true", help=f"drop and re-create the {DEV_DB} schema")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()

    import uvicorn

    from finassist.api.app import create_app
    from finassist.settings import Settings

    url = a.database_url or _local_pg()
    urls = _prepare(url, a.reset)
    provider = _fixture_provider() if a.provider == "fake" else None
    settings = Settings(env="dev", model_provider=a.provider, database_url=urls["finassist_app"],
                        worker_database_url=urls["finassist_worker"], embedded_worker=True,
                        storage_dir=str(BACKEND / "var" / "dev_uploads"))
    app = create_app(settings, extraction_provider=provider)
    if a.provider == "fake":
        print("=" * 72 + f"\nTEST MODE: fake extraction with {len(provider.by_sha)} SYNTHETIC fixtures; no model calls.\n"
              "Non-fixture images will fail extraction (extract_failed).\n" + "=" * 72, flush=True)
    else:
        print("REAL MODEL PROVIDER: extraction calls are billed. CP3 rules: do not use this mode.", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
