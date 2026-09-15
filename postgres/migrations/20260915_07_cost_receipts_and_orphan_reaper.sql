-- Each provider invocation has a worker-generated execution lease.  A receipt
-- is unique inside that lease so an interrupted final-state write cannot make
-- the same invocation appear as a free request.
ALTER TABLE cost_events
  ADD COLUMN IF NOT EXISTS execution_id UUID;

CREATE UNIQUE INDEX IF NOT EXISTS cost_events_task_execution_unique
  ON cost_events(task_id, execution_id)
  WHERE task_id IS NOT NULL AND execution_id IS NOT NULL;
