"""API + Postgres + worker fixtures. Uses a FAKE extraction provider and a SCRIPTED chat model (mocks)."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402

from finassist.api.app import create_app  # noqa: E402
from finassist.domain.money import format_thb  # noqa: E402
from finassist.infra import Database  # noqa: E402
from finassist.providers import FakeExtractionProvider  # noqa: E402
from finassist.services.imports import LocalStorage  # noqa: E402
from finassist.settings import Settings  # noqa: E402

URL = os.environ.get("TEST_DATABASE_URL")
BACKEND = Path(__file__).resolve().parents[2]
SLIPS = BACKEND / "fixtures" / "synthetic" / "slips"
FIXED_NOW = "2026-10-15T06:00:00+00:00"  # 13:00 ICT


def _reset(url: str) -> None:
    with psycopg.connect(url, autocommit=True) as c:
        name = c.execute("select current_database()").fetchone()[0]
        if not name.endswith("_test"):
            pytest.fail(f"refusing to reset non-test database {name!r}")
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        for f in sorted((BACKEND / "db" / "migrations").glob("*.sql")):
            c.execute(f.read_text(encoding="utf-8"))
        # Runtime role for the API: no superuser, no BYPASSRLS → RLS policies apply (0002_rls.sql).
        c.execute("""DO $$ BEGIN
                       IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finassist_app') THEN
                         CREATE ROLE finassist_app LOGIN PASSWORD 'finassist_app_test' NOSUPERUSER NOBYPASSRLS;
                       END IF; END $$;""")
        c.execute("ALTER ROLE finassist_worker LOGIN PASSWORD 'finassist_worker_test'")
        for role in ("finassist_app", "finassist_worker"):
            c.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
            c.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}")
            c.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}")
        c.execute("GRANT USAGE ON SCHEMA public TO finassist_app")
        c.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO finassist_app")
        c.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO finassist_app")


def app_url(url: str, role: str = "finassist_app") -> str:
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    d = conninfo_to_dict(url)
    d.update(user=role, password=f"{role}_test")
    return make_conninfo(**d)


@pytest.fixture(scope="session")
def db():
    if not URL:
        pytest.skip("TEST_DATABASE_URL not set")
    _reset(URL)
    return Database(URL)


@pytest.fixture(autouse=True)
def fixed_now(monkeypatch):
    monkeypatch.setenv("FINASSIST_FIXED_NOW", FIXED_NOW)


@pytest.fixture
def storage(tmp_path):
    return LocalStorage(str(tmp_path / "uploads"))


@pytest.fixture
def provider():
    return FakeExtractionProvider()


@pytest.fixture
def app_db(db):
    return Database(app_url(URL))


@pytest.fixture
def app(app_db, storage):
    # API runs as the RLS-restricted role; `db` (superuser, like the worker's BYPASSRLS role) is used by the worker and checks.
    return create_app(Settings(_env_file=None, model_provider="fake", database_url=URL, storage_dir=str(storage.root)), db=app_db, storage=storage)


@pytest.fixture
def client(app):
    return TestClient(app)


def gt_rows() -> list[dict]:
    return [json.loads(line) for line in (SLIPS / "ground_truth.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]


def gt(file: str) -> dict:
    return next(r for r in gt_rows() if r["file"] == file)


def fields_from_gt(r: dict) -> dict:
    """What a perfect extractor would return for this synthetic image (fake provider output)."""
    occ = r.get("occurred_at") or r.get("occurred_date")
    return {
        "doc_type": r["doc_type"],
        "amount_text": format_thb(r["amount_satang"]) if r.get("amount_satang") is not None else None,
        "date_text": occ[:10] if occ else None,
        "time_text": occ[11:16] if occ and len(occ) > 10 else None,
        "status": {"completed": "success", "pending": "pending", "failed": "failed"}.get(r.get("payment_status")),
        "payee": r.get("payee_display"),
        "bank_ref": r.get("bank_ref"),
        "due_date_text": r.get("bill_due_date"),
        "readability": "clear",
    }


def register(provider: FakeExtractionProvider, file: str, fields: dict | None = None) -> bytes:
    import hashlib

    data = (SLIPS / file).read_bytes()
    provider.by_sha[hashlib.sha256(data).hexdigest()] = fields or fields_from_gt(gt(file))
    return data


class User:
    def __init__(self, client: TestClient):
        self.c = client
        self.email = f"{uuid.uuid4().hex[:10]}@example.test"
        assert client.post("/v1/auth/signup", json={"email": self.email, "password": "correct horse battery"}).status_code == 201
        tok = client.post("/v1/auth/login", json={"email": self.email, "password": "correct horse battery"}).json()["token"]
        self.h = {"Authorization": f"Bearer {tok}"}

    def req(self, method: str, path: str, *, idem: bool = False, **kw):
        headers = dict(self.h)
        if idem:
            headers["Idempotency-Key"] = kw.pop("key", None) or str(uuid.uuid4())
        headers.update(kw.pop("headers", {}))
        return self.c.request(method, "/v1" + path, headers=headers, **kw)

    def onboard(self, balance_satang: int = 1_500_000, *, auto_import: bool = True) -> "User":
        r = self.req("PUT", "/me/profile", json={
            "income_satang": 2_000_000, "income_frequency": "monthly", "next_income_date": "2026-11-01",
            "essentials": [{"name": "Rent", "amount_satang": 500_000, "due_day": 30}]})
        assert r.status_code == 200, r.text
        acct = self.req("GET", "/accounts").json()[0]["id"]
        self.account = acct
        assert self.req("POST", f"/accounts/{acct}/balance-observations", json={"amount_satang": balance_satang}).status_code == 201
        self.pockets = {}
        for name, cats in (("Food", ["food"]), ("Shopping", ["shopping"]), ("Transport", ["transport"]), ("Entertainment", ["entertainment"]), ("Other", ["other", "bills"])):
            self.pockets[name] = self.req("POST", "/pockets", json={"name": name, "categories": cats}).json()["id"]
        assert self.req("POST", "/consents", json={"scope": "photo_processing", "version": "v1",
                                                    "params": {"scan_from": "2026-07-01"}}).status_code == 201
        if auto_import:
            assert self.req("POST", "/consents", json={"scope": "auto_import", "version": "v1"}).status_code == 201
        return self

    def upload(self, data: bytes, name: str = "slip.png", captured_at: str = "2026-10-15T13:00:00+07:00"):
        return self.req("POST", "/uploads", files={"image": (name, data, "image/png")}, data={"captured_at": captured_at})

    def approve_plan(self) -> dict:
        card = self.req("POST", "/plan/suggest").json()
        r = self.req("POST", f"/proposals/{card['proposal_id']}/approve", idem=True, json={"payload_hash": card["payload_hash"], "card_hash": card["card_hash"]})
        assert r.status_code == 200, r.text
        return card


def drain(db, storage, provider, max_jobs: int = 50) -> list[str]:
    """Runs the worker as the finassist_worker role (RLS applies except for claiming jobs). `db` is ignored."""
    from finassist.services.imports import run_once

    wdb = Database(app_url(URL, "finassist_worker"))
    out = []
    for _ in range(max_jobs):
        with wdb.connect() as conn:
            o = run_once(conn, storage, provider)
        if o is None:
            break
        out.append(o)
    return out
