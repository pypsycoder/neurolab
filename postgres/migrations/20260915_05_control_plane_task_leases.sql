-- Durable execution lease for the Redis processing list.  A worker may
-- requeue only a lease older than its configured timeout; stale results are
-- ignored by the matching execution_id predicate.

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS execution_id UUID;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS credential_lane TEXT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'tasks_credential_lane_check'
  ) THEN
    ALTER TABLE tasks ADD CONSTRAINT tasks_credential_lane_check
      CHECK (credential_lane IN ('primary', 'freemium'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS tasks_running_lease_idx
  ON tasks (started_at)
  WHERE status = 'running';

CREATE INDEX IF NOT EXISTS tasks_credential_lane_created_idx
  ON tasks (credential_lane, created_at DESC);
