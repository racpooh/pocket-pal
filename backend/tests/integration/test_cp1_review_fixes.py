"""Regression tests for the Codex CP1 review findings (15 Oct 2026).

#1 budget total can exceed available money     #2 bills imported without auto-import consent
#3 image deletion reported done when it failed   #4 reviewed bills could not be confirmed
#5 a misread OCR reference could double count a payment
"""

from __future__ import annotations

import io
import uuid

import pytest

from finassist.services.imports import LocalStorage, StorageDeleteError

from .conftest import User, drain, fields_from_gt, gt, register

pytestmark = pytest.mark.db


class FlakyStorage(LocalStorage):
    """Local storage whose delete fails while `fail` is set (simulates GCS permission/network errors)."""

    fail = False

    def delete(self, key: str) -> None:
        if self.fail:
            raise StorageDeleteError("PermissionDenied")
        super().delete(key)


@pytest.fixture
def storage(tmp_path):  # overrides conftest.storage for this module
    return FlakyStorage(str(tmp_path / "uploads"))


def _pockets(u: User) -> dict[str, int]:
    return {p["name"]: p["allocation_satang"] for p in u.req("GET", "/plan").json()["pockets"] if p["pocket_id"]}


def _plan_payload(u: User, allocations_by_name: dict[str, int]) -> dict:
    plan = u.req("GET", "/plan").json()["plan"]
    return {"kind": "budget_plan", "payload": {"period_start": plan["period_start"], "period_end": plan["period_end"],
                                               "buffer_satang": plan["buffer_satang"],
                                               "allocations": {u.pockets[n]: v for n, v in allocations_by_name.items()}}}


def _spend(u: User, amount: int, category: str, hour: int = 14):
    r = u.req("POST", "/transactions", idem=True, json={"kind": "expense", "amount_satang": amount, "occurred_date": "2026-10-15",
                                                        "occurred_at": f"2026-10-15T{hour}:00:00+07:00", "category": category,
                                                        "payee": f"shop-{uuid.uuid4().hex[:6]}"})
    assert r.status_code == 201, r.text


# ---------------- #1 ----------------

def test_f1_cannot_raise_total_beyond_available_with_existing_plan(client):
    u = User(client).onboard()
    u.approve_plan()
    alloc = _pockets(u)
    available = u.req("GET", "/plan").json()["cashflow"]["discretionary_satang"]
    assert sum(alloc.values()) == available  # fully allocated, nothing spent
    doubled = {k: v * 2 for k, v in alloc.items()}  # Codex's example: 1,000 allocated of 1,000 → 2,000
    r = u.req("POST", "/proposals", json=_plan_payload(u, doubled))
    assert r.status_code == 400 and r.json()["error"]["code"] == "ALLOCATION_EXCEEDS_AVAILABLE", r.text
    plus_one = dict(alloc, Shopping=alloc["Shopping"] + 1)
    assert u.req("POST", "/proposals", json=_plan_payload(u, plus_one)).status_code == 400
    minus_one = dict(alloc, Shopping=alloc["Shopping"] - 1)
    assert u.req("POST", "/proposals", json=_plan_payload(u, minus_one)).status_code == 201


def test_f1_after_spending_only_unspent_budget_can_move(client):
    u = User(client).onboard()
    u.approve_plan()
    alloc = _pockets(u)
    _spend(u, 30_000, "food")  # after the balance anchor: money left falls by 300.00
    plan = u.req("GET", "/plan").json()
    unspent = sum(p["remaining_satang"] for p in plan["pockets"] if p["pocket_id"])
    assert unspent == plan["cashflow"]["discretionary_satang"]
    # moving unspent budget between pockets is fine
    ok = u.req("POST", "/proposals", json={"kind": "reallocate", "payload": {"plan_id": plan["plan"]["id"], "from_pocket": u.pockets["Food"],
                                                                           "to_pocket": u.pockets["Shopping"], "amount_satang": 10_000}})
    assert ok.status_code == 201, ok.text
    # raising any pocket without lowering another is not
    assert u.req("POST", "/proposals", json=_plan_payload(u, dict(alloc, Transport=alloc["Transport"] + 1))).status_code == 400


