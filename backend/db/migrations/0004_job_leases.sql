-- 0004 — job leases (Codex CP1 re-review #3): a crashed worker's job is reclaimed after its lease expires,
-- and every write by a worker is conditional on the lease token it holds, so a late/old worker cannot overwrite.
BEGIN;
ALTER TABLE job ADD COLUMN lease_token uuid;
CREATE INDEX job_expired_lease ON job (locked_until) WHERE status = 'running';
COMMIT;
