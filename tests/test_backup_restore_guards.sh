#!/usr/bin/env bash
# Invalid caller identities must stop before touching Docker or any database.
set -euo pipefail
SCRIPT="${1:?pass restore verifier path}"
for name in NEUROLAB_RESTORE_EXPECT_CODE_RUN NEUROLAB_RESTORE_EXPECT_DIAGRAM_CARD NEUROLAB_RESTORE_EXPECT_CYCLE_RUN; do
  status=0
  output="$(env RUN_BACKUP_RESTORE_CHECK=1 "$name=not-a-uuid;DROP TABLE tasks" bash "$SCRIPT" /srv/neuro-lab/backups/neuro-lab-postgres-20261003-120000.sql.gz 2>&1)" || status=$?
  [[ "$status" == 2 && "$output" == 'Invalid expected artifact UUID' ]] || { echo 'UUID guard failed'; exit 1; }
done
status=0
output="$(env RUN_BACKUP_RESTORE_CHECK=1 bash "$SCRIPT" /srv/neuro-lab/backups 2>&1)" || status=$?
[[ "$status" == 2 && "$output" == 'Invalid backup path' ]] || { echo 'Backup path guard failed'; exit 1; }
echo 'backup_restore_guards: passed; no Docker/database calls'
