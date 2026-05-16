-- =============================================================================
-- Migration: 001_phase_1a_initial_schema
-- Phase 1A — BrandPulse multi-tenant foundation
--
-- Tables created:
--   tenants            core tenant registry
--   tenant_users       maps Supabase Auth users to tenants (RLS anchor)
--   tenant_config      per-tenant API tokens (Fernet-encrypted) + branch list
--   billplz_bills      Billplz FPX payment records
--   review_snapshots   weekly Google Maps review/rating snapshots per branch
--   payment_events     immutable audit trail for every subscription state change
--
-- Security:
--   RLS enabled on all tables.
--   tenant isolation uses auth.uid() joined to tenant_users — NOT
--   auth.jwt() ->> 'tenant_id' (Supabase default JWTs carry no tenant_id
--   claim; that pattern silently returns zero rows on every query).
--
-- Token encryption:
--   instagram_token_enc / facebook_token_enc are Fernet-encrypted at the
--   application layer using TENANT_SECRET_KEY env var. Supabase Vault deferred
--   to Month 2-3 (requires Pro plan).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. tenants
-- ---------------------------------------------------------------------------
CREATE TABLE tenants (
  id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  slug             TEXT        UNIQUE NOT NULL
                               CHECK (slug ~ '^[a-z0-9-]{3,50}$'),
  name             TEXT        NOT NULL,
  email            TEXT        NOT NULL,
  phone            TEXT,
  status           TEXT        NOT NULL DEFAULT 'created'
                               CHECK (status IN ('created','active','past_due','cancelled')),
  plan             TEXT        NOT NULL DEFAULT 'starter'
                               CHECK (plan IN ('starter','growth','pro')),
  consent_given_at TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;

-- Tenants row is selected via the tenant_users join; no direct USING clause
-- on tenant_id needed here because tenant_users.tenant_id links the two.
-- Users can only see the tenant they belong to.
CREATE POLICY tenant_isolation ON tenants
  USING (id = (
    SELECT tenant_id FROM tenant_users WHERE id = auth.uid()
  ));

-- ---------------------------------------------------------------------------
-- 2. tenant_users  (maps to Supabase Auth users)
-- ---------------------------------------------------------------------------
CREATE TABLE tenant_users (
  id          UUID        PRIMARY KEY,   -- same UUID as auth.users.id
  tenant_id   UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  email       TEXT        NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, email)
);

ALTER TABLE tenant_users ENABLE ROW LEVEL SECURITY;

-- Each user can only see their own row (self_access).
-- The join in other tables' RLS policies reads this table as the auth anchor.
CREATE POLICY self_access ON tenant_users
  USING (id = auth.uid());

-- ---------------------------------------------------------------------------
-- 3. tenant_config
-- ---------------------------------------------------------------------------
CREATE TABLE tenant_config (
  id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           UUID        UNIQUE NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  instagram_token_enc TEXT,          -- Fernet-encrypted token
  facebook_token_enc  TEXT,          -- Fernet-encrypted token
  facebook_page_id    TEXT,
  branches            JSONB       NOT NULL DEFAULT '[]',
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE tenant_config ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON tenant_config
  USING (tenant_id = (
    SELECT tenant_id FROM tenant_users WHERE id = auth.uid()
  ));

-- ---------------------------------------------------------------------------
-- 4. billplz_bills
-- ---------------------------------------------------------------------------
CREATE TABLE billplz_bills (
  id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  billplz_bill_id  TEXT        UNIQUE NOT NULL,
  amount_sen       INTEGER     NOT NULL,
  status           TEXT        NOT NULL DEFAULT 'pending'
                               CHECK (status IN ('pending','paid','expired')),
  due_at           TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE billplz_bills ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON billplz_bills
  USING (tenant_id = (
    SELECT tenant_id FROM tenant_users WHERE id = auth.uid()
  ));

-- ---------------------------------------------------------------------------
-- 5. review_snapshots
-- ---------------------------------------------------------------------------
CREATE TABLE review_snapshots (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  branch_id     TEXT        NOT NULL,
  rating        NUMERIC(3,1),
  review_count  INTEGER,
  snapshot_date DATE        NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, branch_id, snapshot_date)   -- prevents duplicate cron runs
);

ALTER TABLE review_snapshots ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON review_snapshots
  USING (tenant_id = (
    SELECT tenant_id FROM tenant_users WHERE id = auth.uid()
  ));

-- ---------------------------------------------------------------------------
-- 6. payment_events  (immutable audit trail — one row per state transition)
-- ---------------------------------------------------------------------------
CREATE TABLE payment_events (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  event_type        TEXT        NOT NULL,
  gateway           TEXT        NOT NULL CHECK (gateway IN ('billplz','stripe')),
  gateway_reference TEXT        UNIQUE,   -- bill_id or stripe event_id (idempotency key)
  amount_sen        INTEGER,
  status            TEXT        NOT NULL,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE payment_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON payment_events
  USING (tenant_id = (
    SELECT tenant_id FROM tenant_users WHERE id = auth.uid()
  ));
