-- Public IT-research corpus only.  This schema must never contain patient,
-- clinical, secret, prompt, PDF, or raw abstract data.  The migration is
-- applied explicitly to an existing database; init.sql is bootstrap-only.

CREATE SCHEMA IF NOT EXISTS it_research;

CREATE TABLE IF NOT EXISTS it_research.runs (
  id UUID PRIMARY KEY,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  pipeline_version TEXT NOT NULL,
  topic_sha256 CHAR(64) NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('review_required', 'collecting_evidence', 'ready_for_synthesis', 'blocked')),
  provider_status JSONB NOT NULL DEFAULT '{}'::jsonb,
  artifact_ref TEXT,
  CHECK (artifact_ref IS NULL OR artifact_ref !~ '(^/|\\|\.\.)')
);

CREATE TABLE IF NOT EXISTS it_research.sources (
  source_key CHAR(64) PRIMARY KEY,
  canonical_doi TEXT,
  canonical_url TEXT NOT NULL,
  title TEXT NOT NULL,
  published_on DATE NOT NULL,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  abstract_sha256 CHAR(64),
  verification_status TEXT NOT NULL DEFAULT 'metadata_observed'
    CHECK (verification_status IN ('metadata_observed', 'metadata_corroborated', 'content_verified')),
  CHECK (canonical_url ~ '^https://'),
  CHECK (title !~ '[\r\n]')
);

CREATE UNIQUE INDEX IF NOT EXISTS it_research_sources_doi_unique
  ON it_research.sources (canonical_doi) WHERE canonical_doi IS NOT NULL;

CREATE TABLE IF NOT EXISTS it_research.observations (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id UUID NOT NULL REFERENCES it_research.runs(id) ON DELETE CASCADE,
  source_key CHAR(64) NOT NULL REFERENCES it_research.sources(source_key) ON DELETE RESTRICT,
  provider TEXT NOT NULL CHECK (provider IN ('arxiv', 'openalex', 'crossref')),
  provider_id TEXT NOT NULL,
  provider_url TEXT NOT NULL CHECK (provider_url ~ '^https://'),
  checked_on DATE NOT NULL,
  evidence_level TEXT NOT NULL CHECK (evidence_level IN ('primary', 'secondary', 'reference')),
  limitations JSONB NOT NULL DEFAULT '[]'::jsonb,
  authors JSONB NOT NULL DEFAULT '[]'::jsonb,
  UNIQUE (run_id, provider, provider_id)
);

CREATE INDEX IF NOT EXISTS it_research_observations_source_idx
  ON it_research.observations (source_key);
CREATE INDEX IF NOT EXISTS it_research_observations_checked_idx
  ON it_research.observations (checked_on DESC);

CREATE TABLE IF NOT EXISTS it_research.assessments (
  source_key CHAR(64) PRIMARY KEY REFERENCES it_research.sources(source_key) ON DELETE CASCADE,
  assessed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  classifier_version TEXT NOT NULL,
  architecture_layers TEXT[] NOT NULL,
  classification_confidence NUMERIC(4,3) NOT NULL CHECK (classification_confidence BETWEEN 0 AND 1),
  conceptual_support NUMERIC(4,3) NOT NULL CHECK (conceptual_support BETWEEN 0 AND 1),
  implementation_readiness NUMERIC(4,3) NOT NULL CHECK (implementation_readiness BETWEEN 0 AND 1),
  reproducibility NUMERIC(4,3) NOT NULL CHECK (reproducibility BETWEEN 0 AND 1),
  source_independence NUMERIC(4,3) NOT NULL CHECK (source_independence BETWEEN 0 AND 1),
  rationale JSONB NOT NULL DEFAULT '[]'::jsonb,
  CHECK (architecture_layers <@ ARRAY['global_architecture', 'subsystem', 'component', 'feature']::TEXT[]),
  CHECK (cardinality(architecture_layers) > 0)
);

CREATE TABLE IF NOT EXISTS it_research.synthesis_runs (
  id UUID PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  coverage_snapshot JSONB NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('collecting_evidence', 'ready_for_synthesis', 'review_required', 'blocked')),
  specification_sha256 CHAR(64),
  artifact_ref TEXT,
  reviewer_status TEXT NOT NULL DEFAULT 'not_requested'
    CHECK (reviewer_status IN ('not_requested', 'review_required', 'approved', 'rejected')),
  CHECK (artifact_ref IS NULL OR artifact_ref !~ '(^/|\\|\.\.)')
);

REVOKE ALL ON SCHEMA it_research FROM PUBLIC;
GRANT USAGE ON SCHEMA it_research TO CURRENT_USER;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA it_research TO CURRENT_USER;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA it_research TO CURRENT_USER;
