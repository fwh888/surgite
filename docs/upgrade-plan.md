# standup - upgrade spec

## Goals

- Parse git commit history from local repos into structured data
- Persist commits to PostgreSQL
- Expose commit data via a REST API
- Automate ingestion on a schedule
- Preserve the existing AI-summary feature (Groq) as a CLI option and as an API query param

---

## Current state (pre-upgrade)

The existing CLI lives in `standup/standup.py` and is registered as the `standup` console script in `pyproject.toml`. It already provides:

- `standup/models.py` — `Commit` dataclass with fields `hash`, `date`, `author`, `message`
- `standup/git.py` — `get_raw_log()` and `parse_log()`
- `standup/formatter.py` — `format_commit()` / `format_log()` (uses 7-char short hash)
- `standup/summarizer.py` — Groq-backed `summarize_commits()` (requires `GROQ_API_KEY`)
- `standup/standup.py` — argparse CLI with a positional `repo_path` and flags `--since`, `--until`, `--author`, `--output`, `--summarize`

The upgrade keeps this surface and adds persistence + an HTTP layer on top of it.

---

## API Routes

### `POST /ingest`

Accepts a repo path on the local filesystem. Runs `git log` for the given date range, parses commits, and upserts them into PostgreSQL.

**Request body:**
```json
{
  "repo_path": "/home/nick/dev/Arbiter",
  "since": "2026-05-01",
  "until": "2026-05-14"
}
```

**Response:**
```json
{
  "repo": "Arbiter",
  "inserted": 12,
  "updated": 0,
  "unchanged": 3
}
```

- `since` and `until` are optional. Default: last 7 days.
- `inserted` = new rows. `updated` = rows whose author/message/date changed (e.g. after a rebase). `unchanged` = rows that already matched.
- Returns 400 if `repo_path` does not exist or is not a git repo.

---

### `GET /commits`

Returns a list of commits. All query params are optional.

**Query params:**

| Param | Type | Example |
|---|---|---|
| `since` | date (YYYY-MM-DD) | `?since=2026-05-01` |
| `until` | date (YYYY-MM-DD) | `?until=2026-05-14` |
| `author` | string | `?author=nick` |
| `repo` | string | `?repo=Arbiter` |
| `limit` | int (default 50) | `?limit=100` |
| `offset` | int (default 0) | `?offset=50` |

**Response:**
```json
{
  "total": 24,
  "commits": [
    {
      "hash": "a1b2c3d4e5f6...",
      "short_hash": "a1b2c3d",
      "date": "2026-05-14",
      "author": "Nick Coleman",
      "message": "add scan systemd timer",
      "repo": "Arbiter",
      "ingested_at": "2026-05-14T09:00:00Z"
    }
  ]
}
```

`short_hash` is 7 characters, matching `formatter.py`.

---

### `GET /commits/{hash}`

Returns a single commit by its full SHA or a unique short-SHA prefix (minimum 7 characters).

- 404 if no match.
- 409 if the prefix matches more than one commit; the response lists the candidates.

---

### `GET /summary`

Returns an aggregated view. Useful for generating standup text.

**Query params:** same as `GET /commits`, plus:

| Param | Type | Notes |
|---|---|---|
| `ai` | bool (default false) | If `true`, includes a Groq-generated plain-English summary in `ai_summary`. Requires `GROQ_API_KEY`. |

**Response:**
```json
{
  "period": { "since": "2026-05-07", "until": "2026-05-14" },
  "total_commits": 11,
  "by_repo": {
    "Arbiter": 8,
    "standup-gen": 3
  },
  "by_day": {
    "2026-05-13": 4,
    "2026-05-14": 7
  },
  "commits": [ ... ],
  "ai_summary": null
}
```

---

## CLI Interface

The CLI is invoked via the `standup` console script (defined in `pyproject.toml`). It writes to stdout by default. If a running API is available, it can optionally POST to `/ingest` instead.

`repo_path` is a positional argument, matching the existing CLI.

```bash
# Print commits to stdout
standup /home/nick/dev/Arbiter --since 2026-05-01

# Filter by author
standup /home/nick/dev/Arbiter --since 2026-05-01 --author "Nick Coleman"

# Write output to a file
standup /home/nick/dev/Arbiter --since 2026-05-01 --output standup.txt

# Generate an AI summary (existing feature, uses GROQ_API_KEY)
standup /home/nick/dev/Arbiter --since 2026-05-01 --summarize

# Ingest into the API instead of printing (new in this upgrade)
standup /home/nick/dev/Arbiter --since 2026-05-01 --ingest http://localhost:8000
```

---

## `git log` Command

The core command wrapped by `git.py`:

