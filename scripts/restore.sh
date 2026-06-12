#!/usr/bin/env bash
# Restore a standup-gen backup produced by backup.sh.
#
# The dump is a plain pg_dump piped through gzip — restoring is a
# `gunzip | psql` away. Two modes mirror backup.sh: "docker" (the default,
# targets the `db` service) and "local" (host-side psql against a URL).
#
# Usage:
#   scripts/restore.sh path/to/standup-20260101T120000Z.sql.gz
#   BACKUP_MODE=local BACKUP_PG_URL=... scripts/restore.sh ./backup.sql.gz
#
# This script DROPS and recreates the target database before loading.
# It is destructive by design — restore means restore, not merge.

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "usage: $0 <path-to-dump.sql.gz>" >&2
    exit 2
fi

DUMP="$1"
[[ -r "$DUMP" ]] || { echo "[restore] cannot read $DUMP" >&2; exit 1; }

MODE="${BACKUP_MODE:-docker}"
PROJECT="${COMPOSE_PROJECT_NAME:-$(basename "$(pwd)")}"
PG_USER="${POSTGRES_USER:-standup}"
PG_DB="${POSTGRES_DB:-standup}"

echo "[restore] reading $DUMP (mode=$MODE)"

run_restore() {
    # stdin is the gunzipped dump; the inner command applies it.
    gunzip -c "$DUMP" | "$@"
}

if [[ "$MODE" == "docker" ]]; then
    if ! command -v docker >/dev/null 2>&1; then
        echo "[restore] docker not found; set BACKUP_MODE=local or install docker" >&2
        exit 1
    fi
    # Drop+recreate inside the existing db container so the WAL/data dir
    # stays where Postgres expects it. `psql -c` to drop the active
    # connections, then CREATE DATABASE, then load the dump.
    DC="docker compose -p $PROJECT exec -T db"
    $DC psql -U "$PG_USER" -d postgres -v ON_ERROR_STOP=1 -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$PG_DB' AND pid <> pg_backend_pid();" >/dev/null
    $DC dropdb -U "$PG_USER" --if-exists "$PG_DB"
    $DC createdb -U "$PG_USER" "$PG_DB"
    run_restore $DC psql -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=1
elif [[ "$MODE" == "local" ]]; then
    if [[ -z "${BACKUP_PG_URL:-}" ]]; then
        echo "[restore] BACKUP_MODE=local requires BACKUP_PG_URL" >&2
        exit 1
    fi
    # psql URL form doesn't carry a "database to administer"; we need
    # the admin URL explicitly. Reuse BACKUP_PG_URL_ADMIN if set,
    # otherwise derive postgres://... from BACKUP_PG_URL.
    ADMIN_URL="${BACKUP_PG_URL_ADMIN:-${BACKUP_PG_URL%/standup}/postgres}"
    psql "$ADMIN_URL" -v ON_ERROR_STOP=1 -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$PG_DB' AND pid <> pg_backend_pid();" >/dev/null
    dropdb "${BACKUP_PG_URL%/*}/$PG_DB" 2>/dev/null || true
    createdb "${BACKUP_PG_URL%/*}/$PG_DB"
    run_restore psql "$BACKUP_PG_URL" -v ON_ERROR_STOP=1
else
    echo "[restore] unknown BACKUP_MODE: $MODE" >&2
    exit 1
fi

echo "[restore] done"
