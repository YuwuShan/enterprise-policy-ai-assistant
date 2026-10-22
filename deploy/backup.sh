#!/bin/sh
set -eu
cd /opt/oa-assistant
umask 077
mkdir -p deploy/backups
stamp="$(date -u +%Y%m%dT%H%M%SZ)-$(python3 -c 'import uuid; print(uuid.uuid4().hex[:8])')"
snapshot="/app/data/day7-backup-$stamp.db"
archive="deploy/backups/oa-$stamp.db"
# sqlite3.backup creates a consistent snapshot while the OA process remains running.
docker compose -f compose.yaml -f compose.cloud.yaml exec -T oa python -c 'import sqlite3,sys; from oa.db import DB_PATH; source=sqlite3.connect(DB_PATH); target=sqlite3.connect(sys.argv[1]); source.backup(target); target.close(); source.close()' "$snapshot"
docker compose -f compose.yaml -f compose.cloud.yaml cp "oa:$snapshot" "$archive"
chmod 600 "$archive"
python3 deploy/restore_check.py "$archive"
printf 'Backup saved: %s\n' "$archive"
# Snapshots are retained. No file cleanup or live-database overwrite is performed.
