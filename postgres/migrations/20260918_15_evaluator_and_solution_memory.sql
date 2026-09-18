-- Redacted audit receipts for self-evolving evaluators and reusable assets.
CREATE TABLE IF NOT EXISTS it_research.evaluator_versions (
  id UUID PRIMARY KEY,
  evaluator_kind TEXT NOT NULL CHECK (evaluator_kind IN ('article_scoring','response_quality')),
  version_label TEXT NOT NULL,
  parent_id UUID REFERENCES it_research.evaluator_versions(id),
  definition_sha256 CHAR(64) NOT NULL CHECK (definition_sha256 ~ '^[0-9a-f]{64}$'),
  frozen_case_set_sha256 CHAR(64) NOT NULL CHECK (frozen_case_set_sha256 ~ '^[0-9a-f]{64}$'),
  active_case_set_sha256 CHAR(64) NOT NULL CHECK (active_case_set_sha256 ~ '^[0-9a-f]{64}$'),
  state TEXT NOT NULL CHECK (state IN ('proposed','shadow','promoted','reverted')),
  proposed_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (evaluator_kind, version_label)
);

CREATE TABLE IF NOT EXISTS it_research.evaluator_runs (
  id UUID PRIMARY KEY,
  evaluator_id UUID NOT NULL REFERENCES it_research.evaluator_versions(id) ON DELETE RESTRICT,
  cohort_sha256 CHAR(64) NOT NULL CHECK (cohort_sha256 ~ '^[0-9a-f]{64}$'),
  assessor TEXT NOT NULL,
  assessor_role TEXT NOT NULL CHECK (assessor_role IN ('author','independent_evaluator')),
  metrics JSONB NOT NULL CHECK (jsonb_typeof(metrics) = 'object' AND octet_length(metrics::text) <= 2048),
  evaluated_case_count INTEGER NOT NULL CHECK (evaluated_case_count > 0),
  completed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS it_research.evaluator_decisions (
  id UUID PRIMARY KEY,
  baseline_evaluator_id UUID NOT NULL REFERENCES it_research.evaluator_versions(id) ON DELETE RESTRICT,
  candidate_evaluator_id UUID NOT NULL REFERENCES it_research.evaluator_versions(id) ON DELETE RESTRICT,
  baseline_run_id UUID NOT NULL REFERENCES it_research.evaluator_runs(id) ON DELETE RESTRICT,
  candidate_run_id UUID NOT NULL REFERENCES it_research.evaluator_runs(id) ON DELETE RESTRICT,
  decision TEXT NOT NULL CHECK (decision IN ('shadow','promoted','reverted')),
  reason_codes JSONB NOT NULL CHECK (jsonb_typeof(reason_codes) = 'array' AND octet_length(reason_codes::text) <= 2048),
  policy_version TEXT NOT NULL,
  decided_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS it_research.solution_assets (
  id UUID PRIMARY KEY,
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('architecture_pattern','workflow_scheme','code_component','test_suite','evaluator','prompt_template')),
  label TEXT NOT NULL CHECK (char_length(label) BETWEEN 3 AND 160),
  content_sha256 CHAR(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  state TEXT NOT NULL CHECK (state IN ('candidate','promoted','watchlist','retired')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (asset_kind, content_sha256)
);

CREATE TABLE IF NOT EXISTS it_research.solution_outcomes (
  id UUID PRIMARY KEY,
  asset_id UUID NOT NULL REFERENCES it_research.solution_assets(id) ON DELETE CASCADE,
  synthetic_run_sha256 CHAR(64) NOT NULL CHECK (synthetic_run_sha256 ~ '^[0-9a-f]{64}$'),
  evaluator_run_id UUID NOT NULL REFERENCES it_research.evaluator_runs(id) ON DELETE RESTRICT,
  outcome TEXT NOT NULL CHECK (outcome IN ('success','failure','regression')),
  primary_quality DOUBLE PRECISION NOT NULL CHECK (primary_quality BETWEEN 0 AND 1),
  safety_quality DOUBLE PRECISION NOT NULL CHECK (safety_quality BETWEEN 0 AND 1),
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (asset_id, synthetic_run_sha256, evaluator_run_id)
);
