"""Local environment profiles: each one has its OWN Postgres cluster, database, login roles, upload storage and port.

Why (16 Oct 2026): automated runs reset the phone's database once, and every local script shared one pgserver cluster
and the cluster-wide roles `finassist_app` / `finassist_worker`, whose passwords each script rotated — so running the
test suite or an E2E run could break a running phone server even without a reset. Profiles keep them apart:

| profile  | used by                                   | cluster dir (under FINASSIST_PGDATA_ROOT) | database                 | login roles            | storage                         | port |
|----------|-------------------------------------------|-------------------------------------------|--------------------------|------------------------|---------------------------------|------|
| dev      | the phone (owner, `dev_server.py`)        | pgdata-dev                                | finassist_dev            | finassist_{app,worker}_dev | dev-uploads (same root)     | 8000 |
| e2e      | automated client E2E (`cp3a_e2e.py`)      | pgdata-e2e                                | finassist_e2e            | finassist_{app,worker}_e2e | e2e-uploads (same root)     | 8001 |
| test     | pytest (`local_pg.py`)                    | pgdata-test                               | finassist_test           | finassist_app/worker (conftest) | per-test temp dirs     | —    |
| realeval | real-slip evaluation replay (private)     | pgdata-realeval                           | finassist_realeval_test  | finassist_app/worker (conftest) | eval/private/<round>/uploads | — |

FINASSIST_PGDATA_ROOT defaults to ~/.cache/finassist (outside the repo and synced folders); clusters AND upload
storage of the server profiles live there, so uploaded images never sit in the repo folder. The old single-cluster
variable FINASSIST_PGDATA is refused (it would put two profiles in one cluster). Each cluster carries a marker file
`finassist_profile`; a cluster whose marker names another profile is refused.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent


@dataclass(frozen=True)
class Profile:
    name: str
    cluster: str
    database: str
    storage_dir: str | None
    port: int | None

    @property
    def storage(self) -> Path | None:
        return pgdata_root() / self.storage_dir if self.storage_dir else None

    @property
    def app_role(self) -> str:
        return f"finassist_app_{self.name}"

    @property
    def worker_role(self) -> str:
        return f"finassist_worker_{self.name}"


PROFILES = {
    "dev": Profile("dev", "pgdata-dev", "finassist_dev", "dev-uploads", 8000),
    "e2e": Profile("e2e", "pgdata-e2e", "finassist_e2e", "e2e-uploads", 8001),
    "test": Profile("test", "pgdata-test", "finassist_test", None, None),
    "realeval": Profile("realeval", "pgdata-realeval", "finassist_realeval_test", None, None),
}


class EnvError(SystemExit):
    pass


def pgdata_root() -> Path:
    if os.environ.get("FINASSIST_PGDATA"):
        raise EnvError("FINASSIST_PGDATA (one shared cluster) is no longer supported; set FINASSIST_PGDATA_ROOT instead "
                       "(each profile gets its own cluster under it)")
    return Path(os.environ.get("FINASSIST_PGDATA_ROOT", Path.home() / ".cache" / "finassist"))


def cluster_dir(p: Profile) -> Path:
    d = pgdata_root() / p.cluster
    d.mkdir(parents=True, exist_ok=True)
    marker = d.parent / f"{p.cluster}.profile"  # outside PGDATA itself (initdb wants an empty dir)
    if marker.exists() and marker.read_text().strip() != p.name:
        raise EnvError(f"cluster {d} belongs to profile {marker.read_text().strip()!r}, not {p.name!r}; refusing")
    marker.write_text(p.name)
    return d


def _psql_retry(srv, sql: str, tries: int = 30) -> str:
    """pgserver can return before the server accepts connections on a cold start (seen in the owner's VM)."""
    for i in range(tries):
        try:
            return srv.psql(sql)
        except subprocess.CalledProcessError:
            if i == tries - 1:
                raise
            time.sleep(1)
    raise RuntimeError("unreachable")


def local_admin_url(p: Profile) -> str:
    """Start (or reuse) this profile's own pgserver cluster; create its database; return the admin URL."""
    import pixeltable_pgserver as pgserver
    from psycopg.conninfo import make_conninfo

    srv = pgserver.get_server(str(cluster_dir(p)), cleanup_mode=None)
    if p.database not in _psql_retry(srv, "select datname from pg_database;"):
        _psql_retry(srv, f"create database {p.database};")
    return make_conninfo(srv.get_uri(), dbname=p.database)


def port_free(port: int, host: str = "127.0.0.1") -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False
