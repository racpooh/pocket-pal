"""Uploads, extraction jobs, validation, dedup, review queue (R2.*, SI-5, SI-6, SI-10)."""

from __future__ import annotations

import hashlib
import io
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from finassist.api.errors import ApiError
from finassist.domain import extraction_validation as ev
from finassist.domain.classify import is_intermediary, normalize_payee, suggest
from finassist.domain.dedup import Candidate, decide, normalize_ref
from finassist.infra import audit, bump_watermark, lock_owner_ledger, set_owner
from finassist.providers import EXTRACTION_SCHEMA_VERSION, ExtractionProvider, ProviderError
from finassist.services import core
from finassist.services.core import _nf, now_utc

MAX_ATTEMPTS = 5  # extraction jobs only; purge jobs never give up (see _fail_purge)
LEASE = timedelta(minutes=5)
PURGE_MAX_DELAY = timedelta(hours=1)
PURGE_ALERT_EVERY = 5  # audit an "overdue" event every N failed attempts
SEED_MERCHANTS: dict[str, str] = {}  # curated later; kept empty rather than invented


# ---------------- storage (dev: local private dir; deployed: private bucket, D4) ----------------

class LocalStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def put(self, key: str, data: bytes) -> None:
        p = self.root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        os.chmod(p, 0o600)

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def delete(self, key: str) -> None:
        """Raises on failure. A missing object counts as deleted (idempotent retry)."""
        try:
            (self.root / key).unlink()
        except FileNotFoundError:
            pass


class StorageDeleteError(Exception):
    """The object store did not confirm deletion; the caller must keep the key and retry."""


class GCSStorage:
    """Private Google Cloud Storage bucket (deployed). Bucket must have public access prevention enforced;
    objects are encrypted at rest by Google by default (or CMEK if configured on the bucket)."""

    def __init__(self, bucket: str) -> None:
        from google.cloud import storage  # optional dependency: uv sync --extra gcp

        self.bucket = storage.Client().bucket(bucket)
        self.root = f"gs://{bucket}"

    def put(self, key: str, data: bytes) -> None:
        self.bucket.blob(key).upload_from_string(data, content_type="application/octet-stream")

    def get(self, key: str) -> bytes:
        return self.bucket.blob(key).download_as_bytes()

    def delete(self, key: str) -> None:
        """Raises StorageDeleteError unless GCS confirms deletion. NotFound (already gone) is success."""
        from google.api_core import exceptions as gexc

        try:
            self.bucket.blob(key).delete()
        except gexc.NotFound:
            return
        except Exception as e:  # permission, network, 5xx: keep the key, retry later
            raise StorageDeleteError(type(e).__name__) from None


def make_storage(settings):
    if settings.storage_backend == "gcs":
        return GCSStorage(settings.gcs_bucket)
    return LocalStorage(settings.storage_dir)


