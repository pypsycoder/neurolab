#!/usr/bin/env bash
set -euo pipefail

LIBRARY_PATH="${1:?pass the failover library path}"
PYTHON_BIN="${2:?pass a Python with python-dotenv}"
TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT"' EXIT
mkdir -p "$TEST_ROOT/runtime/it-research"
printf 'GIGACHAT_PRIMARY_KEY_ENV=TEST_PRIMARY\nGIGACHAT_FREEMIUM_KEY_ENV=TEST_FREEMIUM\nTEST_PRIMARY=primary-test-value\nTEST_FREEMIUM=freemium-test-value\nGIGACHAT_MODEL=GigaChat-2-Pro\n' > "$TEST_ROOT/.env"

source "$LIBRARY_PATH"

# Regression: status must be captured inside the failed branch, not after if.
non_transient() { echo 'private provider error body' >&2; return 23; }
if gigachat_run_with_failover "$TEST_ROOT" "$TEST_ROOT/.env" "$PYTHON_BIN" non_transient > "$TEST_ROOT/non-transient" 2>&1; then
  echo 'non-transient failure was falsely reported as success' >&2; exit 1
else
  [[ "$?" == 23 ]]
fi
! grep -q 'private provider error body' "$TEST_ROOT/non-transient"

# An exit code, not a raw provider traceback, is sufficient for failover.
typed_transient() {
  [[ "$1" == primary ]] && return 75
  echo typed-ok
}
gigachat_run_with_failover "$TEST_ROOT" "$TEST_ROOT/.env" "$PYTHON_BIN" typed_transient > "$TEST_ROOT/typed"
[[ "$(<"$TEST_ROOT/typed")" == typed-ok ]]

primary_then_freemium() {
  local lane="$1"
  printf '%s,' "$lane" >> "$TEST_ROOT/attempts"
  if [[ "$lane" == "primary" ]]; then
    echo 'RateLimitError 429' >&2
    return 1
  fi
  [[ "$2" == "freemium-test-value" ]]
  echo 'freemium-ok'
}

gigachat_run_with_failover "$TEST_ROOT" "$TEST_ROOT/.env" "$PYTHON_BIN" primary_then_freemium > "$TEST_ROOT/result"
result="$(<"$TEST_ROOT/result")"
[[ "$result" == 'freemium-ok' ]]
[[ "$(<"$TEST_ROOT/attempts")" == 'primary,freemium,' ]]

both_limited() { echo '429 Too Many Requests' >&2; return 1; }
set +e
gigachat_run_with_failover "$TEST_ROOT" "$TEST_ROOT/.env" "$PYTHON_BIN" both_limited >/dev/null
status=$?
set -e
[[ "$status" == 75 ]]
[[ -s "$TEST_ROOT/runtime/it-research/gigachat-rate-limit-pause-until" ]]

: > "$TEST_ROOT/attempts"
set +e
gigachat_run_with_failover "$TEST_ROOT" "$TEST_ROOT/.env" "$PYTHON_BIN" primary_then_freemium >/dev/null
status=$?
set -e
[[ "$status" == 75 ]]
[[ ! -s "$TEST_ROOT/attempts" ]]
