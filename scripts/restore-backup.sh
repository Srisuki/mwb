#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 /absolute/path/to/mwb_audit_TIMESTAMP.dump" >&2
  exit 2
fi

backup_file=$1
if [ ! -f "$backup_file" ]; then
  echo "Backup file does not exist: $backup_file" >&2
  exit 2
fi

case "$backup_file" in
  /*) ;;
  *) echo "Use an absolute backup path." >&2; exit 2 ;;
esac

echo "This replaces the current mwb_audit database from: $backup_file"
printf "Type RESTORE to continue: "
read confirmation
[ "$confirmation" = "RESTORE" ] || { echo "Restore cancelled."; exit 1; }

docker compose stop backend frontend backup
docker compose cp "$backup_file" postgres:/tmp/mwb_restore.dump
docker compose exec -T postgres sh -c 'dropdb --if-exists --username="$POSTGRES_USER" "$POSTGRES_DB" && createdb --username="$POSTGRES_USER" "$POSTGRES_DB" && pg_restore --exit-on-error --no-owner --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" /tmp/mwb_restore.dump'
docker compose start backend frontend backup
echo "Restore complete. Verify /health and sign in before resuming work."
