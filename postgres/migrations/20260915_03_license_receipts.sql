-- Explicit licence evidence precedes every retained/open-access full-text receipt.
-- Raw HTML is untrusted and is intentionally not stored.

CREATE TABLE IF NOT EXISTS it_research.license_receipts (
  id UUID PRIMARY KEY,
  source_key CHAR(64) NOT NULL REFERENCES it_research.sources(source_key) ON DELETE CASCADE,
  provider TEXT NOT NULL CHECK (provider = 'arxiv'),
  metadata_url TEXT NOT NULL CHECK (metadata_url ~ '^https://arxiv\.org/abs/'),
  license_id TEXT NOT NULL CHECK (license_id IN ('CC-BY-4.0', 'CC0-1.0')),
  evidence_sha256 CHAR(64) NOT NULL,
  checked_on DATE NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_key, license_id, evidence_sha256)
);

CREATE INDEX IF NOT EXISTS it_research_license_receipts_source_idx
  ON it_research.license_receipts(source_key, checked_on DESC);
