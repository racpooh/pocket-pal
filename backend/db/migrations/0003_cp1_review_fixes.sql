-- 0003 — fixes from Codex CP1 review (15 Oct 2026).
BEGIN;

-- #5 OCR reference vs confirmed reference. Only a confirmed reference (typed by the user, or confirmed in review)
-- is unique per owner. A reference read by the model is evidence, not identity.
ALTER TABLE txn ADD COLUMN bank_ref_confirmed boolean NOT NULL DEFAULT false;
DROP INDEX txn_bank_ref_uq;
CREATE UNIQUE INDEX txn_bank_ref_confirmed_uq ON txn (owner_id, bank_ref_norm)
    WHERE bank_ref_norm IS NOT NULL AND bank_ref_confirmed AND deleted_at IS NULL;
CREATE INDEX txn_owner_ref ON txn (owner_id, bank_ref_norm) WHERE bank_ref_norm IS NOT NULL AND deleted_at IS NULL;

-- #3 image deletion is two-phase: the row keeps object_key until the object store confirms deletion.
ALTER TABLE upload ADD COLUMN object_purged_at timestamptz;
CREATE INDEX upload_purge_pending ON upload (owner_id) WHERE status = 'deleted' AND object_key IS NOT NULL;

-- #4 a reviewed bill image creates at most one bill.
CREATE UNIQUE INDEX bill_one_per_upload ON bill (owner_id, upload_id) WHERE upload_id IS NOT NULL;

COMMIT;
