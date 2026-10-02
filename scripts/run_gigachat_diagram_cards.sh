#!/usr/bin/env bash
set -euo pipefail
[[ "${RUN_GIGACHAT_DIAGRAM_CARDS:-0}" == "1" ]] || { echo "Set RUN_GIGACHAT_DIAGRAM_CARDS=1." >&2; exit 2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"; ENV_FILE="${NEUROLAB_ENV_FILE:-$ROOT/.env}"; PY="$ROOT/.venv/bin/python"; CA="${NEUROLAB_SSL_CERT_FILE:-/etc/ssl/certs/ca-certificates.crt}"
[[ -f "$ENV_FILE" && -x "$PY" && -f "$CA" ]] || { echo "Required local Vision inputs are unavailable." >&2; exit 1; }
source "$ROOT/scripts/lib/gigachat_failover.sh"

run_diagram_cards_lane() {
  local _lane="$1" credential="$2" model="$3"
  shift 3
  cd "$ROOT"
  GIGACHAT_CREDENTIALS="$credential" docker compose --profile research run --rm --no-deps \
    -e GIGACHAT_CREDENTIALS -e "GIGACHAT_MODEL=$model" \
    -e "SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt" \
    -v "$CA:/etc/ssl/certs/ca-certificates.crt:ro" \
    --entrypoint python research /app/scripts/run_gigachat_diagram_cards.py "$@"
}

gigachat_run_with_failover "$ROOT" "$ENV_FILE" "$PY" run_diagram_cards_lane "$@"
