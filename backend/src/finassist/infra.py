"""Infrastructure helpers: DB connections, hashing, audit, idempotency, watermark.

Services own their SQL in v1 (no separate repository layer yet); every owner-table
query takes owner_id from the caller, which gets it from the verified session.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from contextlib import contextmanager
from typing import Any, Callable, Iterator

import psycopg
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from finassist.api.errors import ApiError

_ph = PasswordHasher()  # argon2id with library defaults


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(hashed: str, pw: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)  # 256 bits


def sha256(data: bytes | str) -> bytes:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).digest()


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


class Database:
    def __init__(self, url: str) -> None:
        self.url = url

    @contextmanager
    def connect(self) -> Iterator[psycopg.Connection]:
        # autocommit: every `with conn.transaction()` block is a real transaction that commits on exit,
        # independent of when FastAPI tears down dependencies.
        with psycopg.connect(self.url, row_factory=dict_row, autocommit=True) as conn:
            yield conn


def set_owner(conn: psycopg.Connection, owner_id) -> None:
    """Bind this connection to the verified owner for Postgres RLS (0002_rls.sql). Session-level:
    connections are per request and never shared across owners."""
    conn.execute("select set_config('app.owner_id', %s, false)", (str(owner_id),))


def audit(conn: psycopg.Connection, owner_id, actor: str, action: str, subject_type: str, subject_id=None,
          result: str = "ok", request_id: str | None = None, details: dict | None = None) -> None:
    """details must never contain image content, OCR text, tokens or free-text descriptions."""
    conn.execute(
        """insert into audit_event(owner_id,actor,action,subject_type,subject_id,result,request_id,details)
           values (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (owner_id, actor, action, subject_type, subject_id, result, request_id, Jsonb(details or {})),
    )


def bump_watermark(conn: psycopg.Connection, owner_id) -> int:
    row = conn.execute(
        """insert into owner_watermark(owner_id,value) values (%s,1)
           on conflict (owner_id) do update set value = owner_watermark.value + 1 returning value""",
        (owner_id,),
    ).fetchone()
    return row["value"]


def current_watermark(conn: psycopg.Connection, owner_id) -> int:
    row = conn.execute("select value from owner_watermark where owner_id=%s", (owner_id,)).fetchone()
    return row["value"] if row else 0


def lock_owner_ledger(conn: psycopg.Connection, owner_id) -> None:
    """FI-30: serialise 'find candidates → insert' per owner (transaction-scoped)."""
    conn.execute("select pg_advisory_xact_lock(hashtextextended(%s::text, 7))", (str(owner_id),))


def lock_owner_for_approval(conn: psycopg.Connection, owner_id) -> int:
    """SI-3 (Codex CP2 #2): make "check proposal against data → apply" a section no ledger change can interleave.
    Lock order is the same as every ledger writer: (1) the per-owner ledger advisory lock, (2) the owner_watermark
    row. Every ledger change bumps that row inside its own transaction, so a writer that has not committed holds the
    row and this call waits for it (then sees the new value → stale); a writer that starts later waits for the
    approval to commit. Returns the locked watermark value."""
    lock_owner_ledger(conn, owner_id)
    conn.execute("insert into owner_watermark(owner_id,value) values (%s,0) on conflict (owner_id) do nothing", (owner_id,))
    return conn.execute("select value from owner_watermark where owner_id=%s for update", (owner_id,)).fetchone()["value"]


def idempotent(conn: psycopg.Connection, owner_id, key: str | None, scope: str, body: Any,
               fn: Callable[[psycopg.Connection], tuple[int, Any]]) -> tuple[int, Any]:
    """SI-4. Runs fn inside one transaction with the idempotency record.

    - first call: stores (key, request hash, response) atomically with the effect
    - same key + same body: returns the stored response, no new effect
    - same key + different body: 422
    - concurrent duplicate: blocks on the unique key until the first commits, then replays
    If fn raises, nothing is stored and the client may retry with the same key.
    """
    if not key:
        raise ApiError(400, "IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key header is required.")
    try:
        import uuid as _uuid

        key_uuid = _uuid.UUID(key)
    except ValueError:
        raise ApiError(400, "VALIDATION_FAILED", "Idempotency-Key must be a UUID.") from None
    req_hash = sha256(scope + "\n" + canonical_json(body))
    with conn.transaction():
        inserted = conn.execute(
            """insert into idempotency_key(owner_id,key,request_hash) values (%s,%s,%s)
               on conflict do nothing returning key""",
            (owner_id, key_uuid, req_hash),
        ).fetchone()
        if inserted is None:
            row = conn.execute(
                "select request_hash,response_code,response_body from idempotency_key where owner_id=%s and key=%s",
                (owner_id, key_uuid),
            ).fetchone()
            if bytes(row["request_hash"]) != req_hash:
                raise ApiError(422, "IDEMPOTENCY_KEY_REUSED", "This Idempotency-Key was used with a different request.")
            return row["response_code"], row["response_body"]
        code, resp = fn(conn)
        resp = json.loads(json.dumps(resp, default=str))
        conn.execute(
            "update idempotency_key set response_code=%s, response_body=%s where owner_id=%s and key=%s",
            (code, Jsonb(resp), owner_id, key_uuid),
        )
        return code, resp
