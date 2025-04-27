#!/bin/bash

set -e

DB_HOST="db"
DB_PORT="5432"
DB_NAME="bot_db"
DB_USER="bot_user"
DB_PASSWORD="bot_password"
MIGRATION_DIR="/app/migrates"

export PGPASSWORD=$DB_PASSWORD

# Ждём пока база станет доступна
echo "Waiting for PostgreSQL to be ready..."
until psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c '\q' 2>/dev/null; do
  sleep 1
done
echo "PostgreSQL is ready. Starting migrations..."

# ensure table for tracking applied migrations exists
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "CREATE TABLE IF NOT EXISTS migrations_applied (filename TEXT PRIMARY KEY);"

if [ "$1" = "up" ]; then
  for file in $(ls $MIGRATION_DIR/*.sql | grep -v '_down\.sql' | sort); do
    fname=$(basename "$file")
    if ! psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -tAc "SELECT 1 FROM migrations_applied WHERE filename = '$fname';" | grep -q 1; then
      echo "Applying migration: $fname"
      psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f "$file"
      psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "INSERT INTO migrations_applied (filename) VALUES ('$fname');"
    else
      echo "Skipping already applied: $fname"
    fi
  done

elif [ "$1" = "down" ]; then
  last=$(psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -tAc "SELECT filename FROM migrations_applied ORDER BY filename DESC LIMIT 1;")
  if [ -z "$last" ]; then
    echo "No migrations to roll back"
    exit 0
  fi

  down_file="${MIGRATION_DIR}/${last%.sql}_down.sql"
  if [ -f "$down_file" ]; then
    echo "Rolling back: $last"
    psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f "$down_file"
    psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "DELETE FROM migrations_applied WHERE filename = '$last';"
  else
    echo "No down file for $last"
    exit 1
  fi

else
  echo "Usage: bash migrate.sh [up|down]"
  exit 1
fi
