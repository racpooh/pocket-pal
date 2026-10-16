"""Local backend for the Android client (CP3). Real FastAPI app + real Postgres + embedded worker, RLS roles.

  # the phone (owner): fake extraction preloaded with the SYNTHETIC slip fixtures (no model calls, no cost)
  uv run --with pixeltable-pgserver python scripts/dev_server.py --profile dev --provider fake --reset
  # then, with the phone on USB:   adb reverse tcp:8000 tcp:8000   (the app's debug build uses http://127.0.0.1:8000)
  # automated client E2E (android/tools/cp3a_e2e.py starts this itself): --profile e2e  → port 8001, own cluster

Profiles (scripts/local_envs.py) are fully separate: own pgserver cluster, database, login roles, upload storage and
port, so an automated run or the test suite can neither reset nor break the phone's server. `--profile` is required
(no default). Binds 127.0.0.1 only. The fake provider is refused outside FINASSIST_ENV=dev|test by Settings (fail
closed); /v1/health reports test_mode=true so the client shows a TEST MODE banner. Unknown (non-fixture) images fail
extraction with a provider error → extract_failed, which is the honest result for a fake extractor.
"""

from __future__ import annotations

import argparse
import hashlib
import secrets
import shutil
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "src"))
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

from local_envs import PROFILES, Profile, local_admin_url, port_free  # noqa: E402

SERVER_PROFILES = ("dev", "e2e")


def _prepare(url: str, reset: bool, prof: Profile) -> dict[str, str]:
    """Apply migrations (on --reset or an empty DB) and (re)create THIS profile's two login roles with fresh random
    passwords. The roles are per profile (finassist_app_<p>, finassist_worker_<p> ∈ finassist_worker), so rotating them
    never breaks another profile's server or the test suite (which uses finassist_app / finassist_worker)."""
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    with psycopg.connect(url, autocommit=True) as c:
        name = c.execute("select current_database()").fetchone()[0]
        if name != prof.database:
            raise SystemExit(f"profile {prof.name!r} uses database {prof.database!r}, but the URL points at {name!r}; refusing")
        empty = c.execute("select to_regclass('public.app_user') is null").fetchone()[0]
        if reset or empty:
            c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
            for f in sorted((BACKEND / "db" / "migrations").glob("*.sql")):
                c.execute(f.read_text(encoding="utf-8"))
        urls = {}
        for key, role, member_of in (("app", prof.app_role, None), ("worker", prof.worker_role, "finassist_worker")):
            pw = secrets.token_urlsafe(18)
            c.execute(f"""DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                          CREATE ROLE {role} LOGIN NOSUPERUSER NOBYPASSRLS INHERIT; END IF; END $$;""")
            c.execute(f"ALTER ROLE {role} LOGIN NOSUPERUSER NOBYPASSRLS INHERIT PASSWORD '{pw}'")
            if member_of:
                c.execute(f"GRANT {member_of} TO {role}")  # job-claim policy is TO finassist_worker (applies to members)
            c.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
            c.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}")
            c.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}")
            d = conninfo_to_dict(url)
            d.update(user=role, password=pw)
            urls[key] = make_conninfo(**d)
    return urls


def _reset_storage(prof: Profile) -> None:
    root = prof.storage
    assert root is not None and root.name == f"{prof.name}-uploads", root  # only this profile's own storage
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)


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
    ap.add_argument("--profile", choices=SERVER_PROFILES, required=True, help="dev = the phone; e2e = automated runs (no default)")
    ap.add_argument("--provider", choices=["fake", "anthropic"], required=True, help="explicit; no default")
    ap.add_argument("--database-url", default=None, help="admin URL of the profile's database (default: the profile's own local pgserver cluster)")
    ap.add_argument("--reset", action="store_true", help="drop and re-create the profile's schema and upload storage")
    ap.add_argument("--port", type=int, default=None, help="default: dev 8000, e2e 8001")
    a = ap.parse_args()
    prof = PROFILES[a.profile]
    port = a.port or prof.port
    others = {p.port: p.name for p in PROFILES.values() if p.port and p.name != prof.name}
    if port in others:
        raise SystemExit(f"port {port} belongs to profile {others[port]!r}; refusing")
    if not port_free(port):
        raise SystemExit(f"port {port} is already in use (another server running?); refusing to start")

    import uvicorn

    from finassist.api.app import create_app
    from finassist.settings import Settings

    url = a.database_url or local_admin_url(prof)
    urls = _prepare(url, a.reset, prof)
    if a.reset:
        _reset_storage(prof)
    provider = _fixture_provider() if a.provider == "fake" else None
    settings = Settings(env="dev", model_provider=a.provider, database_url=urls["app"],
                        worker_database_url=urls["worker"], embedded_worker=True, storage_dir=str(prof.storage))
    app = create_app(settings, extraction_provider=provider)
    print(f"PROFILE {prof.name}: database {prof.database}, roles {prof.app_role}/{prof.worker_role}, storage {prof.storage}, port {port}", flush=True)
    if a.provider == "fake":
        print("=" * 72 + f"\nTEST MODE: fake extraction with {len(provider.by_sha)} SYNTHETIC fixtures; no model calls.\n"
              "Non-fixture images will fail extraction (extract_failed).\n" + "=" * 72, flush=True)
    else:
        print("REAL MODEL PROVIDER: extraction calls are billed. CP3 rules: do not use this mode.", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
