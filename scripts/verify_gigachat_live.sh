#!/usr/bin/env bash
# Run the opt-in live GigaChat models test on RP5 without printing credentials.
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

set -a
# shellcheck disable=SC1090
source "$env_file"
set +a

export RUN_GIGACHAT_LIVE=1
exec .venv/bin/python -m unittest tests.test_gigachat_live -v
