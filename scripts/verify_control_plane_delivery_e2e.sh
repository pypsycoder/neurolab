#!/usr/bin/env bash
# Opt-in integration verification for the live Docker control plane.
#
# It submits only local-smoke-test payloads: no prompt, credential, patient
# data, or external provider request is involved.  Rows are intentionally
# retained as synthetic audit evidence.  This script never reads or sources
# .env; credentials stay inside the Compose service containers.
set -euo pipefail

if [[ "${1:-}" != "--apply" || $# -ne 1 ]]; then
  echo "Usage: $0 --apply" >&2
  echo "Creates three retained synthetic tasks to verify durable delivery recovery." >&2
  exit 2
fi

cd "$(dirname "$0")/.."

fail() {
  echo "E2E verification failed: $*" >&2
  exit 1
}

new_uuid() {
  local value
  value="$(cat /proc/sys/kernel/random/uuid)"
  [[ "$value" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] \
    || fail "kernel did not provide a UUID"
  printf '%s' "$value"
}

psql() {
  docker compose exec -T postgres sh -c \
    'psql -v ON_ERROR_STOP=1 -tA -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
}

scalar() {
  psql <<<"$1" | tr -d '\r\n'
}

enqueue() {
  local queue_name="$1"
  local payload="$2"
  printf '%s' "$payload" | docker compose exec -T redis redis-cli -x RPUSH "$queue_name" >/dev/null
}

wait_for() {
  local task_id="$1"
  local expected="$2"
  local observation
  for _ in $(seq 1 20); do
    observation="$(scalar "SELECT status || '|' || (execution_id IS NOT NULL)::int || '|' || (SELECT count(*) FROM cost_events WHERE task_id='$task_id'::uuid) FROM tasks WHERE id='$task_id'::uuid;")"
    [[ "$observation" == "$expected" ]] && return 0
    sleep 1
  done
  fail "task $task_id did not reach $expected (last: ${observation:-missing})"
}

docker compose config --quiet

lease_seconds="$(docker compose exec -T orchestrator python -c 'import worker; print(worker.TASK_LEASE_SECONDS)')"
[[ "$lease_seconds" =~ ^[1-9][0-9]*$ ]] || fail "invalid worker lease duration"

# Calling the worker recovery function scans the processing list.  Do not run
# it if a real task is already overdue: that task deserves separate review.
stale_before="$(scalar "SELECT count(*) FROM tasks WHERE status='running' AND started_at < now() - make_interval(secs => $lease_seconds);")"
[[ "$stale_before" == "0" ]] || fail "refusing recovery: $stale_before pre-existing expired task(s)"

duplicate_id="$(new_uuid)"
duplicate_payload="{\"task_id\":\"$duplicate_id\",\"provider\":\"local-smoke-test\",\"model\":\"delivery-e2e\",\"usage\":{\"input_tokens\":0,\"output_tokens\":0},\"amount_usd\":0}"

# Two workers may receive the duplicate concurrently.  Exactly one can claim
# the queued row; the other must acknowledge it without creating a cost event.
enqueue 'neuro-lab:tasks' "$duplicate_payload"
enqueue 'neuro-lab:tasks' "$duplicate_payload"
wait_for "$duplicate_id" 'succeeded|1|1'

stale_id="$(new_uuid)"
stale_execution_id="$(new_uuid)"
stale_payload="{\"task_id\":\"$stale_id\",\"provider\":\"local-smoke-test\",\"model\":\"lease-recovery-e2e\",\"usage\":{\"input_tokens\":0,\"output_tokens\":0},\"amount_usd\":0}"
expired_seconds=$((lease_seconds + 60))

psql <<SQL
INSERT INTO tasks (id, status, provider, model, started_at, execution_id)
VALUES ('$stale_id'::uuid, 'running', 'local-smoke-test', 'lease-recovery-e2e',
        now() - make_interval(secs => $expired_seconds), '$stale_execution_id'::uuid)
ON CONFLICT (id) DO NOTHING;
SQL
enqueue 'neuro-lab:tasks:processing' "$stale_payload"

# This is the exact recovery entrypoint used by the running workers.  The
# preflight above prevents the test from reclaiming another overdue task.
docker compose exec -T orchestrator python -c 'import worker; worker.recover_stale_deliveries()' >/dev/null
wait_for "$stale_id" 'succeeded|1|1'

replaced_lease="$(scalar "SELECT (execution_id <> '$stale_execution_id'::uuid)::int FROM tasks WHERE id='$stale_id'::uuid;")"
[[ "$replaced_lease" == "1" ]] || fail "stale task retained its old execution lease"

unclaimed_id="$(new_uuid)"
unclaimed_payload="{\"task_id\":\"$unclaimed_id\",\"provider\":\"local-smoke-test\",\"model\":\"unclaimed-recovery-e2e\",\"usage\":{\"input_tokens\":0,\"output_tokens\":0},\"amount_usd\":0}"

# This mimics a worker crash after BLMOVE but before PostgreSQL claim_task.
# Recovery must create a queued row, atomically return the raw payload, and
# let a worker process it once.
enqueue 'neuro-lab:tasks:processing' "$unclaimed_payload"
docker compose exec -T orchestrator python -c 'import worker; worker.recover_stale_deliveries()' >/dev/null
wait_for "$unclaimed_id" 'succeeded|1|1'

echo "Control-plane delivery E2E passed: duplicate, expired lease, and unclaimed processing recovery."
