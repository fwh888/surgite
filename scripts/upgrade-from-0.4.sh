#!/usr/bin/env bash
#
# upgrade-from-0.4.sh — migrate a single-operator 0.4.0 install to 0.5.0.
#
# What it does:
#   1. Confirms the DB is at the 0.4.0 head and not already migrated.
#   2. Runs the 0.5.0 schema migration (alembic upgrade head) with your chosen
#      BOOTSTRAP_OWNER_EMAIL. The migration creates that owner and re-associates
#      every existing repo / commit / prompt_settings / shared_summary row with
#      it, so all your 0.4.0 data ends up owned by you.
#   3. Sets that owner's password so you can log in (multi_user) — the migration
#      creates the account without one.
#
# It is safe to re-run: step 2 is a no-op once you're at head, and step 3 just
# re-sets the password.
#
# Usage:
#   ./scripts/upgrade-from-0.4.sh
# Non-interactive (e.g. CI):
#   BOOTSTRAP_OWNER_EMAIL=me@example.com SURGITE_BOOTSTRAP_PASSWORD=... \
#     ./scripts/upgrade-from-0.4.sh --yes
#
# Back up first. There's scripts/backup.sh; or take a plain pg_dump. This
# migration alters every table.

set -euo pipefail

cd "$(dirname "$0")/.."

YES=0
[ "${1:-}" = "--yes" ] && YES=1

# Load .env so POSTGRES_* / DATABASE_URL / BOOTSTRAP_OWNER_EMAIL are available,
# without clobbering anything already exported.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

# uv runs the project's pinned interpreter + deps (alembic, sqlalchemy, argon2).
RUN="uv run"

echo "==> standup-gen 0.4.0 -> 0.5.0 upgrade"

current_rev="$($RUN alembic current 2>/dev/null | awk '{print $1}' | tail -n1 || true)"
head_rev="$($RUN alembic heads 2>/dev/null | awk '{print $1}' | tail -n1)"
echo "    current revision: ${current_rev:-<none>}"
echo "    target revision:  ${head_rev}"

if [ "${current_rev:-}" = "${head_rev}" ]; then
  echo "    Already at head — schema migration will be skipped (password reset still runs)."
fi

# Bootstrap owner email.
EMAIL="${BOOTSTRAP_OWNER_EMAIL:-}"
if [ -z "$EMAIL" ]; then
  read -r -p "Bootstrap owner email (you): " EMAIL
fi
if [ -z "$EMAIL" ]; then
  echo "error: a bootstrap owner email is required." >&2
  exit 1
fi
export BOOTSTRAP_OWNER_EMAIL="$EMAIL"

# Password (silent prompt; not echoed).
PASSWORD="${SURGITE_BOOTSTRAP_PASSWORD:-}"
if [ -z "$PASSWORD" ]; then
  read -r -s -p "Set a password for ${EMAIL}: " PASSWORD; echo
  read -r -s -p "Confirm password: " PASSWORD_CONFIRM; echo
  if [ "$PASSWORD" != "$PASSWORD_CONFIRM" ]; then
    echo "error: passwords don't match." >&2
    exit 1
  fi
fi
if [ -z "$PASSWORD" ]; then
  echo "error: password must not be empty." >&2
  exit 1
fi
export SURGITE_BOOTSTRAP_PASSWORD="$PASSWORD"

if [ "$YES" -ne 1 ]; then
  echo
  echo "This will migrate the database and set ${EMAIL} as the admin owner of all"
  echo "existing data. Make sure you have a backup."
  read -r -p "Proceed? [y/N] " ans
  case "$ans" in
    y|Y|yes|YES) ;;
    *) echo "Aborted."; exit 1 ;;
  esac
fi

echo "==> Running schema migration..."
$RUN alembic upgrade head

echo "==> Setting the owner's password..."
$RUN python - <<'PY'
import os
import sys

from sqlalchemy import select

from surgite.auth import hash_password, normalize_email
from surgite.db import UserRow, get_session

email = normalize_email(os.environ["BOOTSTRAP_OWNER_EMAIL"])
password = os.environ["SURGITE_BOOTSTRAP_PASSWORD"]

with get_session() as s:
    user = s.scalar(select(UserRow).where(UserRow.email == email))
    if user is None:
        sys.exit(f"error: no user {email!r} after migration — did the migration run?")
    user.password_hash = hash_password(password)
    user.is_admin = True
    user.is_active = True
    s.commit()
print(f"    password set for {email} (admin).")
PY

echo
echo "==> Done. Next steps:"
echo "    1. Set AUTH_MODE=multi_user (or single_user) in your .env."
echo "    2. Make sure the app terminates TLS — multi_user refuses plain HTTP."
echo "    3. Restart the app, then log in:"
echo "         surgite --login --email ${EMAIL}"
echo "       or in the browser at /login."
