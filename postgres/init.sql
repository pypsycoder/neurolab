CREATE TABLE IF NOT EXISTS tasks (
  id UUID PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
  provider TEXT,
  model TEXT,
  request_ref TEXT,
  result JSONB,
  execution_id UUID,
  error_message TEXT
);

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS result JSONB;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS execution_id UUID;

CREATE TABLE IF NOT EXISTS cost_events (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
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
