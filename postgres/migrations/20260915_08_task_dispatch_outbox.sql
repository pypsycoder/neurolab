-- Dashboard acceptance must survive a crash after the PostgreSQL transaction
-- and before Redis RPUSH.  Payload retention is limited to synthetic tasks in
-- the current project phase; this table is not authorized for patient data.
CREATE TABLE IF NOT EXISTS task_outbox (
  task_id UUID PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  delivered_at TIMESTAMPTZ,
  delivery_claim_id UUID,
  delivery_claimed_at TIMESTAMPTZ,
  delivery_attempts INTEGER NOT NULL DEFAULT 0 CHECK (delivery_attempts >= 0),
  last_error TEXT
);

CREATE INDEX IF NOT EXISTS task_outbox_pending_idx
  ON task_outbox(created_at)
  WHERE delivered_at IS NULL;