```bash
git log \
  --since="2026-05-01" \
  --until="2026-05-14" \
  --pretty=format:"%H%x1f%ad%x1f%an%x1f%s" \
  --date=short
```

Fields are separated by the ASCII unit-separator character (`\x1f`, `%x1f` in git's format spec) rather than `|`, so commit messages that contain `|` parse correctly. Each line maps to: `hash <US> date <US> author <US> message`.

**Migration note:** the current `git.py` uses `|` as a delimiter and `line.split("|")`. Switching to `\x1f` is a one-line change in `get_raw_log()` and `parse_log()` and should land as part of step 2 below.

---

## Build Order

Follow this order. Do not jump ahead.

1. **`models.py`** — The `Commit` dataclass already exists with `hash`, `date`, `author`, `message`. Leave it alone for now; it gets extended in step 6 when the DB lands (adds `repo`, `ingested_at`; `short_hash` stays derived).
2. **`git.py`** — Already implemented. Update the delimiter from `|` to `\x1f` (see "`git log` Command" above) so messages containing `|` don't break parsing. Verify with a repo whose history has `|` in a commit message.
3. **`formatter.py`** — Already implemented. No changes needed.
4. **`standup.py` (CLI)** — Already implemented end-to-end (stdout + `--output` + `--summarize`). Verify it still works after the step 2 delimiter change before touching the database.
5. **`config.py`** — Read `DATABASE_URL`, `API_HOST`, `API_PORT`, and `GROQ_API_KEY` from environment variables using `os.environ` (with `python-dotenv` for local dev; already a dependency).
6. **`db.py`** — Define the SQLAlchemy engine, session factory, and the ORM model for the `commits` table. Extend the `Commit` dataclass (or add a separate ORM class) with `repo` and `ingested_at`. Add `alembic` and `sqlalchemy` to `pyproject.toml`, run `alembic init`, and write the first migration.
7. **`api.py`** — Implement routes in this order: `GET /commits`, then `GET /commits/{hash}`, then `POST /ingest`, then `GET /summary`. Add `fastapi` and `uvicorn` to `pyproject.toml`.
8. **Modify `standup.py`** — Add the `--ingest <url>` flag. When passed, POST to the API instead of printing. Requires step 7 to exist first.
9. **Automation** — Write a shell script that calls `POST /ingest` for each repo. Set up a systemd timer or cron job to run it nightly.

---

## Local Development Setup

The project uses `uv`. There is no `requirements.txt`.

```bash
# Start PostgreSQL
docker compose up -d

# Install dependencies (creates/updates .venv from pyproject.toml + uv.lock)
uv sync

# Copy and edit env file
cp .env.example .env

# Run migrations
uv run alembic upgrade head

# Start the API (honors API_HOST / API_PORT from .env)
uv run uvicorn standup.api:app --reload --host "${API_HOST:-127.0.0.1}" --port "${API_PORT:-8000}"

# Run the CLI
uv run standup /home/nick/dev/Arbiter --since 2026-05-01
```

---

## Environment Variables

| Variable | Example | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql://standup:standup@localhost:5432/standup` | Required by the API and migrations. |
| `API_HOST` | `127.0.0.1` | Read by `config.py`; used in the uvicorn invocation above. |
| `API_PORT` | `8000` | Same. |
| `GROQ_API_KEY` | `gsk_...` | Required for `--summarize` and `GET /summary?ai=true`. Optional otherwise. |

---

## `docker-compose.yml` (starter)

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: standup
      POSTGRES_PASSWORD: standup
      POSTGRES_DB: standup
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

---

## Automation (systemd timer)

Once the API is running, create a script `ingest_all.sh`:

```bash
#!/bin/bash
REPOS=(
  "/home/nick/dev/Arbiter"
  "/home/nick/dev/standup-gen"
)

for repo in "${REPOS[@]}"; do
  curl -s -X POST http://localhost:8000/ingest \
    -H "Content-Type: application/json" \
    -d "{\"repo_path\": \"$repo\", \"since\": \"$(date -d '7 days ago' +%F)\"}"
done
```

Pair with a systemd timer or cron entry to run nightly.

---

## Extension Ideas (post-v1)

These are out of scope for the initial build. Come back to them once the core works.

- `PATCH /commits/{hash}/tags` — add tags to a commit (e.g. `["feat", "arbiter"]`). Requires a `tags` column on the `commits` table and a corresponding field in the `GET /commits` response.
- `GET /summary?format=markdown` — return a pre-formatted standup block.
- Multi-author support with a `?author=me` shorthand resolved from config.
- A `--watch` mode on the CLI that auto-ingests on every new commit (via `git fsmonitor` or polling).
