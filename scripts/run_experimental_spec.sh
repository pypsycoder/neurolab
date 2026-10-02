#!/usr/bin/env bash
# Generate one strict experimental artifact; never start code or deploy.
set -euo pipefail
[[ "${RUN_EXPERIMENTAL_SPEC:-0}" == 1 ]] || { echo 'Set RUN_EXPERIMENTAL_SPEC=1'; exit 2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ENV_FILE="${NEUROLAB_ENV_FILE:-$ROOT/.env}"
PY="$ROOT/.venv/bin/python"
CA="${NEUROLAB_SSL_CERT_FILE:-/etc/ssl/certs/ca-certificates.crt}"
[[ -f "$ENV_FILE" && -x "$PY" && -f "$CA" ]] || { echo 'Required local spec inputs unavailable'; exit 1; }
source "$ROOT/scripts/lib/gigachat_failover.sh"
run_spec_lane() {
  local lane="$1" credential="$2" model="$3"
  cd "$ROOT"
  GIGACHAT_CREDENTIALS="$credential" docker compose --profile research run --rm --no-deps \
    -e GIGACHAT_CREDENTIALS -e "GIGACHAT_MODEL=$model" -e GIGACHAT_TIMEOUT=120 \
    -e "SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt" \
    -v "$CA:/etc/ssl/certs/ca-certificates.crt:ro" \
    --entrypoint python research /app/scripts/run_experimental_spec.py
}
gigachat_run_with_failover "$ROOT" "$ENV_FILE" "$PY" run_spec_lane
