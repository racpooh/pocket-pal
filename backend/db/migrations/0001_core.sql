-- 0001_core.sql — DRAFT schema for Codex review (CP0). Postgres 16.
-- Encodes the DB-level parts of FI-* (docs/design/02) and SI-* (docs/design/03).
-- Ownership: every owner table has owner_id and UNIQUE (owner_id, id); children
-- reference parents with composite FKs so a row cannot point to another owner's row.
-- RLS policies are added in a later migration (CP3), not here.

BEGIN;

CREATE TABLE app_user (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email         text NOT NULL,
    password_hash text NOT NULL,                       -- argon2id
    timezone      text NOT NULL DEFAULT 'Asia/Bangkok',
    created_at    timestamptz NOT NULL DEFAULT now(),
    deleted_at    timestamptz
);
CREATE UNIQUE INDEX app_user_email_uq ON app_user (lower(email)) WHERE deleted_at IS NULL;

CREATE TABLE user_session (
    token_sha256 bytea PRIMARY KEY CHECK (length(token_sha256) = 32), -- only the hash is stored
    owner_id     uuid NOT NULL REFERENCES app_user(id),
    created_at   timestamptz NOT NULL DEFAULT now(),
    expires_at   timestamptz NOT NULL,
    revoked_at   timestamptz
);

-- Income schedule and onboarding inputs (R1.2)
CREATE TABLE income_schedule (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id           uuid NOT NULL REFERENCES app_user(id),
    amount_satang      bigint NOT NULL CHECK (amount_satang > 0),
    frequency          text NOT NULL CHECK (frequency IN ('monthly','biweekly','weekly','irregular')),
    next_income_date   date NOT NULL,
    version            int NOT NULL DEFAULT 1,
    UNIQUE (owner_id, id)
);

CREATE TABLE essential_expense (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id       uuid NOT NULL REFERENCES app_user(id),
    name           text NOT NULL,
    amount_satang  bigint NOT NULL CHECK (amount_satang > 0),
    frequency      text NOT NULL CHECK (frequency IN ('monthly','weekly','once')),
    due_day        smallint CHECK (due_day BETWEEN 1 AND 31),
    UNIQUE (owner_id, id)
);

-- Consent (R1.3, R9.6, SI-5). New grant = new row; never reactivated.
CREATE TABLE consent_grant (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    uuid NOT NULL REFERENCES app_user(id),
    scope       text NOT NULL CHECK (scope IN ('photo_processing','auto_import','chat_history_retention')),
    version     text NOT NULL,              -- version of the consent text shown
    params      jsonb NOT NULL DEFAULT '{}', -- e.g. scan date range
    granted_at  timestamptz NOT NULL DEFAULT now(),
    revoked_at  timestamptz,
    UNIQUE (owner_id, id)
);
CREATE UNIQUE INDEX consent_one_active_per_scope ON consent_grant (owner_id, scope) WHERE revoked_at IS NULL;

-- Accounts and balance anchors (FI-7..FI-10)
CREATE TABLE account (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id  uuid NOT NULL REFERENCES app_user(id),
    name      text NOT NULL,
    kind      text NOT NULL CHECK (kind IN ('spending','savings','other')),
    tracked   boolean NOT NULL DEFAULT true,
    UNIQUE (owner_id, id)
);

CREATE TABLE balance_observation (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id       uuid NOT NULL,
    account_id     uuid NOT NULL,
    amount_satang  bigint NOT NULL,          -- may be negative (overdraft); it is an observation
    as_of          timestamptz NOT NULL,
    as_of_is_date_only boolean NOT NULL DEFAULT false,
    created_at     timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (owner_id, account_id) REFERENCES account (owner_id, id),
    UNIQUE (owner_id, id)
);

-- Category taxonomy (global) and pockets (per owner). D5: category -> pocket mapping.
CREATE TABLE category (
    code  text PRIMARY KEY,      -- e.g. 'food', 'transport'
    label text NOT NULL
);

CREATE TABLE pocket (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id  uuid NOT NULL REFERENCES app_user(id),
    name      text NOT NULL,
    sort_key  int NOT NULL DEFAULT 0,
    archived_at timestamptz,
    UNIQUE (owner_id, id),
    UNIQUE (owner_id, name)
);

