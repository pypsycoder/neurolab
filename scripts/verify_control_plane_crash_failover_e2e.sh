#!/usr/bin/env bash
# Opt-in crash/failover test for the live Docker control plane.
#
# This test never calls an external provider.  It uses one new
# local-smoke-test message and deliberately SIGKILLs a temporary worker after
# Redis BLMOVE and before PostgreSQL claim_task.  It may run only while the
# normal task and processing queues are empty and no task is running.
set -euo pipefail

if [[ "${1:-}" != "--apply" || $# -ne 1 ]]; then
  echo "Usage: $0 --apply" >&2
  echo "Runs one synthetic crash/failover test after verifying the live queue is idle." >&2
  exit 2
fi

cd "$(dirname "$0")/.."

fail() {
  echo "Crash/failover E2E failed: $*" >&2
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

redis_scalar() {
  docker compose exec -T redis redis-cli --raw "$@" | tr -d '\r\n'
}

helper_container='neuro-lab-crash-e2e-helper'
recovery_container='neuro-lab-crash-e2e-recovery'

restore_workers() {
  docker rm -f "$helper_container" "$recovery_container" >/dev/null 2>&1 || true
  docker compose up -d --scale orchestrator=2 orchestrator >/dev/null 2>&1 || true
}

docker compose config --quiet

for container_name in "$helper_container" "$recovery_container"; do
  if docker container inspect "$container_name" >/dev/null 2>&1; then
    fail "reserved test container already exists: $container_name"
  fi
done

[[ "$(redis_scalar LLEN neuro-lab:tasks)" == "0" ]] \
  || fail "refusing: normal task queue is not empty"
[[ "$(redis_scalar LLEN neuro-lab:tasks:processing)" == "0" ]] \
  || fail "refusing: processing queue is not empty"
[[ "$(scalar "SELECT count(*) FROM tasks WHERE status='running';")" == "0" ]] \
  || fail "refusing: a task is currently running"

task_id="$(new_uuid)"
payload="{\"task_id\":\"$task_id\",\"provider\":\"local-smoke-test\",\"model\":\"crash-failover-e2e\",\"usage\":{\"input_tokens\":0,\"output_tokens\":0},\"amount_usd\":0}"

# From this point a failure must restore the two production worker replicas.
trap restore_workers EXIT
docker compose stop orchestrator >/dev/null

# The helper does exactly BLMOVE and then waits.  It deliberately does not
# call handle_delivery, so there is no task row to recover yet.
docker compose run -d --name "$helper_container" --no-deps --entrypoint python orchestrator -c \
  'import time, worker; raw = worker.queue.blmove(worker.TASK_QUEUE, worker.PROCESSING_QUEUE, timeout=30, src="LEFT", dest="RIGHT"); assert raw is not None; time.sleep(300)' \
  >/dev/null
printf '%s' "$payload" | docker compose exec -T redis redis-cli -x RPUSH neuro-lab:tasks >/dev/null

for _ in $(seq 1 20); do
  in_processing="$(redis_scalar LLEN neuro-lab:tasks:processing)"
  db_rows="$(scalar "SELECT count(*) FROM tasks WHERE id='$task_id'::uuid;")"
  [[ "$in_processing" == "1" && "$db_rows" == "0" ]] && break
  sleep 1
done
[[ "${in_processing:-}" == "1" && "${db_rows:-}" == "0" ]] \
  || fail "helper did not reach post-BLMOVE/pre-claim state"

# SIGKILL models a process crash: the raw delivery remains in processing.
docker kill "$helper_container" >/dev/null
docker rm "$helper_container" >/dev/null

# A one-shot worker with rapid recovery is used only for this synthetic test.
# It executes the same worker loop and recovery code as the permanent service.
docker compose run -d --name "$recovery_container" --no-deps \
  -e RECOVERY_INTERVAL_SECONDS=1 orchestrator >/dev/null

for _ in $(seq 1 30); do
  observation="$(scalar "SELECT status || '|' || (execution_id IS NOT NULL)::int || '|' || (SELECT count(*) FROM cost_events WHERE task_id='$task_id'::uuid) FROM tasks WHERE id='$task_id'::uuid;")"
  [[ "$observation" == 'succeeded|1|1' ]] && break
  sleep 1
done
[[ "${observation:-}" == 'succeeded|1|1' ]] \
  || fail "recovered task did not complete once (last: ${observation:-missing})"
[[ "$(redis_scalar LLEN neuro-lab:tasks:processing)" == "0" ]] \
  || fail "processing queue was not drained after recovery"

restore_workers
trap - EXIT
echo "Control-plane crash/failover E2E passed: BLMOVE-before-claim crash recovered once."
