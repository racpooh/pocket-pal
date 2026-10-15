-- 0007 (Codex CP2 re-review): close the hard-delete gap in 0006.
-- 0006 only noticed a lone leg when its partner was still present as a soft-deleted row, so `DELETE FROM txn`
-- of one leg passed. Rule now (FI-13a): a transfer_group_id means "transfer between two tracked own accounts", so a
-- group is either empty (both legs gone) or exactly one transfer_out + one transfer_in, both live, identical in
-- amount, status, states and time. A transfer to an untracked/external account is a single transfer_out leg WITHOUT
-- a group id (02 §3) and is not affected. Checked at commit (deferred), for the old and the new group when
-- transfer_group_id or owner_id changes.
BEGIN;

CREATE OR REPLACE FUNCTION txn_transfer_group_ok(oid uuid, gid uuid) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    n_live int; n_deleted int; n_out int; n_in int; n_variants int;
BEGIN
    IF gid IS NULL THEN
        RETURN;
    END IF;
    SELECT count(*) FILTER (WHERE deleted_at IS NULL),
           count(*) FILTER (WHERE deleted_at IS NOT NULL),
           count(*) FILTER (WHERE deleted_at IS NULL AND kind = 'transfer_out'),
           count(*) FILTER (WHERE deleted_at IS NULL AND kind = 'transfer_in'),
           count(DISTINCT (amount_satang, payment_status, amount_state, direction_state, occurred_date, occurred_at))
               FILTER (WHERE deleted_at IS NULL)
      INTO n_live, n_deleted, n_out, n_in, n_variants
      FROM txn WHERE owner_id = oid AND transfer_group_id = gid;
    IF n_live = 0 THEN
        RETURN;  -- whole transfer deleted (soft or hard)
    END IF;
    IF n_live <> 2 OR n_out <> 1 OR n_in <> 1 OR n_variants <> 1 OR n_deleted <> 0 THEN
        RAISE EXCEPTION 'transfer group % is inconsistent: % live leg(s) (out %, in %), % variant(s), % deleted',
            gid, n_live, n_out, n_in, n_variants, n_deleted USING ERRCODE = 'check_violation';
    END IF;
END $$;

CREATE OR REPLACE FUNCTION txn_transfer_group_check() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        PERFORM txn_transfer_group_ok(OLD.owner_id, OLD.transfer_group_id);
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') AND (TG_OP = 'INSERT' OR NEW.owner_id IS DISTINCT FROM OLD.owner_id
                                          OR NEW.transfer_group_id IS DISTINCT FROM OLD.transfer_group_id) THEN
        PERFORM txn_transfer_group_ok(NEW.owner_id, NEW.transfer_group_id);
    END IF;
    RETURN NULL;
END $$;

-- 0006's trigger already calls txn_transfer_group_check() for INSERT/UPDATE/DELETE, deferred; the function body
-- above replaces its logic. Recreate it anyway so this migration is self-describing.
DROP TRIGGER IF EXISTS txn_transfer_group_consistent ON txn;
CREATE CONSTRAINT TRIGGER txn_transfer_group_consistent
    AFTER INSERT OR UPDATE OR DELETE ON txn
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION txn_transfer_group_check();

COMMIT;
