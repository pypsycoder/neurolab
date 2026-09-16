#!/usr/bin/env bash
# Opt-in operational check: print only model identifiers available to the local key.
set -euo pipefail

if [[ "${RUN_GIGACHAT_MODEL_DISCOVERY:-0}" != "1" ]]; then
  echo "Set RUN_GIGACHAT_MODEL_DISCOVERY=1 to list models available to the local key." >&2
  exit 2
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ENV_FILE="${NEUROLAB_ENV_FILE:-$PROJECT_ROOT/.env}"
PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
SYSTEM_CA_BUNDLE="${NEUROLAB_SSL_CERT_FILE:-/etc/ssl/certs/ca-certificates.crt}"
if [[ ! -f "$ENV_FILE" || ! -x "$PYTHON_BIN" || ! -f "$SYSTEM_CA_BUNDLE" ]]; then
  echo "Required local GigaChat inputs are unavailable." >&2
  exit 1
fi

CREDENTIAL="$(NEUROLAB_ENV_FILE="$ENV_FILE" $PYTHON_BIN -c '
import os
from dotenv import dotenv_values
values = dotenv_values(os.environ["NEUROLAB_ENV_FILE"])
name = os.environ.get("NEUROLAB_GIGACHAT_CREDENTIAL_ENV", values.get("GIGACHAT_PRIMARY_KEY_ENV", "GIGACHAT_CREDENTIALS"))
if not isinstance(name, str) or not name.isidentifier(): raise SystemExit("Configured GigaChat credential name is invalid.")
value = values.get(name)
if not value: raise SystemExit("Configured GigaChat credential is absent or empty.")
print(value)
')"

cleanup() { unset CREDENTIAL; }
trap cleanup EXIT

cd "$PROJECT_ROOT"
docker compose --profile claim-proposal run --rm \
  -e "GIGACHAT_CREDENTIALS=$CREDENTIAL" \
  -e "SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt" \
  -v "$SYSTEM_CA_BUNDLE:/etc/ssl/certs/ca-certificates.crt:ro" \
  --entrypoint python claim-proposal -c '
import os
from gigachat import GigaChat
with GigaChat(credentials=os.environ["GIGACHAT_CREDENTIALS"], verify_ssl_certs=True) as client:
    for item in client.get_models().data:
        print(item.id_)
'
