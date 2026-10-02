#!/usr/bin/env bash
# Opt-in, one-shot document-card analysis. The GigaChat credential stays in one
# ephemeral container environment and is never printed, stored, or committed.
set -euo pipefail

if [[ "${RUN_GIGACHAT_DOCUMENT_CARD:-0}" != "1" ]]; then
  echo "Set RUN_GIGACHAT_DOCUMENT_CARD=1 for one review-required document card." >&2
  exit 2
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ENV_FILE="${NEUROLAB_ENV_FILE:-$PROJECT_ROOT/.env}"
PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
SYSTEM_CA_BUNDLE="${NEUROLAB_SSL_CERT_FILE:-/etc/ssl/certs/ca-certificates.crt}"
if [[ ! -f "$ENV_FILE" || ! -x "$PYTHON_BIN" || ! -f "$SYSTEM_CA_BUNDLE" ]]; then
  echo "Required local document-card inputs are unavailable." >&2
  exit 1
fi

source "$PROJECT_ROOT/scripts/lib/gigachat_failover.sh"

run_document_card_lane() {
  local _lane="$1" credential="$2" model="$3"
  shift 3
  cd "$PROJECT_ROOT"
  GIGACHAT_CREDENTIALS="$credential" docker compose --profile research run --rm --no-deps \
    -e GIGACHAT_CREDENTIALS \
    -e "GIGACHAT_MODEL=$model" \
    -e "SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt" \
    -v "$SYSTEM_CA_BUNDLE:/etc/ssl/certs/ca-certificates.crt:ro" \
    --entrypoint python research /app/scripts/run_gigachat_document_card.py --persist "$@"
}

gigachat_run_with_failover "$PROJECT_ROOT" "$ENV_FILE" "$PYTHON_BIN" run_document_card_lane "$@"