CREATE TABLE pocket_category_map (
    owner_id      uuid NOT NULL,
    category_code text NOT NULL REFERENCES category(code),
    pocket_id     uuid NOT NULL,
    PRIMARY KEY (owner_id, category_code),
    FOREIGN KEY (owner_id, pocket_id) REFERENCES pocket (owner_id, id)
);

-- Budget plan per period; version is the optimistic-concurrency token for proposals (SI-3)
CREATE TABLE budget_plan (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id      uuid NOT NULL REFERENCES app_user(id),
    period_start  date NOT NULL,
    period_end    date NOT NULL,          -- exclusive
    buffer_satang bigint NOT NULL DEFAULT 0 CHECK (buffer_satang >= 0),
    version       int NOT NULL DEFAULT 1,
    CHECK (period_start < period_end),
    UNIQUE (owner_id, id),
    UNIQUE (owner_id, period_start)
);

CREATE TABLE pocket_allocation (
    owner_id          uuid NOT NULL,
    plan_id           uuid NOT NULL,
    pocket_id         uuid NOT NULL,
    allocation_satang bigint NOT NULL CHECK (allocation_satang >= 0),  -- FI-17
    PRIMARY KEY (plan_id, pocket_id),
    FOREIGN KEY (owner_id, plan_id) REFERENCES budget_plan (owner_id, id),
    FOREIGN KEY (owner_id, pocket_id) REFERENCES pocket (owner_id, id)
);

-- Uploads and extraction (R2.*, R10.2, R10.3)
CREATE TABLE upload (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id      uuid NOT NULL REFERENCES app_user(id),
    consent_grant_id uuid NOT NULL,
    sha256        bytea NOT NULL CHECK (length(sha256) = 32),
    phash         bigint,
    object_key    text,                       -- null once the image is deleted
    mime          text NOT NULL CHECK (mime IN ('image/jpeg','image/png')),
    bytes         int NOT NULL CHECK (bytes > 0 AND bytes <= 8388608),
    captured_at   timestamptz,
    status        text NOT NULL CHECK (status IN ('received','extracting','validated','needs_review',
                    'imported','rejected','merged_duplicate','extract_failed','cancelled_consent','deleted')),
    created_at    timestamptz NOT NULL DEFAULT now(),
    deleted_at    timestamptz,
    FOREIGN KEY (owner_id, consent_grant_id) REFERENCES consent_grant (owner_id, id),
    UNIQUE (owner_id, id)
);
CREATE UNIQUE INDEX upload_sha_uq ON upload (owner_id, sha256) WHERE status <> 'deleted';

CREATE TABLE extraction (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id      uuid NOT NULL,
    upload_id     uuid NOT NULL,
    model_id      text NOT NULL,              -- provider/model identifier, or 'fake:<name>'
    schema_version text NOT NULL,
    fields        jsonb NOT NULL,             -- structured output only; no raw OCR dump
    field_states  jsonb NOT NULL,             -- {"amount":"ok|missing|conflicting", ...}
    latency_ms    int,
    input_tokens  int,
    output_tokens int,
    cost_microusd bigint,
    created_at    timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (owner_id, upload_id) REFERENCES upload (owner_id, id),
    UNIQUE (owner_id, id)
);

