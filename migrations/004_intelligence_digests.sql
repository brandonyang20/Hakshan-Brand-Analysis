-- =============================================================================
-- Migration: 004_intelligence_digests
-- Weekly AI-generated brand intelligence digest paragraphs.
-- Populated by digest_service.py using Claude claude-sonnet-4-6.
-- One row per tenant per week (upserted on re-run).
-- =============================================================================

CREATE TABLE intelligence_digests (
  id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  week_start       DATE        NOT NULL,   -- Monday of the week this digest covers
  digest_text      TEXT        NOT NULL,
  model            TEXT        NOT NULL DEFAULT 'claude-sonnet-4-6',
  prompt_tokens    INTEGER,
  completion_tokens INTEGER,
  generated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, week_start)
);

ALTER TABLE intelligence_digests ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON intelligence_digests
  USING (tenant_id = (
    SELECT tenant_id FROM tenant_users WHERE id = auth.uid()
  ));
