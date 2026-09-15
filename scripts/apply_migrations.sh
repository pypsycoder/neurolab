#!/usr/bin/env bash
# Apply versioned PostgreSQL migrations exactly once.  The Compose .env file is
# never sourced or printed: psql receives its connection parameters only from
# the already-running postgres container.
set -euo pipefail

if [[ "${1:-}" != "--apply" ]]; then
  echo "Dry-run only. Review pending filenames, then rerun: bash scripts/apply_migrations.sh --apply"
  apply=false
else
  apply=true
fi

[[ -f compose.yaml && -d postgres/migrations ]] || {
  echo "Run from the NeuroLab repository root." >&2
  exit 1
}

docker compose config --quiet
postgres_psql() {
  docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
}

postgres_query() {
  docker compose exec -T postgres sh -c 'psql -tA -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
}

postgres_psql <<'SQL'
CREATE TABLE IF NOT EXISTS schema_migrations (
  filename TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
SQL

for migration in postgres/migrations/*.sql; do
  [[ -f "$migration" ]] || continue
  filename="$(basename "$migration")"
  [[ "$filename" =~ ^[0-9]{8}_[0-9]{2}_[A-Za-z0-9_.-]+\.sql$ ]] || {
    echo "Unexpected migration filename: $filename" >&2
    exit 1
  }
  applied="$(printf "SELECT 1 FROM schema_migrations WHERE filename = '%s';\n" "$filename" | postgres_query)"
  if [[ "$applied" == "1" ]]; then
    echo "applied: $filename"
    continue
  fi
  echo "pending: $filename"
  if ! $apply; then
    continue
  fi
  {
    printf 'BEGIN;\n'
    cat "$migration"
    printf '\nINSERT INTO schema_migrations (filename) VALUES ('\''%s'\'');\nCOMMIT;\n' "$filename"
  } | postgres_psql
  echo "applied: $filename"
done
