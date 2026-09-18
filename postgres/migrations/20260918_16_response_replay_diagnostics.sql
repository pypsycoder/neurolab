-- Strictly redacted, per-case response-contract outcomes. No prompts or model text.
CREATE TABLE IF NOT EXISTS it_research.evaluator_run_diagnostics (
  id UUID PRIMARY KEY,
  evaluator_run_id UUID NOT NULL REFERENCES it_research.evaluator_runs(id) ON DELETE CASCADE,
  diagnostic_version TEXT NOT NULL CHECK (char_length(diagnostic_version) BETWEEN 3 AND 120),
  cases JSONB NOT NULL CHECK (jsonb_typeof(cases) = 'array' AND octet_length(cases::text) <= 2048),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (evaluator_run_id, diagnostic_version)
);
