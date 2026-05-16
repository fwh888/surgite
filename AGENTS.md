# AGENTS.md

This file provides guidance to AI coding assistants (Claude Code, Cursor, Copilot, etc.) when working with code in this repository.

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

# Install as a global tool (makes `standup` available anywhere)
uv tool install .

# Start the API (once api.py exists)
uv run uvicorn standup.api:app --reload --host "${API_HOST:-127.0.0.1}" --port "${API_PORT:-8000}"

# Run migrations (once db.py and alembic exist)
uv run alembic upgrade head
```

There is no test suite yet.

## Architecture

This is a Python CLI tool (and planned REST API) for generating standup summaries from git history.

**Current data flow:**

```
git.get_raw_log()  →  git.parse_log()  →  formatter.format_log()  →  stdout / file
                                                                  ↘  summarizer.summarize_commits()  →  Groq API
```

- `standup/models.py` — `Commit` dataclass (`hash`, `date`, `author`, `message`)
- `standup/git.py` — runs `git log` via subprocess; `get_raw_log()` returns raw text, `parse_log()` returns `list[Commit]`
- `standup/formatter.py` — formats `Commit` objects to `[date] message (author) <short_hash>` strings
- `standup/summarizer.py` — sends formatted log to Groq (`llama-3.1-8b-instant`); outputs an "Accomplishments:" bullet list in neutral language; identity is injected via `STANDUP_USER`/`STANDUP_ROLE` env vars
- `standup/standup.py` — argparse CLI entry point; registered as the `standup` console script in `pyproject.toml`

## Planned v1 Upgrade (in progress)

The upgrade adds persistence and a REST API on top of the existing CLI. Follow the build order in `docs/upgrade-plan.md` — do not skip steps. Key additions:

- `standup/config.py` — reads `DATABASE_URL`, `API_HOST`, `API_PORT`, `GROQ_API_KEY` from env
- `standup/db.py` — SQLAlchemy engine, session factory, ORM model for `commits` table; `Commit` gains `repo` and `ingested_at` fields; uses Alembic for migrations
- `standup/api.py` — FastAPI app with routes: `POST /ingest`, `GET /commits`, `GET /commits/{hash}`, `GET /summary`
- CLI gets a new `--ingest <url>` flag to POST to the API instead of printing

**Planned v2** adds a repo management table (`repos`), new CRUD routes, and a web UI (vanilla JS/Alpine.js served by FastAPI, or React/Vite SPA — see `docs/v2-frontend.md`).

## Environment Variables

| Variable | Notes |
|---|---|
| `GROQ_API_KEY` | Required for `--summarize` and `GET /summary?ai=true` |
| `DATABASE_URL` | `postgresql://standup:standup@localhost:5432/standup` — required once the DB layer exists |
| `API_HOST` | Defaults to `127.0.0.1` |
| `API_PORT` | Defaults to `8000` |
| `STANDUP_USER` | Name injected into the summarizer prompt (e.g. `Alice`); defaults to `the developer` |
| `STANDUP_ROLE` | Optional role description (e.g. `backend engineer at Acme`) appended to the identity in the prompt |

The CLI loads `.env` via `python-dotenv` on startup.
