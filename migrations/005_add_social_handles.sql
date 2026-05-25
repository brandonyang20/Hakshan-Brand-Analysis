-- =============================================================================
-- Migration: 005_add_social_handles
-- Adds social_handles JSONB column to tenant_config.
-- Format: {"instagram": "handle", "facebook": "page-name", "tiktok": "handle", "xhs": "uid"}
-- Tenant sets these during onboarding; no OAuth required.
-- =============================================================================

ALTER TABLE tenant_config
  ADD COLUMN IF NOT EXISTS social_handles JSONB NOT NULL DEFAULT '{}';
