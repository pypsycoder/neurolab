#!/usr/bin/env bash
set -euo pipefail
[[ "${RUN_DURABLE_RECONCILIATION:-0}" == 1 ]] || { echo 'Set RUN_DURABLE_RECONCILIATION=1'; exit 2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"
docker compose --profile research run --rm --no-deps -e LANGGRAPH_STRICT_MSGPACK=true --entrypoint python research /app/scripts/run_durable_reconciliation.py "$@"
