#!/usr/bin/env bash
# Logical PostgreSQL backup. Parses only required .env values; never executes it.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="/srv/neuro-lab/backups"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
OUT_FILE="${BACKUP_DIR}/neuro-lab-postgres-${TIMESTAMP}.sql.gz"

read_env_value() {
  python3 - "$PROJECT_DIR/.env" "$1" <<'PY'
from pathlib import Path
import sys

path, wanted = map(str, sys.argv[1:])
for raw in Path(path).read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    if line.startswith("export "):
        line = line[7:].lstrip()
    key, marker, value = line.partition("=")
    if marker and key.strip() == wanted:
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        print(value)
        break
else:
    raise SystemExit(f"Missing {wanted} in {path}")
PY
}

if [[ ! -f "$PROJECT_DIR/.env" ]]; then
  echo "Missing .env in ${PROJECT_DIR}; aborting." >&2
  exit 1
fi
if [[ ! -d "$BACKUP_DIR" || ! -w "$BACKUP_DIR" ]]; then
  echo "Backup directory is missing or not writable: ${BACKUP_DIR}" >&2
  exit 1
fi

POSTGRES_USER="$(read_env_value POSTGRES_USER)"
POSTGRES_DB="$(read_env_value POSTGRES_DB)"
: "${POSTGRES_USER:?POSTGRES_USER must not be empty}"
: "${POSTGRES_DB:?POSTGRES_DB must not be empty}"

cd "$PROJECT_DIR"
echo "[$(date -Is)] starting backup -> ${OUT_FILE}"
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" | gzip > "$OUT_FILE"

DUMP_SIZE="$(du -h "$OUT_FILE" | cut -f1)"
echo "[$(date -Is)] backup complete: ${OUT_FILE} (${DUMP_SIZE})"
DELETED="$(find "$BACKUP_DIR" -maxdepth 1 -name 'neuro-lab-postgres-*.sql.gz' -mtime "+${RETENTION_DAYS}" -print -delete | wc -l)"
echo "[$(date -Is)] retention: removed ${DELETED} backup(s) older than ${RETENTION_DAYS} days"
