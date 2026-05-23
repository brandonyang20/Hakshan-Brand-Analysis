-- =============================================================================
-- Migration: 002_review_snapshots_index
-- Phase 1B — Add lookup index for per-branch snapshot queries
-- =============================================================================

-- Speeds up "get last 2 snapshots for tenant+branch" — the hot path for deltas
CREATE INDEX IF NOT EXISTS review_snapshots_lookup
  ON review_snapshots (tenant_id, branch_id, snapshot_date DESC);
