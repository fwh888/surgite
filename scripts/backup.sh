#!/usr/bin/env bash
# Back up the standup-gen Postgres database.
#
# The pgdata named volume is the only persistent state in the stack, and
# the user's PBS job (vmid 207 in the homelab) is the intended off-host
# consumer of these dumps. This script writes one gzip-compressed pg_dump
# per run to $BACKUP_DIR with a date-stamped filename.
#
# Two modes, in order of preference:
#   1. Inside the `db` container (default). Works whether the host has
#      pg_dump installed or not; only docker compose is required.
#   2. On the host against a local Postgres. Set BACKUP_MODE=local and
#      BACKUP_PG_URL to enable.
#
# Env vars (all optional):
#   BACKUP_DIR             output dir (default: ./backups)
#   COMPOSE_PROJECT_NAME   project name passed to docker compose
#                          (default: directory name; matches what Komodo
#                          uses to prefix the stack's containers)
#   BACKUP_MODE            "docker" (default) or "local"
#   BACKUP_PG_URL          Postgres URL (only used when BACKUP_MODE=local)
#   BACKUP_KEEP            how many recent dumps to keep (default: 14)

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP="${BACKUP_KEEP:-14}"
MODE="${BACKUP_MODE:-docker}"
PROJECT="${COMPOSE_PROJECT_NAME:-$(basename "$(pwd)")}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
FILENAME="standup-${TS}.sql.gz"
TARGET="${BACKUP_DIR}/${FILENAME}"

mkdir -p "$BACKUP_DIR"

echo "[backup] writing $TARGET (mode=$MODE)"

if [[ "$MODE" == "docker" ]]; then
    if ! command -v docker >/dev/null 2>&1; then
        echo "[backup] docker not found on PATH; set BACKUP_MODE=local or install docker" >&2
        exit 1
    fi
    # `docker compose exec -T db pg_dump` streams to stdout; we gzip in
    # this shell. The `-T` disables a TTY (pg_dump insists on getting
    # its stdin closed cleanly when piped to gzip).
    docker compose -p "$PROJECT" exec -T db \
        pg_dump -U "${POSTGRES_USER:-standup}" -d "${POSTGRES_DB:-standup}" --no-owner \
        | gzip -9 > "$TARGET"
elif [[ "$MODE" == "local" ]]; then
    if [[ -z "${BACKUP_PG_URL:-}" ]]; then
        echo "[backup] BACKUP_MODE=local requires BACKUP_PG_URL" >&2
        exit 1
    fi
    pg_dump "$BACKUP_PG_URL" --no-owner | gzip -9 > "$TARGET"
else
    echo "[backup] unknown BACKUP_MODE: $MODE" >&2
    exit 1
fi

echo "[backup] wrote $(du -h "$TARGET" | cut -f1)"

# Rotate old dumps, keeping the most recent $KEEP. ls -1t sorts by mtime
# newest-first; tail drops the first $KEEP lines and deletes the rest.
if [[ -d "$BACKUP_DIR" ]]; then
    mapfile -t OLD < <(ls -1t "$BACKUP_DIR"/standup-*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) || true)
    for f in "${OLD[@]:-}"; do
        [[ -n "$f" ]] && rm -f -- "$f" && echo "[backup] pruned $f"
    done
fi

echo "[backup] done"
