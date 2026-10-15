-- 0006 (Codex CP2 #1): a transfer's legs must agree on everything that decides whether and when they count.
-- Checked at COMMIT (deferred), so a service that updates both legs in one transaction passes, and any path that
-- changes or deletes one leg alone — including code written later — fails the whole transaction.
BEGIN;

CREATE FUNCTION txn_transfer_group_check() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    gid uuid := COALESCE(NEW.transfer_group_id, OLD.transfer_group_id);
    oid uuid := COALESCE(NEW.owner_id, OLD.owner_id);
    n_live int; n_out int; n_in int; n_variants int;
BEGIN
    IF gid IS NULL THEN
        RETURN NULL;
    END IF;
    SELECT count(*) FILTER (WHERE deleted_at IS NULL),
           count(*) FILTER (WHERE deleted_at IS NULL AND kind = 'transfer_out'),
           count(*) FILTER (WHERE deleted_at IS NULL AND kind = 'transfer_in'),
           count(DISTINCT (amount_satang, payment_status, amount_state, direction_state, occurred_date, occurred_at))
               FILTER (WHERE deleted_at IS NULL)
      INTO n_live, n_out, n_in, n_variants
      FROM txn WHERE owner_id = oid AND transfer_group_id = gid;
    IF n_out > 1 OR n_in > 1 OR n_variants > 1
       OR (n_live = 1 AND EXISTS (SELECT 1 FROM txn WHERE owner_id = oid AND transfer_group_id = gid AND deleted_at IS NOT NULL)) THEN
        RAISE EXCEPTION 'transfer group % is inconsistent (legs must match and be deleted together)', gid
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END $$;

CREATE CONSTRAINT TRIGGER txn_transfer_group_consistent
    AFTER INSERT OR UPDATE OR DELETE ON txn
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION txn_transfer_group_check();

COMMIT;