def test_f1_cannot_move_spent_budget_out_of_an_overspent_pocket(client):
    u = User(client).onboard()
    u.approve_plan()
    alloc = _pockets(u)
    _spend(u, alloc["Food"] + 20_000, "food")  # Food overspent by 200.00
    plan = u.req("GET", "/plan").json()
    r = u.req("POST", "/proposals", json={"kind": "reallocate", "payload": {"plan_id": plan["plan"]["id"], "from_pocket": u.pockets["Food"],
                                                                          "to_pocket": u.pockets["Shopping"], "amount_satang": 10_000}})
    assert r.status_code == 400 and r.json()["error"]["code"] == "ALLOCATION_EXCEEDS_AVAILABLE", r.text


def test_f1_check_is_repeated_at_approval(client):
    u = User(client).onboard()
    u.approve_plan()
    plan = u.req("GET", "/plan").json()
    card = u.req("POST", "/proposals", json={"kind": "reallocate", "payload": {"plan_id": plan["plan"]["id"], "from_pocket": u.pockets["Food"],
                                                                             "to_pocket": u.pockets["Shopping"], "amount_satang": 50_000}}).json()
    _spend(u, _pockets(u)["Food"], "food")  # Food fully spent after the proposal was made
    r = u.req("POST", f"/proposals/{card['proposal_id']}/approve", idem=True, json={"payload_hash": card["payload_hash"]})
    assert r.status_code == 409
    details = r.json()["error"]["details"]
    # Re-checked under lock at approval: the move would now create spendable money → refused, no replacement offered.
    assert details.get("reason") == "ALLOCATION_EXCEEDS_AVAILABLE" and "replacement_proposal_id" not in details, details
    assert _pockets(u)["Shopping"] == plan["pockets"][[p["name"] for p in plan["pockets"]].index("Shopping")]["allocation_satang"]


# ---------------- #2 and #4 ----------------

def _bill_file():
    from .conftest import gt_rows

    return next(r["file"] for r in gt_rows() if r["doc_type"] == "bill")


def test_f2_bill_needs_auto_import_consent(client, db, storage, provider):
    u = User(client).onboard(auto_import=False)
    u.upload(register(provider, _bill_file()))
    assert drain(db, storage, provider) == ["needs_review"]
    assert u.req("GET", "/bills").json() == []
    item = u.req("GET", "/review-items").json()["items"][0]
    assert item["reason"] == "confirm_import"
    r = u.req("POST", f"/review-items/{item['id']}/resolve", json={"decision": "accept"})
    assert r.status_code == 200 and r.json().get("bill_id"), r.text
    assert len(u.req("GET", "/bills").json()) == 1 and u.req("GET", "/transactions").json() == []
    again = u.req("POST", f"/review-items/{item['id']}/resolve", json={"decision": "accept"})
    assert again.status_code == 404 and len(u.req("GET", "/bills").json()) == 1


def test_f2_bill_with_consent_still_imports(client, db, storage, provider):
    u = User(client).onboard(auto_import=True)
    u.upload(register(provider, _bill_file()))
    assert drain(db, storage, provider) == ["bill_created"]


def test_f4_bill_missing_due_date_can_be_completed_once(client, db, storage, provider):
    u = User(client).onboard()
    f = fields_from_gt(gt(_bill_file()))
    f["due_date_text"] = None
    u.upload(register(provider, _bill_file(), f))
    assert drain(db, storage, provider) == ["needs_review"]
    item = u.req("GET", "/review-items").json()["items"][0]
    assert "due_date" in item["problem_fields"]
    bad = u.req("POST", f"/review-items/{item['id']}/resolve", json={"decision": "accept"})
    assert bad.status_code == 400  # still missing
    ok = u.req("POST", f"/review-items/{item['id']}/resolve", json={"decision": "accept", "fields": {"due_date_text": "25 ต.ค. 69"}})
    assert ok.status_code == 200 and ok.json()["bill_id"], ok.text
    bills = u.req("GET", "/bills").json()
    assert len(bills) == 1 and bills[0]["due_date"] == "2026-10-25" and bills[0]["status"] == "unpaid"
    assert u.req("POST", f"/review-items/{item['id']}/resolve", json={"decision": "accept", "fields": {"due_date_text": "25 ต.ค. 69"}}).status_code == 404


# ---------------- #3 ----------------

