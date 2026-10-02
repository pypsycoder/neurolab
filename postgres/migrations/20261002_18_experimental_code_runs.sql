-- Final independent outcomes only, no code/prompts/transcripts in the DB.
CREATE TABLE IF NOT EXISTS it_research.experimental_code_runs (
  run_id UUID PRIMARY KEY,
  spec_run_id UUID NOT NULL REFERENCES it_research.experimental_specs(run_id) ON DELETE RESTRICT,
  asset_id UUID REFERENCES it_research.solution_assets(id) ON DELETE RESTRICT,
  status TEXT NOT NULL CHECK (status IN ('candidate_passed','candidate_failed')),
  code_sha256 CHAR(64) NOT NULL CHECK (code_sha256 ~ '^[0-9a-f]{64}$'),
  independent_score DOUBLE PRECISION NOT NULL CHECK (independent_score BETWEEN 0 AND 1),
  outcome_sha256 CHAR(64) NOT NULL CHECK (outcome_sha256 ~ '^[0-9a-f]{64}$'),
  outcome JSONB NOT NULL CHECK (jsonb_typeof(outcome)='object' AND octet_length(outcome::text)<=8192),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
