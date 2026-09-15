-- GigaChat chat completions currently expose no documented request-idempotency
-- header.  Persist an attempt before the network call so an interrupted
-- external outcome is never silently replayed and charged again.
CREATE TABLE IF NOT EXISTS provider_attempts (
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  execution_id UUID NOT NULL,
  provider TEXT NOT NULL,
  model TEXT,
  credential_lane TEXT,
  status TEXT NOT NULL CHECK (status IN ('inflight', 'completed', 'failed', 'outcome_unknown')),
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  concluded_at TIMESTAMPTZ,
  error_message TEXT,
  PRIMARY KEY (task_id, execution_id)
);

CREATE INDEX IF NOT EXISTS provider_attempts_inflight_idx
  ON provider_attempts(task_id, started_at DESC)
  WHERE status='inflight';