def test_f3_failed_storage_delete_is_retried_not_reported_done(client, db, storage, provider, monkeypatch):
    u = User(client).onboard()
    data = register(provider, "slip_001_transfer_out.png")
    up = u.upload(data).json()
    drain(db, storage, provider)
    with db.connect() as c:
        key = c.execute("select object_key from upload where id=%s", (up["upload_id"],)).fetchone()["object_key"]
    assert (storage.root / key).exists()

    storage.fail = True
    r = u.req("DELETE", f"/uploads/{up['upload_id']}")
    assert r.status_code == 200 and r.json()["image_purge"] == "pending_retry"
    assert u.req("GET", f"/uploads/{up['upload_id']}/image").status_code == 404  # unreachable through the API at once
    with db.connect() as c:
        row = c.execute("select status, object_key, object_purged_at from upload where id=%s", (up["upload_id"],)).fetchone()
        job = c.execute("select status from job where subject_id=%s and kind='purge_upload'", (up["upload_id"],)).fetchone()
        audit = c.execute("select count(*) n from audit_event where subject_id=%s and action='image_purge' and result='error'", (up["upload_id"],)).fetchone()["n"]
    assert row["status"] == "deleted" and row["object_key"] == key and row["object_purged_at"] is None  # key kept for retry
    assert job["status"] == "queued" and audit == 1 and (storage.root / key).exists()

    u.req("DELETE", "/consents/photo_processing")  # revocation must not cancel the purge
    storage.fail = False
    monkeypatch.setenv("FINASSIST_FIXED_NOW", "2026-10-15T07:00:00+00:00")
    assert drain(db, storage, provider) == ["purged"]
    with db.connect() as c:
        row = c.execute("select object_key, object_purged_at from upload where id=%s", (up["upload_id"],)).fetchone()
        job = c.execute("select status from job where subject_id=%s and kind='purge_upload'", (up["upload_id"],)).fetchone()
    assert row["object_key"] is None and row["object_purged_at"] is not None and job["status"] == "done"
    assert not (storage.root / key).exists()


def test_f3_already_missing_object_counts_as_deleted(client, db, storage, provider):
    u = User(client).onboard()
    up = u.upload(register(provider, "slip_002_transfer_out.png")).json()
    with db.connect() as c:
        key = c.execute("select object_key from upload where id=%s", (up["upload_id"],)).fetchone()["object_key"]
    (storage.root / key).unlink()
    r = u.req("DELETE", f"/uploads/{up['upload_id']}")
    assert r.json()["image_purge"] == "done"


# ---------------- #5 ----------------

def _reencode(data: bytes) -> bytes:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as im:
        buf = io.BytesIO()
        im.convert("RGB").crop((2, 2, im.width - 2, im.height - 2)).save(buf, format="JPEG", quality=85)
        return buf.getvalue()


def test_f5_misread_ref_then_correct_read_does_not_double_count(client, db, storage, provider):
    u = User(client).onboard()
    g = gt("slip_021_transfer_out.png")
    first = fields_from_gt(g)
    first["bank_ref"] = "DS6372651676122"  # the real Haiku v0.2 misread (one digit dropped)
    u.upload(register(provider, "slip_021_transfer_out.png", first), captured_at="2026-10-15T15:00:00+07:00")  # slip time 14:32
    assert drain(db, storage, provider) == ["imported"]
    money_after_first = u.req("GET", "/plan").json()["cashflow"]["discretionary_satang"]

    import hashlib

    copy = _reencode((__import__("pathlib").Path(__file__).resolve().parents[2] / "fixtures/synthetic/slips/slip_021_transfer_out.png").read_bytes())
    provider.by_sha[hashlib.sha256(copy).hexdigest()] = fields_from_gt(g)  # same slip, reference read correctly this time
    r = u.req("POST", "/uploads", files={"image": ("copy.jpg", copy, "image/jpeg")}, data={"captured_at": "2026-10-15T15:05:00+07:00"})
    assert r.status_code == 202
    assert drain(db, storage, provider) == ["needs_review"]
    items = u.req("GET", "/review-items").json()["items"]
    assert items[0]["reason"] == "possible_duplicate" and items[0]["candidate_txn_ids"]
    assert len(u.req("GET", "/transactions").json()) == 1
    assert u.req("GET", "/plan").json()["cashflow"]["discretionary_satang"] == money_after_first
    # user confirms it is the same payment → still one transaction
    rr = u.req("POST", f"/review-items/{items[0]['id']}/resolve", json={"decision": "duplicate_of"})
    assert rr.status_code == 200 and len(u.req("GET", "/transactions").json()) == 1


def test_f5_ocr_refs_are_stored_unconfirmed(client, db, storage, provider):
    u = User(client).onboard()
    u.upload(register(provider, "slip_001_transfer_out.png"))
    drain(db, storage, provider)
    with db.connect() as c:
        assert c.execute("select bank_ref_confirmed from txn").fetchone()["bank_ref_confirmed"] is False
