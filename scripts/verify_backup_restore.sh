#!/usr/bin/env bash
# Restore a specific backup into a disposable database, never the application DB.
set -euo pipefail
[[ "${RUN_BACKUP_RESTORE_CHECK:-0}" == 1 ]] || { echo 'Set RUN_BACKUP_RESTORE_CHECK=1'; exit 2; }
BACKUP_FILE="${1:?pass an exact backup path}"
MIN_MIGRATIONS="${NEUROLAB_RESTORE_MIN_MIGRATIONS:-16}"
EXPECT_CODE_RUN="${NEUROLAB_RESTORE_EXPECT_CODE_RUN:-}"
EXPECT_DIAGRAM_CARD="${NEUROLAB_RESTORE_EXPECT_DIAGRAM_CARD:-}"
EXPECT_DOCUMENT_CARD="${NEUROLAB_RESTORE_EXPECT_DOCUMENT_CARD:-}"
EXPECT_TASK_CARD="${NEUROLAB_RESTORE_EXPECT_TASK_CARD:-}"
EXPECT_CYCLE_RUN="${NEUROLAB_RESTORE_EXPECT_CYCLE_RUN:-}"
EXPECT_GAP_RUN="${NEUROLAB_RESTORE_EXPECT_GAP_RUN:-}"
EXPECT_FULLTEXT_RUN="${NEUROLAB_RESTORE_EXPECT_FULLTEXT_RUN:-}"
EXPECT_REJECTED_SOURCE="${NEUROLAB_RESTORE_EXPECT_REJECTED_SOURCE:-}"
[[ -z "$EXPECT_REJECTED_SOURCE" || "$EXPECT_REJECTED_SOURCE" =~ ^[0-9a-f]{64}$ ]] || { echo 'Invalid expected source digest'; exit 2; }
for identity in "$EXPECT_CODE_RUN" "$EXPECT_DIAGRAM_CARD" "$EXPECT_DOCUMENT_CARD" "$EXPECT_TASK_CARD" "$EXPECT_CYCLE_RUN" "$EXPECT_GAP_RUN" "$EXPECT_FULLTEXT_RUN"; do
  [[ -z "$identity" || "$identity" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || { echo 'Invalid expected artifact UUID'; exit 2; }
done
[[ "$MIN_MIGRATIONS" =~ ^[0-9]{1,4}$ && "$MIN_MIGRATIONS" -ge 16 && "$MIN_MIGRATIONS" -le 1000 ]] || { echo 'Invalid minimum migration count'; exit 2; }
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
[[ "$COUNT" =~ ^[0-9]+$ && "$COUNT" -ge "$MIN_MIGRATIONS" ]] || { echo 'Restore schema incomplete'; exit 1; }
if [[ "${NEUROLAB_RESTORE_REQUIRE_EXPERIMENTAL:-0}" == 1 ]]; then
  COMPLETE="$(restore_psql <<'SQL'
SELECT CASE WHEN
  (SELECT count(*) FROM it_research.experimental_specs) >= 1 AND
  (SELECT count(*) FROM it_research.experimental_code_runs WHERE status='candidate_passed') >= 1 AND
  (SELECT count(*) FROM it_research.solution_assets WHERE asset_kind='code_component') >= 1 AND
  (SELECT count(DISTINCT thread_id) FROM it_research.checkpoints) >= 2
THEN 'complete' ELSE 'incomplete' END;
SQL
  )"
  [[ "$COMPLETE" == complete ]] || { echo 'Restore experiment/checkpoints incomplete'; exit 1; }
  echo 'backup_restore: experimental_receipts_assets_checkpoints_present'
fi
if [[ -n "$EXPECT_CODE_RUN" ]]; then
  PRESENT="$(printf "SELECT CASE WHEN EXISTS (SELECT 1 FROM it_research.experimental_code_runs WHERE run_id='%s' AND status='candidate_passed') THEN 'present' ELSE 'missing' END;\n" "$EXPECT_CODE_RUN" | restore_psql)"
  [[ "$PRESENT" == present ]] || { echo 'Expected passing code outcome missing'; exit 1; }
  echo 'backup_restore: exact_passing_code_outcome_present'
fi
if [[ -n "$EXPECT_DIAGRAM_CARD" ]]; then
  PRESENT="$(printf "SELECT CASE WHEN EXISTS (SELECT 1 FROM it_research.diagram_cards WHERE id='%s') THEN 'present' ELSE 'missing' END;\n" "$EXPECT_DIAGRAM_CARD" | restore_psql)"
  [[ "$PRESENT" == present ]] || { echo 'Expected diagram card missing'; exit 1; }
  echo 'backup_restore: exact_diagram_card_present'
fi
if [[ -n "$EXPECT_DOCUMENT_CARD" ]]; then
  PRESENT="$(printf "SELECT CASE WHEN EXISTS (SELECT 1 FROM it_research.document_cards WHERE id='%s') THEN 'present' ELSE 'missing' END;\n" "$EXPECT_DOCUMENT_CARD" | restore_psql)"
  [[ "$PRESENT" == present ]] || { echo 'Expected document card missing'; exit 1; }
  echo 'backup_restore: exact_document_card_present'
fi
if [[ -n "$EXPECT_TASK_CARD" ]]; then
  PRESENT="$(printf "SELECT CASE WHEN EXISTS (SELECT 1 FROM it_research.task_document_cards WHERE id='%s' AND reviewer_status='needs_review' AND policy_version='task-document-v1' AND audit->>'analysis_mode'='task_conditioned_shadow' AND audit->>'card_sha256'=card_sha256) THEN 'present' ELSE 'missing' END;\n" "$EXPECT_TASK_CARD" | restore_psql)"
  [[ "$PRESENT" == present ]] || { echo 'Expected task document card missing'; exit 1; }
  echo 'backup_restore: exact_task_document_card_present'
fi
if [[ -n "$EXPECT_CYCLE_RUN" ]]; then
  PRESENT="$(printf "SELECT CASE WHEN EXISTS (SELECT 1 FROM it_research.code_cycle_assessments WHERE run_id='%s' AND status='passed' AND passed=9 AND total=9 AND evaluator_sha256='28139dd8a14dff8b20270391aaea3a724d59c758e556b7514aed14e8cd4c2322') THEN 'present' ELSE 'missing' END;\n" "$EXPECT_CYCLE_RUN" | restore_psql)"
  [[ "$PRESENT" == present ]] || { echo 'Expected passing cycle assessment missing'; exit 1; }
  echo 'backup_restore: exact_passing_cycle_assessment_present'
fi
if [[ -n "$EXPECT_GAP_RUN" ]]; then
  PRESENT="$(printf "SELECT CASE WHEN EXISTS (SELECT 1 FROM it_research.corpus_gap_rounds WHERE run_id='%s' AND status='completed' AND receipt->>'run_id'=run_id::text AND receipt->>'status'=status) THEN 'present' ELSE 'missing' END;\n" "$EXPECT_GAP_RUN" | restore_psql)"
  [[ "$PRESENT" == present ]] || { echo 'Expected completed gap search missing'; exit 1; }
  echo 'backup_restore: exact_completed_gap_search_present'
fi
if [[ -n "$EXPECT_FULLTEXT_RUN" ]]; then
  PRESENT="$(printf "SELECT CASE WHEN EXISTS (SELECT 1 FROM it_research.corpus_fulltext_attempts WHERE run_id='%s' AND status IN ('completed','license_unverified','document_unverified') AND receipt->>'run_id'=run_id::text AND receipt->>'status'=status) THEN 'present' ELSE 'missing' END;\n" "$EXPECT_FULLTEXT_RUN" | restore_psql)"
  [[ "$PRESENT" == present ]] || { echo 'Expected terminal fulltext preflight missing'; exit 1; }
  echo 'backup_restore: exact_terminal_fulltext_preflight_present'
fi
if [[ -n "$EXPECT_REJECTED_SOURCE" ]]; then
  PRESENT="$(printf "SELECT CASE WHEN (SELECT count(*) FROM (SELECT DISTINCT ON (mission_id) mission_id,decision FROM it_research.selection_receipts WHERE source_key='%s' AND policy_version='research-selection-v1' AND stage='metadata' AND receipt->>'source_key'=source_key ORDER BY mission_id,created_at DESC,id DESC) latest WHERE decision='reject')=6 THEN 'present' ELSE 'missing' END;\n" "$EXPECT_REJECTED_SOURCE" | restore_psql)"
  [[ "$PRESENT" == present ]] || { echo 'Expected six-mission source rejection missing'; exit 1; }
  echo 'backup_restore: exact_six_mission_source_rejection_present'
fi
echo "backup_restore: passed; migrations=$COUNT; disposable_database_removed_on_exit"