-- Transactions (FI-1, FI-11..FI-15, FI-28..FI-30)
CREATE TABLE txn (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id        uuid NOT NULL,
    account_id      uuid NOT NULL,
    kind            text NOT NULL CHECK (kind IN ('expense','income','refund','transfer_out','transfer_in')),
    amount_satang   bigint NOT NULL CHECK (amount_satang > 0),
    occurred_at     timestamptz,
    occurred_date   date NOT NULL,            -- local business date (FI-5)
    payment_status  text NOT NULL CHECK (payment_status IN ('completed','pending','failed','unknown')),
    amount_state    text NOT NULL CHECK (amount_state IN ('confirmed','uncertain')),
    direction_state text NOT NULL CHECK (direction_state IN ('confirmed','uncertain')),
    payee_display   text,
    payee_key       text,
    bank_ref_norm   text,
    category_code   text REFERENCES category(code),
    category_state  text NOT NULL DEFAULT 'unclassified'
                      CHECK (category_state IN ('unclassified','predicted','confirmed')),
    category_source text CHECK (category_source IN ('user','user_default','history','seed')),
    source          text NOT NULL CHECK (source IN ('manual','auto_import','review_import')),
    upload_id       uuid,
    transfer_group_id uuid,
    refund_of       uuid,
    description     text,
    version         int NOT NULL DEFAULT 1,
    created_at      timestamptz NOT NULL DEFAULT now(),
    deleted_at      timestamptz,
    FOREIGN KEY (owner_id, account_id) REFERENCES account (owner_id, id),
    FOREIGN KEY (owner_id, upload_id) REFERENCES upload (owner_id, id),
    FOREIGN KEY (owner_id, refund_of) REFERENCES txn (owner_id, id),
    UNIQUE (owner_id, id),
    -- category consistency
    CHECK ((category_state = 'unclassified') = (category_code IS NULL)),
    CHECK ((category_state = 'unclassified') = (category_source IS NULL)),
    CHECK (category_state <> 'confirmed' OR category_source = 'user'),
    CHECK (refund_of IS NULL OR kind = 'refund'),
    CHECK (transfer_group_id IS NULL OR kind IN ('transfer_out','transfer_in')),
    CHECK (source = 'manual' OR upload_id IS NOT NULL)
);
-- FI-29: one live transaction per bank reference per owner
CREATE UNIQUE INDEX txn_bank_ref_uq ON txn (owner_id, bank_ref_norm)
    WHERE bank_ref_norm IS NOT NULL AND deleted_at IS NULL;
CREATE INDEX txn_owner_date ON txn (owner_id, occurred_date) WHERE deleted_at IS NULL;
CREATE INDEX txn_owner_payee ON txn (owner_id, payee_key) WHERE deleted_at IS NULL;

-- Explicit links: receipt-as-evidence, confirmed duplicates
CREATE TABLE txn_evidence (
    owner_id   uuid NOT NULL,
    txn_id     uuid NOT NULL,
    upload_id  uuid NOT NULL,
    relation   text NOT NULL CHECK (relation IN ('primary','receipt','duplicate_image')),
    PRIMARY KEY (txn_id, upload_id),
    FOREIGN KEY (owner_id, txn_id) REFERENCES txn (owner_id, id),
    FOREIGN KEY (owner_id, upload_id) REFERENCES upload (owner_id, id)
);
-- An image is evidence of at most one transaction
CREATE UNIQUE INDEX txn_evidence_upload_uq ON txn_evidence (upload_id);

CREATE TABLE payee_default (
    owner_id      uuid NOT NULL REFERENCES app_user(id),
    payee_key     text NOT NULL,
    category_code text NOT NULL REFERENCES category(code),
    set_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (owner_id, payee_key)       -- set only by explicit user action
);

-- Review queue (R2.6)
CREATE TABLE review_item (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    uuid NOT NULL,
    upload_id   uuid NOT NULL,
    reason      text NOT NULL CHECK (reason IN ('missing_fields','possible_duplicate','confirm_import','receipt_link','unpaid_bill_match')),
    problem_fields text[] NOT NULL,
    candidate_txn_ids uuid[] NOT NULL DEFAULT '{}',
    status      text NOT NULL CHECK (status IN ('open','resolved','dismissed')),
    resolution  text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    FOREIGN KEY (owner_id, upload_id) REFERENCES upload (owner_id, id),
    UNIQUE (owner_id, id)
);
CREATE UNIQUE INDEX review_one_open_per_upload ON review_item (upload_id) WHERE status = 'open';

-- Bills (FI-19..FI-22)
CREATE TABLE bill (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id       uuid NOT NULL REFERENCES app_user(id),
    biller         text NOT NULL,
    amount_due_satang bigint NOT NULL CHECK (amount_due_satang > 0),
    due_date       date NOT NULL,
    status         text NOT NULL CHECK (status IN ('unpaid','paid','cancelled')),
    essential_expense_id uuid,
    upload_id      uuid,
    version        int NOT NULL DEFAULT 1,
    FOREIGN KEY (owner_id, essential_expense_id) REFERENCES essential_expense (owner_id, id),
    FOREIGN KEY (owner_id, upload_id) REFERENCES upload (owner_id, id),
    UNIQUE (owner_id, id)
);

CREATE TABLE bill_payment_link (
    owner_id  uuid NOT NULL,
    bill_id   uuid NOT NULL,
    txn_id    uuid NOT NULL,
    linked_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (bill_id),                  -- one payment per bill (FI-21)
    UNIQUE (txn_id),                        -- a payment settles at most one bill (FI-20)
    FOREIGN KEY (owner_id, bill_id) REFERENCES bill (owner_id, id),
    FOREIGN KEY (owner_id, txn_id) REFERENCES txn (owner_id, id)
);

