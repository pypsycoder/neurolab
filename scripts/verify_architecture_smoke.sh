#!/usr/bin/env bash
# Deterministic RP5-only architecture smoke over synthetic local contracts.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PYTHON_BIN="$PROJECT_ROOT/runtime/langgraph-eval/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing isolated evaluation Python: $PYTHON_BIN" >&2
  exit 1
fi

"$PROJECT_ROOT/scripts/verify_synthetic_smoke.sh"

PYTHONPATH="$PROJECT_ROOT/src" "$PYTHON_BIN" -m unittest -q \
  tests.test_agent_roles \
  tests.test_agent_transitions \
  tests.test_architecture_smoke

PYTHONPATH="$PROJECT_ROOT/src" "$PYTHON_BIN" -c '
from neurolab.architecture_smoke import run_architecture_smoke

state = run_architecture_smoke(
    task="synthetic architecture smoke",
    thread_id="architecture-smoke-runner",
    changed_paths=["openhands_eval_fixture/calculator.py"],
    allowed_paths=["openhands_eval_fixture/calculator.py"],
    test_command="python3 -B -m unittest discover -s openhands_eval_fixture",
    test_exit_code=0,
)
assert state.decision == "review_required"
print(state.report)
'
