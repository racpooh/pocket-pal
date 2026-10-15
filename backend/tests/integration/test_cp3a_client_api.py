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


# ---------------- Codex CP3a review ----------------

def test_me_returns_only_the_session_owner(client, db):
    u = User(client).onboard()
    with db.connect() as c:
        oid = c.execute("select id from app_user where email=%s", (u.email,)).fetchone()["id"]
    assert u.req("GET", "/me").json() == {"user_id": str(oid)}


def test_upload_for_another_account_is_refused_and_stores_nothing(client, db, storage, provider):
    """#1: an image queued for account A must never be filed under B, even if the client's session changed."""
    a, b = User(client).onboard(), User(client).onboard()
    a_id = a.req("GET", "/me").json()["user_id"]
    data = register(provider, "slip_003_transfer_out.png")
    r = b.req("POST", "/uploads", files={"image": ("x.png", data, "image/png")},
              data={"captured_at": "2026-10-15T13:00:00+07:00", "expected_owner_id": a_id})
    assert r.status_code == 409 and r.json()["error"]["code"] == "OWNER_MISMATCH"
    assert b.req("GET", "/uploads").json() == [] and a.req("GET", "/uploads").json() == []
    b_id = b.req("GET", "/me").json()["user_id"]
    ok = b.req("POST", "/uploads", files={"image": ("x.png", data, "image/png")},
               data={"captured_at": "2026-10-15T13:00:00+07:00", "expected_owner_id": b_id})
    assert ok.status_code == 202
    drain(db, storage, provider)  # leave no queued job for later tests (the worker claims across owners)


def test_undated_photo_needs_explicit_confirmation(client, db, storage, provider):
    """Codex answer 2: no capture date → the consented range cannot be checked → never accepted silently."""
    u = User(client).onboard()
    data = register(provider, "slip_004_transfer_out.png")
    r = u.req("POST", "/uploads", files={"image": ("x.png", data, "image/png")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "CAPTURE_DATE_REQUIRED"
    assert u.req("GET", "/uploads").json() == []
    r2 = u.req("POST", "/uploads", files={"image": ("x.png", data, "image/png")}, data={"confirmed_undated": "true"})
    assert r2.status_code == 202
    with db.connect() as c:
        d = c.execute("select details from audit_event where action='upload' and subject_id=%s", (r2.json()["upload_id"],)).fetchone()["details"]
    assert d["undated_confirmed"] is True
    drain(db, storage, provider)


def _receipt_review(u, db, storage, provider):
    from .conftest import gt, gt_rows

    rec = [r for r in gt_rows() if any(t.startswith("same_purchase_as") for t in r["group_tags"]) and r["doc_type"] == "receipt"][0]
    slip = rec["group_tags"][0].split(":", 1)[1]
    assert gt(slip)["doc_type"] != "receipt"
    u.upload(register(provider, slip))
    drain(db, storage, provider)
    u.upload(register(provider, rec["file"]))
    drain(db, storage, provider)
    return u.req("GET", "/review-items").json()["items"][0]


def test_receipt_review_offers_link_not_accept_and_link_adds_no_spending(client, db, storage, provider):
    """#3: a receipt for a purchase already recorded must be attached, not recorded again."""
    u = User(client).onboard()
    item = _receipt_review(u, db, storage, provider)
    assert item["reason"] == "receipt_link"
    assert item["allowed_decisions"] == ["link_receipt", "distinct", "not_a_transaction"]
    cand = item["candidates"]
    assert len(cand) == 1 and cand[0]["amount_satang"] > 0 and cand[0]["txn_id"] == item["candidate_txn_ids"][0]
    before = u.req("GET", "/spending?from=2026-07-01&to=2026-11-01").json()["total_satang"]
    bad = u.req("POST", f"/review-items/{item['id']}/resolve", json={"decision": "accept"})
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "DECISION_NOT_ALLOWED"
    other = u.req("POST", "/transactions", idem=True, json={"kind": "expense", "amount_satang": 1, "occurred_date": "2026-10-15",
                                                            "payee": "x", "confirm_distinct": True}).json()["id"]
    wrong = u.req("POST", f"/review-items/{item['id']}/resolve", json={"decision": "link_receipt", "txn_id": other})
    assert wrong.status_code == 400  # only a suggested record can be linked
    ok = u.req("POST", f"/review-items/{item['id']}/resolve", json={"decision": "link_receipt", "txn_id": cand[0]["txn_id"]})
    assert ok.status_code == 200
    assert u.req("GET", "/spending?from=2026-07-01&to=2026-11-01").json()["total_satang"] == before + 1  # only the ฿0.01 test row
    assert len([t for t in u.req("GET", "/transactions").json() if t["amount_satang"] == cand[0]["amount_satang"]]) == 1
