#!/usr/bin/env bash
# Restore a specific backup into a disposable database, never the application DB.
set -euo pipefail
[[ "${RUN_BACKUP_RESTORE_CHECK:-0}" == 1 ]] || { echo 'Set RUN_BACKUP_RESTORE_CHECK=1'; exit 2; }
BACKUP_FILE="${1:?pass an exact backup path}"
[[ "$BACKUP_FILE" =~ ^/srv/neuro-lab/backups/neuro-lab-postgres-[0-9]{8}-[0-9]{6}\.sql\.gz$ && -f "$BACKUP_FILE" ]] || {
  echo 'Invalid backup path'; exit 2;
}
gzip -t "$BACKUP_FILE"
RESTORE_DB="neurolab_restore_check_$(date -u +%Y%m%d%H%M%S)_$$"
[[ "$RESTORE_DB" =~ ^neurolab_restore_check_[0-9]{14}_[0-9]+$ ]] || exit 2
restore_psql() {
  docker compose exec -T -e RESTORE_DB="$RESTORE_DB" postgres sh -c 'psql -X -tA -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$RESTORE_DB"'
}
cleanup() {
  docker compose exec -T -e RESTORE_DB="$RESTORE_DB" postgres sh -c 'dropdb -U "$POSTGRES_USER" "$RESTORE_DB"' >/dev/null
}
docker compose exec -T -e RESTORE_DB="$RESTORE_DB" postgres sh -c 'createdb -U "$POSTGRES_USER" "$RESTORE_DB"'
trap cleanup EXIT
gzip -dc "$BACKUP_FILE" | restore_psql >/dev/null
COUNT="$(printf 'SELECT count(*) FROM schema_migrations;\n' | restore_psql)"
[[ "$COUNT" =~ ^[0-9]+$ && "$COUNT" -ge 16 ]] || { echo 'Restore schema incomplete'; exit 1; }
echo "backup_restore: passed; migrations=$COUNT; disposable_database_removed_on_exit"
