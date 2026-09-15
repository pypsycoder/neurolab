#!/usr/bin/env bash
set -euo pipefail

apply=false
[[ "${1:-}" == "--apply" ]] && apply=true
command -v docker >/dev/null || { echo "Docker is not installed; stop before changing the system."; exit 1; }
docker compose version >/dev/null || { echo "Docker Compose plugin unavailable; stop before changing the system."; exit 1; }

if $apply; then
  sudo install -d -m 0750 /opt/neuro-lab /opt/neuro-lab/inventory
  sudo install -d -m 0750 /srv/neuro-lab/logs /srv/neuro-lab/cache /srv/neuro-lab/artifacts /srv/neuro-lab/backups
  echo "Directories prepared. Create /opt/neuro-lab/.env from .env.example before starting services."
else
  cat <<'EOF'
Preflight passed. No system change was made.
To create only isolated directories, rerun: bash scripts/bootstrap.sh --apply
Before docker compose up, inspect inventory and create .env with unique secrets.
EOF
fi
