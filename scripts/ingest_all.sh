#!/bin/bash
set -euo pipefail

# Ingest all tracked repos into the database via POST /ingest.
#
# Repo paths are read from a config file (default: repos.txt next to this
# script) instead of being hardcoded here. One absolute path per line; blank
# lines and lines starting with '#' are ignored.
#
# Override the list location with REPO_LIST and the API with API_URL:
#   REPO_LIST=/etc/standup/repos.txt API_URL=http://localhost:9000 ./ingest_all.sh
#
# NOTE (v2): this config file is a stopgap. The v2 plan (docs/v2-frontend.md)
# replaces it with a `repos` table managed through the API, at which point this
# script loops over the registered repos instead of reading a flat file.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_LIST="${REPO_LIST:-$SCRIPT_DIR/repos.txt}"
API_URL="${API_URL:-http://localhost:8000}"

# macOS date syntax; on Linux use: SINCE=$(date -d '7 days ago' +%F)
SINCE=$(date -v-7d +%F)

if [[ ! -f "$REPO_LIST" ]]; then
  echo "Repo list not found: $REPO_LIST" >&2
  echo "Create it (one absolute repo path per line) or set REPO_LIST." >&2
  exit 1
fi

while IFS= read -r repo || [[ -n "$repo" ]]; do
  # Skip blank lines and comments.
  [[ -z "${repo// }" || "$repo" == \#* ]] && continue

  echo "Ingesting $repo..."
  curl -s -X POST "$API_URL/ingest" \
    -H "Content-Type: application/json" \
    -d "{\"repo_path\": \"$repo\", \"since\": \"$SINCE\"}" \
    | python3 -m json.tool
done < "$REPO_LIST"
