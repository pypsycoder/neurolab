#!/usr/bin/env bash
# Prepare the isolated RP5 development/test environment. No secrets are read.
set -euo pipefail

if [[ ! -f "pyproject.toml" ]]; then
  echo "Run this script from the neurolab repository root." >&2
  exit 1
fi

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
