-- The control-plane worker must not alter production schema at runtime.
-- This migration makes its final legacy dependency explicit for both fresh
-- and already-running databases before runtime DDL is removed.

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS result JSONB;

CREATE TABLE IF NOT EXISTS worker_heartbeats (
  worker_name TEXT PRIMARY KEY,
  last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
  status TEXT NOT NULL DEFAULT 'idle'
);
