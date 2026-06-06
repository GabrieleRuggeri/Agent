#!/bin/sh
set -eu

export PGPASSWORD="${POSTGRES_PASSWORD}"
HOST="${POSTGRES_HOST:-postgres}"
USER="${POSTGRES_USER:-agentic}"
DB="${POSTGRES_DB:-agentic}"

PSQL="psql -h ${HOST} -U ${USER} -d ${DB} -v ON_ERROR_STOP=1"

${PSQL} -f /migrations/000_schema_migrations.sql

for file in /migrations/[0-9]*.sql; do
  version=$(basename "$file" .sql)
  case "$version" in
    000_schema_migrations) continue ;;
  esac

  applied=$(${PSQL} -tAc "SELECT COUNT(*) FROM schema_migrations WHERE version = '${version}'" | tr -d '[:space:]')

  if [ "$applied" = "0" ]; then
    echo "Applying ${version}..."
    ${PSQL} -f "$file"
    ${PSQL} -c "INSERT INTO schema_migrations (version) VALUES ('${version}')"
  else
    echo "Skipping ${version} (already applied)"
  fi
done
