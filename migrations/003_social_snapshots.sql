-- =============================================================================
-- Migration: 003_social_snapshots
-- Weekly social media follower/engagement snapshots per tenant per platform.
-- Populated by social_scraper.py (Playwright headless browser).
-- Platforms: instagram, facebook, tiktok, xhs
-- =============================================================================

CREATE TABLE social_snapshots (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  platform      TEXT        NOT NULL
                            CHECK (platform IN ('instagram','facebook','tiktok','xhs')),
  snapshot_date DATE        NOT NULL,
  followers     INTEGER,
  following     INTEGER,
  posts         INTEGER,
  total_likes   BIGINT,     -- TikTok cumulative heart count
  last_post_date DATE,
  error         TEXT,       -- scrape error message if run but failed
  scraped_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, platform, snapshot_date)
);

ALTER TABLE social_snapshots ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON social_snapshots
  USING (tenant_id = (
    SELECT tenant_id FROM tenant_users WHERE id = auth.uid()
  ));

CREATE INDEX social_snapshots_tenant_platform_date
  ON social_snapshots(tenant_id, platform, snapshot_date DESC);
