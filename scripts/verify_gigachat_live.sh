#!/usr/bin/env bash
# Run the opt-in live GigaChat models test on RP5 without printing credentials.
# Compose-style .env files are data, not shell code: never source them.
set -euo pipefail

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Run ./scripts/bootstrap_rp5.sh first." >&2
  exit 1
fi

env_file="${NEUROLAB_ENV_FILE:-.env}"
if [[ ! -f "$env_file" ]]; then
  echo "Local environment file not found: $env_file" >&2
  exit 1
fi

# By default the SDK test reads GIGACHAT_CREDENTIALS.  A deployment that keeps
# multiple provider keys may opt in to another *variable name* without exposing
# its value: NEUROLAB_GIGACHAT_CREDENTIAL_ENV=GIGACHAT_KEY_A1.
export RUN_GIGACHAT_LIVE=1
export NEUROLAB_ENV_FILE="$env_file"
export NEUROLAB_GIGACHAT_CREDENTIAL_ENV="${NEUROLAB_GIGACHAT_CREDENTIAL_ENV:-GIGACHAT_CREDENTIALS}"

exec .venv/bin/python -c '
import os
import sys

from dotenv import dotenv_values

env_file = os.environ["NEUROLAB_ENV_FILE"]
credential_name = os.environ["NEUROLAB_GIGACHAT_CREDENTIAL_ENV"]
credential = dotenv_values(env_file).get(credential_name)
if not credential:
    raise SystemExit(f"Credential variable {credential_name!r} is absent or empty in the local env file.")

# The contract test must keep TLS verification enabled and use its reviewed API
# endpoint even if the running Compose stack has legacy provider settings.
os.environ["GIGACHAT_CREDENTIALS"] = credential
os.environ["GIGACHAT_BASE_URL"] = "https://api.giga.chat/v1"
os.environ["GIGACHAT_VERIFY_SSL_CERTS"] = "true"
os.execv(sys.executable, [sys.executable, "-m", "unittest", "tests.test_gigachat_live", "-v"])
'
