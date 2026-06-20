#!/usr/bin/env bash
# Rotate the SECRETS_ENCRYPTION_KEY (slice 2 plan #74).
#
# Re-encrypts every active provider_keys row under the new key and swaps
# the master key in place. The running API process is unaffected — the
# in-process Fernet is built once at import time and cached; restart it
# to pick up the new key. The audit log records who ran the rotation
# (the operator) but the API itself doesn't see this script.
#
# Usage:
#   scripts/rotate-secrets.sh                       # generate a new key, persist
#   scripts/rotate-secrets.sh <new-raw-key>         # use a specific key
#   scripts/rotate-secrets.sh <new-fernet-key>      # 44-char urlsafe-b64 key
#
# Either form is fine; we derive the Fernet key from the input the same
# way backend/secrets.py does (accepting either a Fernet key or an
# arbitrary passphrase).

set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .secrets_key ]; then
  echo "error: no .secrets_key in $(pwd) — start the API at least once to generate one" >&2
  exit 1
fi

NEW_INPUT="${1:-}"
if [ -z "$NEW_INPUT" ]; then
  echo "Generating a fresh Fernet key..."
  NEW_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
else
  NEW_KEY="$NEW_INPUT"
fi

# Re-encrypt every active provider_keys row under the new key. The
# `update` SQL has to use the OLD key to decrypt first; the script
# reads the current .secrets_key (the OLD master), decrypts each row,
# swaps the master, then re-encrypts. We use a single Python
# transaction so a crash mid-rotation doesn't leave the table half-
# encrypted.

OLD_KEY=$(cat .secrets_key)

uv run --quiet python3 - "$OLD_KEY" "$NEW_KEY" <<'PYEOF'
import sys
import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken

OLD_MATERIAL, NEW_MATERIAL = sys.argv[1], sys.argv[2]


def _derive(material: str) -> bytes:
    material = material.strip()
    try:
        decoded = base64.urlsafe_b64decode(material)
        if len(decoded) == 32:
            return material.encode("ascii")
    except (ValueError, base64.binascii.Error):
        pass
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


old_fernet = Fernet(_derive(OLD_MATERIAL))
new_fernet = Fernet(_derive(NEW_MATERIAL))

from backend.db import ProviderKeyRow, session_scope
from backend.config import DATABASE_URL

# Cheap guard: refuse to run on a SQLite test DB. The check is the
# dialect name; if we ever support other backends, this branch needs
# to grow.
if DATABASE_URL.startswith("sqlite"):
    print("refusing to rotate on a SQLite database (test DB?)", file=sys.stderr)
    sys.exit(2)

with session_scope() as s:
    rows = s.query(ProviderKeyRow).filter(ProviderKeyRow.revoked_at.is_(None)).all()
    print(f"re-encrypting {len(rows)} active provider_keys row(s)")
    for row in rows:
        try:
            plain = old_fernet.decrypt(row.encrypted_key.encode("ascii"))
        except InvalidToken:
            print(f"  warning: row {row.id} for user {row.user_id} did not decrypt cleanly; leaving as-is", file=sys.stderr)
            continue
        row.encrypted_key = new_fernet.encrypt(plain).decode("ascii")
    s.commit()
PYEOF

# Persist the new master.
printf '%s\n' "$NEW_KEY" > .secrets_key
chmod 600 .secrets_key

cat <<EOF

Rotation complete.

  - Old master: $(echo "$OLD_KEY" | head -c 8)…
  - New master: $(echo "$NEW_KEY" | head -c 8)…
  - Active rows re-encrypted: see script output above

Next steps:
  1. Restart the standup-gen API to load the new master key.
  2. Back up .secrets_key (chmod 600) somewhere safe.
  3. The old key is no longer valid; if you saved it elsewhere, delete it.
EOF
