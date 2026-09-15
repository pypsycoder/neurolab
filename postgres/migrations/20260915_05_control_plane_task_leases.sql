-- Durable execution lease for the Redis processing list.  A worker may
-- requeue only a lease older than its configured timeout; stale results are
-- ignored by the matching execution_id predicate.

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS execution_id UUID;

CREATE INDEX IF NOT EXISTS tasks_running_lease_idx
  ON tasks (started_at)
  WHERE status = 'running';
