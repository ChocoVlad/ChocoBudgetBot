#!/bin/bash

set -e

DB_PATH="data/bot.db"
MIGRATION_DIR="migrates"

# ensure table for tracking applied migrations exists
sqlite3 $DB_PATH "CREATE TABLE IF NOT EXISTS migrations_applied (filename TEXT PRIMARY KEY);"

if [ "$1" = "up" ]; then
  for file in $(ls $MIGRATION_DIR/*.sql | grep -v '_down\.sql' | sort); do
    fname=$(basename "$file")
    if ! sqlite3 $DB_PATH "SELECT 1 FROM migrations_applied WHERE filename = '$fname';" | grep -q 1; then
      echo "Applying migration: $fname"
      sqlite3 $DB_PATH < "$file"
      sqlite3 $DB_PATH "INSERT INTO migrations_applied (filename) VALUES ('$fname');"
    else
      echo "Skipping already applied: $fname"
    fi
  done

elif [ "$1" = "down" ]; then
  last=$(sqlite3 $DB_PATH "SELECT filename FROM migrations_applied ORDER BY ROWID DESC LIMIT 1;")
  if [ -z "$last" ]; then
    echo "No migrations to roll back"
    exit 0
  fi

  down_file="${MIGRATION_DIR}/${last%.sql}_down.sql"
  if [ -f "$down_file" ]; then
    echo "Rolling back: $last"
    sqlite3 $DB_PATH < "$down_file"
    sqlite3 $DB_PATH "DELETE FROM migrations_applied WHERE filename = '$last';"
  else
    echo "No down file for $last"
    exit 1
  fi

else
  echo "Usage: bash migrate.sh [up|down]"
  exit 1
fi
