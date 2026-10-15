"""Start (or reuse) a throwaway local Postgres for tests/demos without Docker, and print TEST_DATABASE_URL.

  uv run --with pixeltable-pgserver python scripts/local_pg.py
Data lives in ~/.cache/finassist/pgdata (override with FINASSIST_PGDATA), outside the repo and outside synced folders.
Uses a unix socket.
"""

from __future__ import annotations

import os
from pathlib import Path

import pixeltable_pgserver as pgserver

DATA = Path(os.environ.get("FINASSIST_PGDATA", Path.home() / ".cache" / "finassist" / "pgdata"))
DATA.mkdir(parents=True, exist_ok=True)
srv = pgserver.get_server(str(DATA), cleanup_mode=None)
if "finassist_test" not in srv.psql("select datname from pg_database;"):
    srv.psql("create database finassist_test;")
from psycopg.conninfo import make_conninfo

print(make_conninfo(srv.get_uri(), dbname="finassist_test"))
