"""CP3a backend additions used by the Android client: upload retry, explicit test-mode reporting."""

from __future__ import annotations

import pytest

from .conftest import User, drain, register

pytestmark = pytest.mark.db


def _status(u: User, uid: str) -> str:
    return u.req("GET", f"/uploads/{uid}").json()["status"]


def test_retry_failed_extraction_requeues_once_and_imports(client, db, storage, provider):
    u = User(client).onboard()
    data = register(provider, "slip_003_transfer_out.png")
    uid = u.upload(data).json()["upload_id"]
    with db.connect() as c:  # as if the worker had given up (extraction errors are covered elsewhere)
        c.execute("update job set status='dead' where subject_id=%s", (uid,))
        c.execute("update upload set status='extract_failed' where id=%s", (uid,))
    r = u.req("POST", f"/uploads/{uid}/retry")
    assert r.status_code == 202 and r.json()["status"] == "received"
    again = u.req("POST", f"/uploads/{uid}/retry")
    assert again.status_code == 409 and again.json()["error"]["code"] == "NOT_RETRYABLE"  # already queued: no second job
    with db.connect() as c:
        assert c.execute("select count(*) n from job where subject_id=%s and status in ('queued','running')", (uid,)).fetchone()["n"] == 1
    drain(db, storage, provider)
    assert _status(u, uid) == "imported"
    assert u.req("POST", f"/uploads/{uid}/retry").status_code == 409


def test_retry_respects_consent(client, db, storage, provider):
    u = User(client).onboard()
    uid = u.upload(register(provider, "slip_004_transfer_out.png")).json()["upload_id"]
    assert u.req("DELETE", "/consents/photo_processing").status_code == 200
    assert _status(u, uid) == "cancelled_consent"
    r = u.req("POST", f"/uploads/{uid}/retry")
    assert r.status_code == 403 and r.json()["error"]["code"] == "CONSENT_REQUIRED"
    assert u.req("POST", "/consents", json={"scope": "photo_processing", "version": "v1", "params": {"scan_from": "2026-10-15"}}).status_code == 201
    r2 = u.req("POST", f"/uploads/{uid}/retry")  # captured 15 Oct 13:00 → inside the new range
    assert r2.status_code == 202
    drain(db, storage, provider)
    assert _status(u, uid) in ("imported", "needs_review")
    other = User(client).onboard()
    assert other.req("POST", f"/uploads/{uid}/retry").status_code == 404


def test_list_pockets_is_owner_scoped(client):
    u, other = User(client).onboard(), User(client).onboard()
    names = [p["name"] for p in u.req("GET", "/pockets").json()]
    assert sorted(names) == ["Entertainment", "Food", "Other", "Shopping", "Transport"]
    other_ids = {p["pocket_id"] for p in other.req("GET", "/pockets").json()}
    assert not other_ids & {p["pocket_id"] for p in u.req("GET", "/pockets").json()}
    assert next(p for p in u.req("GET", "/pockets").json() if p["name"] == "Other")["categories"] == ["bills", "other"]
