#!/usr/bin/env bash
set -euo pipefail
[[ "${RUN_PERSIST_CODE_OUTCOME:-0}" == 1 ]] || { echo 'Set RUN_PERSIST_CODE_OUTCOME=1'; exit 2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"
docker compose --profile research run --rm --no-deps --entrypoint python research /app/scripts/persist_code_outcome.py "$@"
