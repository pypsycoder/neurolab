-- Independent append-only reassessments; historical author outcomes are not overwritten.
CREATE TABLE IF NOT EXISTS it_research.code_cycle_assessments (
  run_id UUID NOT NULL REFERENCES it_research.experimental_code_runs(run_id) ON DELETE RESTRICT,
  evaluator_sha256 CHAR(64) NOT NULL CHECK (evaluator_sha256 ~ '^[0-9a-f]{64}$'),
  code_sha256 CHAR(64) NOT NULL CHECK (code_sha256 ~ '^[0-9a-f]{64}$'),
  status TEXT NOT NULL CHECK (status IN ('passed','failed')),
  passed INTEGER NOT NULL CHECK (passed BETWEEN 0 AND 9),
  total INTEGER NOT NULL CHECK (total = 9),
  CHECK ((status = 'passed') = (passed = 9)),
  assessment_sha256 CHAR(64) NOT NULL CHECK (assessment_sha256 ~ '^[0-9a-f]{64}$'),
  assessment JSONB NOT NULL CHECK (jsonb_typeof(assessment) = 'object' AND octet_length(assessment::text) <= 4096),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, evaluator_sha256)
);