def _sniff(data: bytes) -> tuple[str, int | None]:
    """Magic-byte check + decode with Pillow; returns (mime, dHash64). Rejects non-images."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        mime = "image/png"
    elif data[:3] == b"\xff\xd8\xff":
        mime = "image/jpeg"
    else:
        raise ApiError(415, "UNSUPPORTED_MEDIA", "Only JPEG or PNG images are accepted.")
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as im:
            im.verify()
        with Image.open(io.BytesIO(data)) as im:
            if im.width * im.height > 40_000_000:
                raise ApiError(413, "UPLOAD_TOO_LARGE", "Image dimensions too large.")
            g = im.convert("L").resize((9, 8))
            px = list(g.tobytes())
        bits = 0
        for row in range(8):
            for col in range(8):
                bits = (bits << 1) | (1 if px[row * 9 + col] > px[row * 9 + col + 1] else 0)
        phash = bits - (1 << 64) if bits >= (1 << 63) else bits  # fit signed bigint
    except ApiError:
        raise
    except Exception:
        raise ApiError(415, "UNSUPPORTED_MEDIA", "The file is not a readable image.") from None
    return mime, phash


def create_upload(conn, storage: LocalStorage, owner_id, data: bytes, captured_at: datetime | None, max_bytes: int) -> tuple[int, dict]:
    if not data:
        raise ApiError(400, "VALIDATION_FAILED", "Empty upload.")
    if len(data) > max_bytes:
        raise ApiError(413, "UPLOAD_TOO_LARGE", "Image is larger than the limit.")
    mime, phash = _sniff(data)
    digest = hashlib.sha256(data).digest()
    with conn.transaction():
        grant = core.active_consent(conn, owner_id, "photo_processing", lock="share")
        if not grant:
            raise ApiError(403, "CONSENT_REQUIRED", "Allow photo processing first.", details={"scope": "photo_processing"})
        rng = grant["params"] or {}
        if captured_at and rng.get("scan_from") and captured_at.date() < date.fromisoformat(rng["scan_from"]):
            raise ApiError(403, "OUTSIDE_CONSENTED_RANGE", "This photo is outside the date range you allowed.")
        existing = conn.execute("select id,status from upload where owner_id=%s and sha256=%s and status<>'deleted'", (owner_id, digest)).fetchone()
        if existing:
            return 200, {"upload_id": str(existing["id"]), "status": existing["status"], "duplicate_image": True}
        uid = core.new_id()
        key = f"owners/{owner_id}/uploads/{uid}"
        storage.put(key, data)
        conn.execute("""insert into upload(id,owner_id,consent_grant_id,sha256,phash,object_key,mime,bytes,captured_at,status)
                        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,'received')""",
                     (uid, owner_id, grant["id"], digest, phash, key, mime, len(data), captured_at))
        conn.execute("insert into job(owner_id,kind,subject_id,consent_grant_id,run_after) values (%s,'extract',%s,%s,%s)",
                     (owner_id, uid, grant["id"], now_utc()))
        audit(conn, owner_id, "user", "upload", "upload", uid, details={"bytes": len(data), "mime": mime})
    return 202, {"upload_id": str(uid), "status": "received", "duplicate_image": False}


def list_uploads(conn, owner_id, status: str | None = None) -> list[dict]:
    q = "select id,status,mime,bytes,captured_at,created_at from upload where owner_id=%s and status<>'deleted'"
    args = [owner_id]
    if status:
        q += " and status=%s"; args.append(status)
    return conn.execute(q + " order by created_at desc", args).fetchall()


def get_upload(conn, owner_id, upload_id) -> dict:
    row = conn.execute("select id,status,mime,bytes,captured_at,created_at from upload where owner_id=%s and id=%s and status<>'deleted'",
                       (owner_id, upload_id)).fetchone()
    if not row:
        raise _nf()
    ex = conn.execute("""select model_id,field_states,created_at from extraction where owner_id=%s and upload_id=%s
                         order by created_at desc limit 1""", (owner_id, upload_id)).fetchone()
    txn = conn.execute("select txn_id,relation from txn_evidence where owner_id=%s and upload_id=%s", (owner_id, upload_id)).fetchone()
    return {**row, "extraction": ex, "evidence_of": txn}


def read_image(conn, storage: LocalStorage, owner_id, upload_id) -> tuple[bytes, str]:
    row = conn.execute("select object_key,mime from upload where owner_id=%s and id=%s and status<>'deleted' and object_key is not null",
                       (owner_id, upload_id)).fetchone()
    if not row:
        raise _nf()
    return storage.get(row["object_key"]), row["mime"]


def delete_upload(conn, storage: LocalStorage, owner_id, upload_id, *, remove_records: bool = True) -> dict:
    """Two-phase delete (CP1 #3). One transaction marks the upload deleted (unreachable via the API), removes its
    records and queues a purge job; the stored object is then deleted and only a confirmed delete clears the key.
    A repeated DELETE is idempotent and doubles as a recovery path: it re-queues and retries the purge."""
    removed, repeat = 0, False
    with conn.transaction():
        row = conn.execute("select object_key, status from upload where owner_id=%s and id=%s for update", (owner_id, upload_id)).fetchone()
        if not row:
            raise _nf()
        if row["object_key"]:
            conn.execute("""insert into job(owner_id,kind,subject_id,consent_grant_id,run_after) values (%s,'purge_upload',%s,null,%s)
                            on conflict do nothing""", (owner_id, upload_id, now_utc()))
        if row["status"] == "deleted":
            repeat = True
        else:
            conn.execute("update upload set status='deleted', deleted_at=%s where id=%s", (now_utc(), upload_id))
            conn.execute("update job set status='cancelled' where owner_id=%s and subject_id=%s and kind='extract' and status in ('queued','running')",
                         (owner_id, upload_id))
            conn.execute("update review_item set status='dismissed', resolution='upload_deleted' where owner_id=%s and upload_id=%s and status='open'",
                         (owner_id, upload_id))
            if remove_records:
                removed = conn.execute("""update txn set deleted_at=%s, bank_ref_norm=null where owner_id=%s and upload_id=%s
                                          and source<>'manual' and deleted_at is null""", (now_utc(), owner_id, upload_id)).rowcount
                removed += conn.execute("""update bill set status='cancelled', version=version+1 where owner_id=%s and upload_id=%s
                                           and status='unpaid'""", (owner_id, upload_id)).rowcount
            bump_watermark(conn, owner_id)
            audit(conn, owner_id, "user", "upload_delete", "upload", upload_id, details={"records_removed": removed})
    purge = "done" if repeat else "not_needed"
    if row["object_key"]:
        purge = "done" if _purge_object(conn, storage, owner_id, upload_id, row["object_key"]) else "pending_retry"
    out = {"upload_id": str(upload_id), "status": "deleted", "records_removed": removed, "image_purge": purge}
    if repeat:
        out["repeat"] = True
    return out


def _purge_object(conn, storage, owner_id, upload_id, key: str) -> bool:
    """Delete the stored image; only on confirmed success clear the key and close the purge job."""
    try:
        storage.delete(key)
    except Exception as e:
        with conn.transaction():
            audit(conn, owner_id, "system", "image_purge", "upload", upload_id, result="error", details={"code": type(e).__name__})
        return False
    with conn.transaction():
        conn.execute("update upload set object_key=null, object_purged_at=%s where owner_id=%s and id=%s and object_key=%s",
                     (now_utc(), owner_id, upload_id, key))
        conn.execute("update job set status='done', locked_until=null where owner_id=%s and subject_id=%s and kind='purge_upload' and status in ('queued','running')",
                     (owner_id, upload_id))
        audit(conn, owner_id, "system", "image_purge", "upload", upload_id)
    return True


def delete_all_imported(conn, storage: LocalStorage, owner_id) -> dict:
    ids = [r["id"] for r in conn.execute("select id from upload where owner_id=%s and status<>'deleted'", (owner_id,)).fetchall()]
    for i in ids:
        delete_upload(conn, storage, owner_id, i)
    return {"uploads_deleted": len(ids)}


# ---------------- worker ----------------

def claim_job(conn) -> dict | None:
    """Claim one job: queued and due, OR running with an expired lease (its worker died). Each claim gets a new
    lease token; every later write by the worker is conditional on that token (stale workers cannot overwrite)."""
    import uuid as _uuid

    with conn.transaction():
        # Recovery for purge jobs that died under the old policy: purges never give up.
        conn.execute("""update job d set status='queued', run_after=%s where d.kind='purge_upload' and d.status='dead'
                        and not exists (select 1 from job l where l.kind='purge_upload' and l.subject_id=d.subject_id
                                        and l.status in ('queued','running'))""", (now_utc(),))
        job = conn.execute(
            """select id,owner_id,kind,subject_id,consent_grant_id,attempts,status from job
               where (status='queued' and run_after <= %s) or (status='running' and locked_until < %s)
               order by id for update skip locked limit 1""", (now_utc(), now_utc())).fetchone()
        if not job:
            return None
        set_owner(conn, job["owner_id"])  # RLS: everything below is scoped to this job's owner
        reclaimed = job["status"] == "running"
        if reclaimed:
            audit(conn, job["owner_id"], "worker", "job_lease_expired", "job", None, details={"job_id": job["id"], "kind": job["kind"], "attempts": job["attempts"]})
            if job["kind"] == "extract" and job["attempts"] >= MAX_ATTEMPTS:  # crash loop: stop retrying extraction
                conn.execute("update job set status='dead', last_error_code='LeaseExpired', locked_until=null, lease_token=null where id=%s", (job["id"],))
                conn.execute("update upload set status='extract_failed' where id=%s and status in ('received','extracting')", (job["subject_id"],))
                return {"dead": True, **job}
        token = _uuid.uuid4()
        conn.execute("update job set status='running', attempts=attempts+1, locked_until=%s, lease_token=%s where id=%s",
                     (now_utc() + LEASE, token, job["id"]))
        if job["kind"] == "extract":
            conn.execute("update upload set status='extracting' where id=%s and status='received'", (job["subject_id"],))
    job["attempts"] += 1
    job["lease_token"] = token
    job["reclaimed"] = reclaimed
    return job


def run_once(conn, storage: LocalStorage, provider: ExtractionProvider) -> str | None:
    """Process at most one job. Returns an outcome label, or None when idle."""
    job = claim_job(conn)
    if not job:
        return None
    if job.get("dead"):
        return "dead"
    owner = job["owner_id"]
    if job["kind"] == "purge_upload":
        row = conn.execute("select object_key from upload where owner_id=%s and id=%s", (owner, job["subject_id"])).fetchone()
        if not row or not row["object_key"]:
            _finish(conn, job, "done")
            return "purged"
        if _purge_object(conn, storage, owner, job["subject_id"], row["object_key"]):
            return "purged"
        return _fail_purge(conn, job)
    up = conn.execute("select object_key,mime,status from upload where owner_id=%s and id=%s", (owner, job["subject_id"])).fetchone()
    if not up or up["status"] in ("deleted", "cancelled_consent") or not up["object_key"]:
        _finish(conn, job, "cancelled")
        return "cancelled"
    try:
        result = provider.extract(storage.get(up["object_key"]), up["mime"])  # outside any DB transaction
    except (ProviderError, FileNotFoundError) as e:
        return _fail(conn, job, type(e).__name__)
    return persist_extraction(conn, job, result)


def _finish(conn, job, status: str) -> None:
    with conn.transaction():
        conn.execute("update job set status=%s, locked_until=null where id=%s and lease_token=%s", (status, job["id"], job["lease_token"]))


def _fail_purge(conn, job) -> str:
    """Purge failures are retried forever with capped backoff; never 'dead'. Overdue purges are audited."""
    with conn.transaction():
        delay = min(timedelta(seconds=2 ** min(job["attempts"], 20)), PURGE_MAX_DELAY)
        n = conn.execute("""update job set status='queued', run_after=%s, last_error_code='StorageDeleteError', locked_until=null
                            where id=%s and lease_token=%s and status='running'""", (now_utc() + delay, job["id"], job["lease_token"])).rowcount
        if n and job["attempts"] % PURGE_ALERT_EVERY == 0:
            audit(conn, job["owner_id"], "system", "image_purge_overdue", "upload", job["subject_id"], result="error",
                  details={"attempts": job["attempts"]})
    return "purge_retry" if n else "stale_lease"


def _fail(conn, job, code: str, *, mark_upload: bool = True) -> str:
    with conn.transaction():
        if job["attempts"] >= MAX_ATTEMPTS:
            n = conn.execute("update job set status='dead', last_error_code=%s where id=%s and lease_token=%s and status='running'",
                             (code, job["id"], job["lease_token"])).rowcount
            if not n:
                return "stale_lease"
            if mark_upload:
                conn.execute("update upload set status='extract_failed' where id=%s and status='extracting'", (job["subject_id"],))
            audit(conn, job["owner_id"], "worker", "extract", "upload", job["subject_id"], result="error", details={"code": code, "dead": True})
            return "dead"
        delay = timedelta(seconds=2 ** job["attempts"])
        n = conn.execute("update job set status='queued', run_after=%s, last_error_code=%s where id=%s and status='running' and lease_token=%s",
                         (now_utc() + delay, code, job["id"], job["lease_token"])).rowcount
        if not n:
            return "stale_lease"
        audit(conn, job["owner_id"], "worker", "extract", "upload", job["subject_id"], result="error", details={"code": code, "attempt": job["attempts"]})
    return "retry"


def persist_extraction(conn, job: dict, result) -> str:
    owner, upload_id = job["owner_id"], job["subject_id"]
    with conn.transaction():
        # SI-5: lock consent FOR SHARE (revoke takes FOR UPDATE) and re-check job/upload state.
        grant = conn.execute("select id,params,revoked_at from consent_grant where owner_id=%s and id=%s for share",
                             (owner, job["consent_grant_id"])).fetchone()
        jrow = conn.execute("select status, lease_token from job where id=%s for update", (job["id"],)).fetchone()
        if jrow["lease_token"] != job.get("lease_token"):
            # Another worker reclaimed this job after our lease expired (and may have finished it): write nothing.
            audit(conn, owner, "worker", "extract", "upload", upload_id, result="rejected", details={"why": "stale_lease"})
            return "stale_lease"
        up = conn.execute("select status,captured_at from upload where owner_id=%s and id=%s for update", (owner, upload_id)).fetchone()
        if not grant or grant["revoked_at"] is not None or jrow["status"] != "running" or up["status"] not in ("extracting", "received"):
            conn.execute("update job set status='cancelled' where id=%s", (job["id"],))
            if up and up["status"] in ("extracting", "received"):
                conn.execute("update upload set status='cancelled_consent' where id=%s", (upload_id,))
            audit(conn, owner, "worker", "extract", "upload", upload_id, result="rejected", details={"why": "consent_or_state"})
            return "discarded"
        tz = core.user_tz(conn, owner)
        rng = grant["params"] or {}
        v = ev.validate(result.fields, captured_at=up["captured_at"],
                        scan_from=date.fromisoformat(rng["scan_from"]) if rng.get("scan_from") else None,
                        scan_to=date.fromisoformat(rng["scan_to"]) if rng.get("scan_to") else None, tz=tz,
                        reference_at=up["captured_at"] or now_utc())
        # Store structured fields only, dropping anything outside the schema (no free-text memo channel).
        allowed = set(ev_fields())
        stored = {k: result.fields.get(k) for k in allowed if k in result.fields}
        conn.execute("""insert into extraction(owner_id,upload_id,model_id,schema_version,fields,field_states,latency_ms,input_tokens,output_tokens)
                        values (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                     (owner, upload_id, result.model_id, EXTRACTION_SCHEMA_VERSION, Jsonb(stored), Jsonb(v.field_states),
                      result.latency_ms, result.input_tokens, result.output_tokens))
        outcome = _route(conn, owner, upload_id, v, tz)
        conn.execute("update job set status='done', locked_until=null where id=%s and lease_token=%s", (job["id"], job["lease_token"]))
        audit(conn, owner, "worker", "extract", "upload", upload_id, details={"outcome": outcome, "model": result.model_id})
    return outcome


def ev_fields() -> list[str]:
    from finassist.providers import EXTRACTION_TOOL

    return list(EXTRACTION_TOOL["input_schema"]["properties"])


def _review(conn, owner, upload_id, reason: str, problems: list[str], candidates: list[str] | None = None) -> None:
    conn.execute("""insert into review_item(owner_id,upload_id,reason,problem_fields,candidate_txn_ids,status)
                    values (%s,%s,%s,%s,%s,'open')""", (owner, upload_id, reason, problems, candidates or []))
    conn.execute("update upload set status='needs_review' where id=%s", (upload_id,))


def _route(conn, owner, upload_id, v: ev.Validated, tz: str) -> str:
    if v.doc_type == "not_financial":
        conn.execute("update upload set status='rejected' where id=%s", (upload_id,))
        return "not_financial"
    if not v.critical_ok:
        bad = sorted(k for k, s in v.field_states.items() if s != "ok" and k in (*ev.CRITICAL, "due_date"))
        _review(conn, owner, upload_id, "missing_fields", bad or v.problems)
        return "needs_review"
    if v.doc_type == "bill":
        if not v.due_date:
            _review(conn, owner, upload_id, "missing_fields", ["due_date"])
            return "needs_review"
        if not core.active_consent(conn, owner, "auto_import", lock="share"):
            _review(conn, owner, upload_id, "confirm_import", [])
            return "needs_review"
        _create_bill_from(conn, owner, upload_id, v, actor="worker")
        conn.execute("update upload set status='imported' where id=%s", (upload_id,))
        return "bill_created"

    lock_owner_ledger(conn, owner)
    payee_key = normalize_payee(v.payee_display)
    ref = normalize_ref(v.bank_ref)
    rows = conn.execute("""select id,amount_satang,occurred_at,occurred_date,payee_key,bank_ref_norm,source,upload_id from txn
                           where owner_id=%s and deleted_at is null and (bank_ref_norm=%s or occurred_date between %s and %s)""",
                        (owner, ref, v.occurred_date - timedelta(days=1), v.occurred_date + timedelta(days=1))).fetchall()
    cands = [Candidate(str(r["id"]), "manual" if r["source"] == "manual" else "transfer_out", r["amount_satang"], r["occurred_at"],
                       r["occurred_date"].isoformat(), r["payee_key"], r["bank_ref_norm"]) for r in rows]
    # No image-hash signal: on templated slips distinct payments hash identically (see dedup.decide rule 4).
    new = Candidate("new", v.doc_type, v.amount_satang, v.occurred_at, v.occurred_date.isoformat(), payee_key, ref)
    d = decide(new, cands)
    if d.action == "same_payment":
        conn.execute("insert into txn_evidence(owner_id,txn_id,upload_id,relation) values (%s,%s,%s,'duplicate_image') on conflict do nothing",
                     (owner, d.match_id, upload_id))
        conn.execute("update upload set status='merged_duplicate' where id=%s", (upload_id,))
        return "merged_duplicate"
    if d.action == "receipt_evidence":
        _review(conn, owner, upload_id, "receipt_link", [], [d.match_id])
        return "needs_review"
    if d.action == "possible_duplicate":
        cand = [d.match_id] if d.match_id and _is_txn(conn, owner, d.match_id) else []
        _review(conn, owner, upload_id, "possible_duplicate", [d.reason], cand)
        return "needs_review"

    auto = core.active_consent(conn, owner, "auto_import", lock="share")
    if not auto:
        _review(conn, owner, upload_id, "confirm_import", [])
        return "needs_review"
    _insert_import_txn(conn, owner, upload_id, v, payee_key, ref, source="auto_import")
    conn.execute("update upload set status='imported' where id=%s", (upload_id,))
    return "imported"


def _is_txn(conn, owner, tid) -> bool:
    try:
        return conn.execute("select 1 from txn where owner_id=%s and id=%s", (owner, tid)).fetchone() is not None
    except psycopg.errors.InvalidTextRepresentation:
        return False


def _create_bill_from(conn, owner, upload_id, v: ev.Validated, actor: str) -> str:
    b = core.create_bill(conn, owner, {"biller": v.payee_display or "Unknown biller", "amount_due_satang": v.amount_satang,
                                       "due_date": v.due_date}, upload_id=upload_id)
    return str(b["id"])


def _insert_import_txn(conn, owner, upload_id, v: ev.Validated, payee_key, ref, source: str, ref_confirmed: bool = False) -> str:
    hist = [r["category_code"] for r in conn.execute(
        "select category_code from txn where owner_id=%s and payee_key=%s and category_state='confirmed' and deleted_at is null",
        (owner, payee_key)).fetchall()] if payee_key else []
    default = conn.execute("select category_code from payee_default where owner_id=%s and payee_key=%s", (owner, payee_key)).fetchone() if payee_key else None
    s = suggest(payee_key, user_default=default["category_code"] if default else None, confirmed_history=hist,
                seed=SEED_MERCHANTS, intermediary=is_intermediary(v.payee_display))
    account = core.main_account(conn, owner)
    t = conn.execute(
        """insert into txn(owner_id,account_id,kind,amount_satang,occurred_at,occurred_date,payment_status,amount_state,direction_state,
                           payee_display,payee_key,bank_ref_norm,bank_ref_confirmed,category_code,category_state,category_source,source,upload_id)
           values (%s,%s,%s,%s,%s,%s,%s,'confirmed','confirmed',%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
        (owner, account, v.kind, v.amount_satang, v.occurred_at, v.occurred_date, v.payment_status, v.payee_display, payee_key, ref,
         bool(ref and ref_confirmed), s.category_code, s.state, s.source, source, upload_id)).fetchone()
    conn.execute("insert into txn_evidence(owner_id,txn_id,upload_id,relation) values (%s,%s,%s,'primary')", (owner, t["id"], upload_id))
    bump_watermark(conn, owner)
    return str(t["id"])


# ---------------- review ----------------

def list_review(conn, owner_id) -> list[dict]:
    rows = conn.execute("""select r.id,r.upload_id,r.reason,r.problem_fields,r.candidate_txn_ids,r.created_at, e.fields
                           from review_item r left join lateral (select fields from extraction x where x.upload_id=r.upload_id
                           order by created_at desc limit 1) e on true
                           where r.owner_id=%s and r.status='open' order by r.created_at""", (owner_id,)).fetchall()
    out = []
    for r in rows:
        f = r.pop("fields") or {}
        # Only the fields the user needs to see or fix; never the raw image text.
        r["extracted"] = {k: f.get(k) for k in ("doc_type", "amount_text", "date_text", "time_text", "payee", "status")}
        out.append(r)
    return out


def resolve_review(conn, owner_id, item_id, body: dict) -> dict:
    """decision: accept (with optional corrected fields) | not_a_transaction | duplicate_of | link_receipt | distinct."""
    with conn.transaction():
        it = conn.execute("select * from review_item where owner_id=%s and id=%s and status='open' for update", (owner_id, item_id)).fetchone()
        if not it:
            raise _nf()
        up = conn.execute("select status,captured_at from upload where owner_id=%s and id=%s for update", (owner_id, it["upload_id"])).fetchone()
        if up["status"] == "deleted":
            raise _nf()
        decision = body["decision"]
        result: dict = {"decision": decision}
        if decision == "not_a_transaction":
            conn.execute("update upload set status='rejected' where id=%s", (it["upload_id"],))
        elif decision in ("duplicate_of", "link_receipt"):
            target = body.get("txn_id") or (it["candidate_txn_ids"][0] if it["candidate_txn_ids"] else None)
            if not target or not conn.execute("select 1 from txn where owner_id=%s and id=%s and deleted_at is null", (owner_id, target)).fetchone():
                raise _nf()
            rel = "receipt" if decision == "link_receipt" else "duplicate_image"
            conn.execute("insert into txn_evidence(owner_id,txn_id,upload_id,relation) values (%s,%s,%s,%s)", (owner_id, target, it["upload_id"], rel))
            conn.execute("update upload set status='merged_duplicate' where id=%s", (it["upload_id"],))
            result["txn_id"] = str(target)
        elif decision in ("accept", "distinct"):
            ex = conn.execute("select fields from extraction where owner_id=%s and upload_id=%s order by created_at desc limit 1",
                              (owner_id, it["upload_id"])).fetchone()
            fields = {**(ex["fields"] if ex else {}), **{k: v for k, v in (body.get("fields") or {}).items() if k in set(ev_fields())}}
            v = ev.validate(fields, captured_at=None, scan_from=None, scan_to=None, tz=core.user_tz(conn, owner_id))
            # The user is confirming in review: their values are accepted even if the date is old or the image was poor.
            if "implausible_date" in v.problems and v.field_states.get("occurred") == "conflicting":
                v.field_states["occurred"] = "ok"
            v.field_states.pop("readability", None)
            needed = ("amount", "occurred", "due_date") if v.doc_type == "bill" else ev.CRITICAL
            missing = [{"path": k, "issue": v.field_states.get(k, "missing")} for k in needed if v.field_states.get(k) != "ok"]
            if v.doc_type is None or missing:
                raise ApiError(400, "VALIDATION_FAILED", "Some required details are still missing.", fields=missing or [{"path": "doc_type", "issue": "missing"}])
            if v.doc_type == "bill":
                # A reviewed bill creates a bill, never a transaction; the unique (owner, upload) index makes a repeat impossible.
                try:
                    with conn.transaction():
                        result["bill_id"] = _create_bill_from(conn, owner_id, it["upload_id"], v, actor="user")
                except psycopg.errors.UniqueViolation:
                    raise ApiError(409, "ALREADY_IMPORTED", "A bill from this image already exists.") from None
            else:
                lock_owner_ledger(conn, owner_id)
                ref = normalize_ref(v.bank_ref)
                user_ref = "bank_ref" in (body.get("fields") or {})
                if decision == "accept" and ref and conn.execute(
                        "select 1 from txn where owner_id=%s and bank_ref_norm=%s and deleted_at is null", (owner_id, ref)).fetchone():
                    raise ApiError(409, "POSSIBLE_DUPLICATE", "A record with this bank reference already exists; choose duplicate_of or distinct.")
                try:
                    with conn.transaction():
                        result["txn_id"] = _insert_import_txn(conn, owner_id, it["upload_id"], v, normalize_payee(v.payee_display), ref,
                                                              source="review_import", ref_confirmed=user_ref)
                except psycopg.errors.UniqueViolation:
                    raise ApiError(409, "POSSIBLE_DUPLICATE", "Another record already has this confirmed bank reference.") from None
            conn.execute("update upload set status='imported' where id=%s", (it["upload_id"],))
        else:
            raise ApiError(400, "VALIDATION_FAILED", "Unknown decision.")
        conn.execute("update review_item set status='resolved', resolution=%s, resolved_at=%s where id=%s", (decision, now_utc(), item_id))
        bump_watermark(conn, owner_id)
        audit(conn, owner_id, "user", "review_resolve", "review_item", item_id, details={"decision": decision})
    return result


def batch_categorise(conn, owner_id, payee_key: str, category: str, set_default: bool) -> dict:
    with conn.transaction():
        if not conn.execute("select 1 from category where code=%s", (category,)).fetchone():
            raise ApiError(400, "VALIDATION_FAILED", "Unknown category.")
        n = conn.execute("""update txn set category_code=%s, category_state='confirmed', category_source='user', version=version+1
                            where owner_id=%s and payee_key=%s and deleted_at is null and category_state<>'confirmed'""",
                         (category, owner_id, payee_key)).rowcount
        if set_default:
            conn.execute("""insert into payee_default(owner_id,payee_key,category_code) values (%s,%s,%s)
                            on conflict (owner_id,payee_key) do update set category_code=excluded.category_code, set_at=now()""",
                         (owner_id, payee_key, category))
        bump_watermark(conn, owner_id)
        audit(conn, owner_id, "user", "batch_categorise", "payee", None, details={"count": n, "set_default": set_default})
    return {"updated": n}


def uncategorised_groups(conn, owner_id) -> list[dict]:
    """Batch review: unclassified spending grouped by payee, largest first."""
    return conn.execute("""select payee_key, min(payee_display) payee_display, count(*) n, sum(amount_satang) total_satang
                           from txn where owner_id=%s and deleted_at is null and kind='expense' and category_state='unclassified'
                           group by payee_key order by sum(amount_satang) desc limit 20""", (owner_id,)).fetchall()


def scan_status(conn, owner_id) -> dict:
    counts = {r["status"]: r["n"] for r in conn.execute("select status, count(*) n from upload where owner_id=%s group by status", (owner_id,)).fetchall()}
    last = conn.execute("""select max(at) t from audit_event where owner_id=%s and action='extract' and result='ok'""", (owner_id,)).fetchone()["t"]
    paused = core.active_consent(conn, owner_id, "photo_processing") is None
    return {"counts": counts, "last_successful_processing_at": last, "processing_allowed": not paused}
