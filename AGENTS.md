# AGENTS.md

This file provides guidance to AI coding assistants (Claude Code, Cursor, Copilot, etc.) when working with code in this repository.

## Project principles

This project is deliberately minimalist and easy to maintain. When suggesting or writing code, hold the line on:

- **No dead code, no bloat, no "just in case" branches.** If a check, parameter, or abstraction has no real caller or scenario today, leave it out.
- **No duplicated logic.** If two places do the same thing, extract a shared helper rather than copy-pasting. Prefer one source of truth per behaviour.
- **Use dataclasses (or Pydantic models at boundaries) for structured data** rather than ad-hoc dicts/tuples — they document the shape and make refactors safe.
- **Fewer lines is better, all else equal.** Prefer the simplest version that handles real cases; expand only when reality demands it.

## Commands

```bash
# Install / sync dependencies (uses uv, no requirements.txt)
uv sync

# Run the CLI
uv run standup /path/to/repo --since 7.days.ago
uv run standup /path/to/repo --since 2026-05-01 --summarize     # requires GROQ_API_KEY
uv run standup /path/to/repo --since 2026-05-01 --output out.txt
uv run standup /path/to/repo --since 2026-05-01 --until 2026-05-10
uv run standup /path/to/repo --since 7.days.ago --author "Alice"
uv run standup /path/to/repo --since-commit abc1234               # range from a commit

# Install as a global tool (makes `standup` available anywhere)
uv tool install .

# Start the Postgres dev database
docker compose up -d

# Run migrations
uv run alembic upgrade head

# Start the API
uv run uvicorn standup.api:app --reload --host "${API_HOST:-127.0.0.1}" --port "${API_PORT:-8000}"

# Run tests
uv run pytest
```

## Architecture

This is a Python CLI tool and FastAPI REST API for generating standup summaries from git history. The CLI is standalone (prints/writes formatted log, optionally AI-summarized). The API persists commits in Postgres and exposes them with filtering and summary endpoints.

**Data flow:**

```
CLI:  git.get_raw_log()  →  git.parse_log()  →  formatter.format_log()  →  stdout / file
                                                                        ↘  summarizer.summarize_commits()  →  Groq API

API:  POST /ingest  →  git.get_raw_log/parse_log  →  CommitRow upsert (Postgres)
      GET /commits, /commits/{hash}, /summary  →  SQLAlchemy query  →  JSON
      GET /summary?ai=true  →  formatter.format_log  →  summarizer  →  Groq API
```

- `standup/models.py` — `Commit` dataclass (`hash`, `date`, `author`, `message`, optional `repo`, `ingested_at`)
- `standup/git.py` — runs `git log` via subprocess; `get_raw_log()` supports `since`, `until`, `author`, and `since_commit` (auto-detects whether `until` is a git ref); `parse_log()` returns `list[Commit]`
- `standup/formatter.py` — formats `Commit` objects to `[date] message (author) <short_hash>` strings
- `standup/summarizer.py` — sends formatted log to Groq (`llama-3.1-8b-instant`); outputs an "Accomplishments:" bullet list in neutral language; identity is injected via `STANDUP_USER`/`STANDUP_ROLE` env vars
- `standup/standup.py` — argparse CLI entry point; registered as the `standup` console script in `pyproject.toml`
- `standup/config.py` — loads `DATABASE_URL` (required), `API_HOST`, `API_PORT`, `GROQ_API_KEY` from env via `python-dotenv`
- `standup/db.py` — SQLAlchemy engine, `Base`, `CommitRow` ORM model (`commits` table), and `get_session()` factory
- `standup/schemas.py` — Pydantic request models (`IngestRequest`)
- `standup/api.py` — FastAPI app with routes:
  - `POST /ingest` — runs `git log` against `repo_path`, upserts into `commits` (insert / update / unchanged counts returned)
  - `GET /commits` — paginated list with `since`/`until`/`author`/`repo`/`limit`/`offset` filters
  - `GET /commits/{hash}` — lookup by full or prefix hash; 400 for invalid hex, 404 for not found, 409 for ambiguous prefix
  - `GET /summary` — aggregates by repo and day over the full filtered set; `ai=true` runs the Groq summarizer (capped at `AI_SUMMARY_MAX_COMMITS = 500` to bound token cost)
  - `SQLAlchemyError` is mapped to a 503 globally
- `alembic/` — migrations; `e5e311c2e5f0_create_commits_table.py` is the initial schema
- `tests/` — pytest suite covering the API; `conftest.py` swaps in a temp SQLite DB and clears tables between tests

## Planned upgrades

- CLI `--ingest <url>` flag to POST to the API instead of printing (not yet wired up in `standup/standup.py`)
- **v2:** a repo management table (`repos`), new CRUD routes, and a web UI (vanilla JS/Alpine.js served by FastAPI, or React/Vite SPA — see `docs/v2-frontend.md`)

## Environment Variables

| Variable | Notes |
|---|---|
| `DATABASE_URL` | **Required.** `postgresql://standup:standup@localhost:5432/standup` for local dev; the test suite overrides this with a temp SQLite file in `tests/conftest.py` |
| `GROQ_API_KEY` | Required for `--summarize` and `GET /summary?ai=true` |
| `API_HOST` | Defaults to `127.0.0.1` |
| `API_PORT` | Defaults to `8000` |
| `STANDUP_USER` | Name injected into the summarizer prompt (e.g. `Alice`); defaults to `the developer` |
| `STANDUP_ROLE` | Optional role description (e.g. `backend engineer at Acme`) appended to the identity in the prompt |

The CLI loads `.env` via `python-dotenv` on startup (and `standup.config` does the same for the API).