-- Goals (R6.*)
CREATE TABLE goal (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id        uuid NOT NULL REFERENCES app_user(id),
    name            text NOT NULL,
    target_satang   bigint NOT NULL CHECK (target_satang > 0),
    saved_satang    bigint NOT NULL DEFAULT 0 CHECK (saved_satang >= 0),
    deadline        date NOT NULL,
    contribution_satang_per_period bigint NOT NULL DEFAULT 0 CHECK (contribution_satang_per_period >= 0),
    status          text NOT NULL CHECK (status IN ('active','achieved','archived')),
    version         int NOT NULL DEFAULT 1,
    UNIQUE (owner_id, id)
);

-- Proposals and approvals (SI-3)
CREATE TABLE proposal (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id         uuid NOT NULL REFERENCES app_user(id),
    kind             text NOT NULL CHECK (kind IN ('reallocate','budget_plan','goal_create','goal_update')),
    payload          jsonb NOT NULL,
    payload_hash     bytea NOT NULL CHECK (length(payload_hash) = 32),
    base_plan_id     uuid,
    base_plan_version int,
    base_goal_version int,
    base_data_watermark bigint NOT NULL,
    created_by       text NOT NULL CHECK (created_by IN ('agent','user')),
    status           text NOT NULL CHECK (status IN ('pending','applied','stale','superseded','cancelled','expired')),
    superseded_by    uuid,
    expires_at       timestamptz NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    decided_at       timestamptz,
    FOREIGN KEY (owner_id, base_plan_id) REFERENCES budget_plan (owner_id, id),
    UNIQUE (owner_id, id)
);

-- Monotonic per-owner data watermark, bumped by any ledger change (proposal staleness)
CREATE TABLE owner_watermark (
    owner_id  uuid PRIMARY KEY REFERENCES app_user(id),
    value     bigint NOT NULL DEFAULT 0
);

-- Idempotency (SI-4)
CREATE TABLE idempotency_key (
    owner_id      uuid NOT NULL REFERENCES app_user(id),
    key           uuid NOT NULL,
    request_hash  bytea NOT NULL CHECK (length(request_hash) = 32),
    response_code int,
    response_body jsonb,
    created_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (owner_id, key)
);

-- Jobs (outbox + queue in one table; no broker)
CREATE TABLE job (
    id               bigserial PRIMARY KEY,
    owner_id         uuid NOT NULL REFERENCES app_user(id),
    kind             text NOT NULL CHECK (kind IN ('extract','purge_upload','purge_owner_imports')),
    subject_id       uuid NOT NULL,
    consent_grant_id uuid,
    status           text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','done','dead','cancelled')),
    attempts         int NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    run_after        timestamptz NOT NULL DEFAULT now(),
    locked_until     timestamptz,
    last_error_code  text,
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX job_ready ON job (run_after) WHERE status = 'queued';
CREATE UNIQUE INDEX job_one_live_per_subject ON job (kind, subject_id) WHERE status IN ('queued','running');

-- Chat history (R8.1, R10.1) — retention governed by consent
CREATE TABLE chat_message (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id   uuid NOT NULL REFERENCES app_user(id),
    role       text NOT NULL CHECK (role IN ('user','assistant','tool')),
    content    jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Audit (R9.8). details must be redacted: no image content, OCR text or tokens.
CREATE TABLE audit_event (
    id           bigserial PRIMARY KEY,
    owner_id     uuid NOT NULL,
    actor        text NOT NULL CHECK (actor IN ('user','agent','worker','system')),
    action       text NOT NULL,
    subject_type text NOT NULL,
    subject_id   uuid,
    result       text NOT NULL CHECK (result IN ('ok','rejected','error')),
    request_id   text,
    details      jsonb NOT NULL DEFAULT '{}',
    at           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_owner_at ON audit_event (owner_id, at);

INSERT INTO category (code, label) VALUES
  ('food','Food & drinks'), ('transport','Transport'), ('shopping','Shopping'),
  ('entertainment','Entertainment'), ('bills','Bills & utilities'), ('health','Health'),
  ('education','Education'), ('travel','Travel'), ('transfer_people','Transfers to people'),
  ('other','Other');

COMMIT;
