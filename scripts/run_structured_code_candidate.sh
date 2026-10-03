#!/usr/bin/env bash
set -euo pipefail
[[ "${RUN_STRUCTURED_CODE_CANDIDATE:-0}" == 1 ]] || { echo 'Set RUN_STRUCTURED_CODE_CANDIDATE=1'; exit 2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
source "$ROOT/scripts/lib/gigachat_failover.sh"
run_candidate_lane() {
  local lane="$1" credential="$2" model="$3"
  shift 3
  cd "$ROOT"
  GIGACHAT_CREDENTIALS="$credential" docker compose --profile research run --rm --no-deps \
    -e GIGACHAT_CREDENTIALS -e GIGACHAT_SCOPE -e "GIGACHAT_MODEL=$model" -e GIGACHAT_TIMEOUT=180 \
    -e SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    -v "$ROOT/runtime/ca/ca-certificates.crt:/etc/ssl/certs/ca-certificates.crt:ro" \
    --entrypoint python research /app/scripts/run_structured_code_candidate.py "$@"
}
gigachat_run_with_failover "$ROOT" "$ROOT/.env" "$ROOT/.venv/bin/python" run_candidate_lane "$@"
