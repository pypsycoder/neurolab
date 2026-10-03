#!/usr/bin/env bash
# Opt-in synthetic-only replay. Credentials enter one ephemeral container only.
set -euo pipefail

if [[ "${RUN_GIGACHAT_RESPONSE_REPLAY:-0}" != "1" ]]; then
  echo "Set RUN_GIGACHAT_RESPONSE_REPLAY=1 for a synthetic-only model replay." >&2
  exit 2
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ENV_FILE="${NEUROLAB_ENV_FILE:-$PROJECT_ROOT/.env}"
PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
SYSTEM_CA_BUNDLE="${NEUROLAB_SSL_CERT_FILE:-/etc/ssl/certs/ca-certificates.crt}"
if [[ ! -f "$ENV_FILE" || ! -x "$PYTHON_BIN" || ! -f "$SYSTEM_CA_BUNDLE" ]]; then
  echo "Required local replay inputs are unavailable." >&2
  exit 1
fi

source "$PROJECT_ROOT/scripts/lib/gigachat_failover.sh"

run_response_replay_lane() {
  local _lane="$1" credential="$2" model="$3"
  shift 3
  cd "$PROJECT_ROOT"
  GIGACHAT_CREDENTIALS="$credential" docker compose --profile research run --rm --no-deps \
    -e GIGACHAT_CREDENTIALS -e GIGACHAT_SCOPE \
    -e "GIGACHAT_MODEL=$model" \
    -e "SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt" \
    -v "$SYSTEM_CA_BUNDLE:/etc/ssl/certs/ca-certificates.crt:ro" \
    --entrypoint python research /app/scripts/run_gigachat_response_quality_replay.py --persist "$@"
}

gigachat_run_with_failover "$PROJECT_ROOT" "$ENV_FILE" "$PYTHON_BIN" run_response_replay_lane "$@"
