#!/usr/bin/env bash
# Reproducible RP5-only pre-smoke for synthetic MCP and LangGraph contracts.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PYTHON_BIN="$PROJECT_ROOT/runtime/langgraph-eval/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing isolated evaluation Python: $PYTHON_BIN" >&2
  exit 1
fi

cd "$PROJECT_ROOT"

PYTHONPATH="$PROJECT_ROOT/src" "$PYTHON_BIN" -m unittest -q \
  tests.test_gigachat_config \
  tests.test_workflow \
  tests.test_mcp_policy \
  tests.test_mcp_stdio \
  tests.test_synthetic_mcp_trace

RUN_MCP_DOCKER_EVAL=1 PYTHONPATH="$PROJECT_ROOT/src" "$PYTHON_BIN" -m unittest -q \
  tests.test_mcp_docker_fixture \
  tests.test_mcp_docker_git_fixture

PYTHONPATH="$PROJECT_ROOT/src" "$PYTHON_BIN" -c '
from neurolab.synthetic_mcp_trace import run_synthetic_mcp_trace
state = run_synthetic_mcp_trace("synthetic pre-smoke", thread_id="synthetic-pre-smoke")
assert state["status"] == "validated"
print(state["report"])
'

"$PROJECT_ROOT/scripts/verify_synthetic_worktree.sh"
