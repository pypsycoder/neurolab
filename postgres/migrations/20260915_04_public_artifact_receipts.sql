-- Repository metadata is reproducibility evidence only after a human-reviewed
-- claim links it to a source.  No source code, README, dataset or token is kept.

CREATE TABLE IF NOT EXISTS it_research.public_artifact_receipts (
  id UUID PRIMARY KEY,
  source_key CHAR(64) NOT NULL REFERENCES it_research.sources(source_key) ON DELETE CASCADE,
  claim_id UUID NOT NULL REFERENCES it_research.claims(id) ON DELETE CASCADE,
  repository TEXT NOT NULL CHECK (repository ~ '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'),
  api_url TEXT NOT NULL CHECK (api_url ~ '^https://api\.github\.com/repos/'),
  html_url TEXT NOT NULL CHECK (html_url ~ '^https://github\.com/'),
  default_branch TEXT NOT NULL,
  code_license TEXT NOT NULL,
  evidence_sha256 CHAR(64) NOT NULL,
  has_readme BOOLEAN NOT NULL,
  has_test_paths BOOLEAN NOT NULL,
  has_environment_manifest BOOLEAN NOT NULL,
  has_data_paths BOOLEAN NOT NULL,
  verification_status TEXT NOT NULL CHECK (verification_status = 'public_artifact_metadata_verified'),
  checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (claim_id, repository, evidence_sha256)
);

CREATE INDEX IF NOT EXISTS it_research_public_artifacts_claim_idx
  ON it_research.public_artifact_receipts(claim_id, checked_at DESC);
