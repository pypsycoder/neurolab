CREATE TABLE IF NOT EXISTS tasks (
  id UUID PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
  provider TEXT,
  model TEXT,
  credential_lane TEXT CHECK (credential_lane IN ('primary', 'freemium')),
  request_ref TEXT,
  result JSONB,
  execution_id UUID,
  error_message TEXT
);

CREATE TABLE IF NOT EXISTS cost_events (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
  execution_id UUID,
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  provider TEXT NOT NULL,
  model TEXT,
  input_tokens INTEGER CHECK (input_tokens >= 0),
  output_tokens INTEGER CHECK (output_tokens >= 0),
  amount_usd NUMERIC(12, 6) CHECK (amount_usd >= 0),
  raw_usage JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS cost_events_task_id_idx ON cost_events(task_id);
CREATE INDEX IF NOT EXISTS cost_events_recorded_at_idx ON cost_events(recorded_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS cost_events_task_execution_unique
  ON cost_events(task_id, execution_id)
  WHERE task_id IS NOT NULL AND execution_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS worker_heartbeats (
  worker_name TEXT PRIMARY KEY,
  last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
  status TEXT NOT NULL DEFAULT 'idle'
);
