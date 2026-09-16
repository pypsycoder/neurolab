#!/usr/bin/env bash
set -euo pipefail
[[ "${RUN_GIGACHAT_DIAGRAM_CARDS:-0}" == "1" ]] || { echo "Set RUN_GIGACHAT_DIAGRAM_CARDS=1." >&2; exit 2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"; ENV_FILE="${NEUROLAB_ENV_FILE:-$ROOT/.env}"; PY="$ROOT/.venv/bin/python"; CA="${NEUROLAB_SSL_CERT_FILE:-/etc/ssl/certs/ca-certificates.crt}"
[[ -f "$ENV_FILE" && -x "$PY" && -f "$CA" ]] || { echo "Required local Vision inputs are unavailable." >&2; exit 1; }
CREDENTIAL="$(NEUROLAB_ENV_FILE="$ENV_FILE" "$PY" -c 'import os; from dotenv import dotenv_values as d; v=d(os.environ["NEUROLAB_ENV_FILE"]); n=v.get("GIGACHAT_PRIMARY_KEY_ENV","GIGACHAT_CREDENTIALS"); x=v.get(n); assert isinstance(n,str) and n.isidentifier() and x; print(x)')"
MODEL="$(NEUROLAB_ENV_FILE="$ENV_FILE" "$PY" -c 'import os,re; from dotenv import dotenv_values as d; x=d(os.environ["NEUROLAB_ENV_FILE"]).get("GIGACHAT_MODEL","GigaChat-2-Pro"); assert isinstance(x,str) and re.fullmatch(r"[A-Za-z0-9_.:-]{2,80}",x.strip()); print(x.strip())')"
cleanup(){ unset CREDENTIAL MODEL; }; trap cleanup EXIT
cd "$ROOT"
docker compose --profile claim-proposal run --rm -e "GIGACHAT_CREDENTIALS=$CREDENTIAL" -e "GIGACHAT_MODEL=$MODEL" -e "SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt" -v "$CA:/etc/ssl/certs/ca-certificates.crt:ro" --entrypoint python claim-proposal /app/scripts/run_gigachat_diagram_cards.py "$@"
