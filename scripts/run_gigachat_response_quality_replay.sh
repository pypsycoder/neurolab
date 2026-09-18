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

MODEL="$(NEUROLAB_ENV_FILE="$ENV_FILE" $PYTHON_BIN -c '
import os, re
from dotenv import dotenv_values
value = dotenv_values(os.environ["NEUROLAB_ENV_FILE"]).get("GIGACHAT_MODEL", "GigaChat-2-Pro")
if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{2,80}", value.strip()):
    raise SystemExit("Configured GigaChat model is invalid.")
print(value.strip())
')"

cleanup() { unset CREDENTIAL MODEL; }
trap cleanup EXIT

cd "$PROJECT_ROOT"
docker compose --profile claim-proposal run --rm \
  -e "GIGACHAT_CREDENTIALS=$CREDENTIAL" \
  -e "GIGACHAT_MODEL=$MODEL" \
  -e "SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt" \
  -v "$SYSTEM_CA_BUNDLE:/etc/ssl/certs/ca-certificates.crt:ro" \
  --entrypoint python claim-proposal /app/scripts/run_gigachat_response_quality_replay.py --persist "$@"
