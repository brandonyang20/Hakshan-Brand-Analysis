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
-- NOTE: Tables are created first (all of them), then RLS + policies are applied.
--   This is required because the tenants policy references tenant_users, and
--   tenant_users references tenants via FK — both must exist before any policy
--   that cross-references them is created.
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

-- ---------------------------------------------------------------------------
-- 3. tenant_config
-- ---------------------------------------------------------------------------
CREATE TABLE tenant_config (
  id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           UUID        UNIQUE NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  instagram_token_enc TEXT,
  facebook_token_enc  TEXT,
  facebook_page_id    TEXT,
  branches            JSONB       NOT NULL DEFAULT '[]',
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

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
  UNIQUE (tenant_id, branch_id, snapshot_date)
);

-- ---------------------------------------------------------------------------
-- 6. payment_events  (immutable audit trail)
-- ---------------------------------------------------------------------------
CREATE TABLE payment_events (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  event_type        TEXT        NOT NULL,
  gateway           TEXT        NOT NULL CHECK (gateway IN ('billplz','stripe')),
  gateway_reference TEXT        UNIQUE,
  amount_sen        INTEGER,
  status            TEXT        NOT NULL,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- RLS — enable + policies (all tables exist by this point)
-- ---------------------------------------------------------------------------

ALTER TABLE tenants         ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_users    ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_config   ENABLE ROW LEVEL SECURITY;
ALTER TABLE billplz_bills   ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment_events  ENABLE ROW LEVEL SECURITY;

-- tenants: user sees only their own tenant (via tenant_users join)
CREATE POLICY tenant_isolation ON tenants
  USING (id = (
    SELECT tenant_id FROM tenant_users WHERE id = auth.uid()
  ));

-- tenant_users: each user sees only their own row
CREATE POLICY self_access ON tenant_users
  USING (id = auth.uid());

-- all other tables: isolated by tenant_id via tenant_users
CREATE POLICY tenant_isolation ON tenant_config
  USING (tenant_id = (
    SELECT tenant_id FROM tenant_users WHERE id = auth.uid()
  ));

CREATE POLICY tenant_isolation ON billplz_bills
  USING (tenant_id = (
    SELECT tenant_id FROM tenant_users WHERE id = auth.uid()
  ));

CREATE POLICY tenant_isolation ON review_snapshots
  USING (tenant_id = (
    SELECT tenant_id FROM tenant_users WHERE id = auth.uid()
  ));

CREATE POLICY tenant_isolation ON payment_events
  USING (tenant_id = (
    SELECT tenant_id FROM tenant_users WHERE id = auth.uid()
  ));
