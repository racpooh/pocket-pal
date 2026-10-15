-- 0005: approval cards (docs/design/05 §Proposals, 02 FI-31..FI-33).
-- The card shown to the user is computed by deterministic code when the proposal is created, stored with the
-- proposal and bound to the approval by card_hash. Proposal content never changes after insert; an edit creates a
-- new proposal (edited_from) and supersedes the old one.
BEGIN;

ALTER TABLE proposal ADD COLUMN card jsonb;
ALTER TABLE proposal ADD COLUMN card_hash bytea CHECK (card_hash IS NULL OR length(card_hash) = 32);
ALTER TABLE proposal ADD COLUMN edited_from uuid;
ALTER TABLE proposal ADD CONSTRAINT proposal_card_pair CHECK ((card IS NULL) = (card_hash IS NULL));
ALTER TABLE proposal ADD CONSTRAINT proposal_edited_from_fk FOREIGN KEY (owner_id, edited_from) REFERENCES proposal (owner_id, id);
CREATE INDEX proposal_owner_status ON proposal (owner_id, status, created_at DESC);

CREATE FUNCTION proposal_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.owner_id IS DISTINCT FROM OLD.owner_id OR NEW.kind IS DISTINCT FROM OLD.kind
       OR NEW.payload IS DISTINCT FROM OLD.payload OR NEW.payload_hash IS DISTINCT FROM OLD.payload_hash
       OR NEW.card IS DISTINCT FROM OLD.card OR NEW.card_hash IS DISTINCT FROM OLD.card_hash
       OR NEW.base_plan_id IS DISTINCT FROM OLD.base_plan_id OR NEW.base_plan_version IS DISTINCT FROM OLD.base_plan_version
       OR NEW.base_goal_version IS DISTINCT FROM OLD.base_goal_version
       OR NEW.base_data_watermark IS DISTINCT FROM OLD.base_data_watermark
       OR NEW.created_by IS DISTINCT FROM OLD.created_by OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
       OR NEW.edited_from IS DISTINCT FROM OLD.edited_from THEN
        RAISE EXCEPTION 'proposal content is immutable' USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.status <> 'pending' AND NEW.status IS DISTINCT FROM OLD.status THEN
        RAISE EXCEPTION 'proposal status % is final', OLD.status USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER proposal_guard BEFORE UPDATE ON proposal FOR EACH ROW EXECUTE FUNCTION proposal_guard();

COMMIT;
