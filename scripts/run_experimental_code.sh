#!/usr/bin/env bash
# Code execution is bounded and cannot modify tests, the repository or host services.
set -euo pipefail
[[ "${RUN_EXPERIMENTAL_CODE:-0}" == 1 ]] || { echo 'Set RUN_EXPERIMENTAL_CODE=1'; exit 2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PY="$ROOT/.venv/bin/python"
source "$ROOT/scripts/lib/gigachat_failover.sh"
run_code_lane() {
  local lane="$1"
  shift 3
  NEUROLAB_GIGACHAT_CODE_LANE="$lane" "$PY" "$ROOT/scripts/run_experimental_code.py" "$@"
}
gigachat_run_with_failover "$ROOT" "$ROOT/.env" "$PY" run_code_lane "$@"
