#!/bin/bash

set -e

MIGRATION_DIR="/app/migrates"

: "${DB_HOST:?Need to set DB_HOST}"
: "${DB_PORT:?Need to set DB_PORT}"
: "${DB_NAME:?Need to set DB_NAME}"
: "${DB_USER:?Need to set DB_USER}"
: "${DB_PASSWORD:?Need to set DB_PASSWORD}"

export PGPASSWORD=$DB_PASSWORD

# Создаём таблицу для трекинга миграций
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "CREATE TABLE IF NOT EXISTS migrations_applied (filename TEXT PRIMARY KEY);"

if [ "$1" = "up" ]; then
  for file in $(ls $MIGRATION_DIR/*.sql | grep -v '_down\.sql' | sort); do
    fname=$(basename "$file")
    if ! psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT 1 FROM migrations_applied WHERE filename = '$fname';" | grep -q 1; then
      echo "Applying migration: $fname"
      psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$file"
      psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "INSERT INTO migrations_applied (filename) VALUES ('$fname');"
    else
      echo "Skipping already applied: $fname"
    fi
  done

elif [ "$1" = "down" ]; then
  last=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT filename FROM migrations_applied ORDER BY filename DESC LIMIT 1;")
  if [ -z "$last" ]; then
    echo "No migrations to roll back"
    exit 0
  fi

  down_file="${MIGRATION_DIR}/${last%.sql}_down.sql"
  if [ -f "$down_file" ]; then
    echo "Rolling back: $last"
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$down_file"
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "DELETE FROM migrations_applied WHERE filename = '$last';"
  else
    echo "No down file for $last"
    exit 1
  fi

else
  echo "Usage: bash migrate.sh [up|down]"
  exit 1
fi
