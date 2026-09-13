#!/usr/bin/env bash
set -euo pipefail
cat <<'EOF'
Read-only migration checklist:
1. Identify NVMe by UUID (lsblk -f); do not rely on /dev/nvme0n1 name alone.
2. Make a verified backup of /opt/neuro-lab/.env and PostgreSQL dump.
3. Stop only this project: cd /opt/neuro-lab && docker compose stop.
4. Copy neuro-lab Docker volumes and /srv/neuro-lab to the mounted NVMe.
5. Update compose bind mounts / Docker data-root only after a rollback path is documented.
6. Start neuro-lab, run health checks, and confirm tasks/cost_events before removing any old copy.
EOF
