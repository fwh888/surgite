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
uv run standup /path/to/repo --since 2026-05-01 --summarize     # requires a provider API key
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
uv run uvicorn backend.api:app --reload --host "${API_HOST:-127.0.0.1}" --port "${API_PORT:-8000}"

# Run tests
uv run pytest

# Lint and format (ruff). CI runs `ruff check .` and `ruff format --check .`
uv run ruff check .          # lint (add --fix to auto-fix)
uv run ruff format .         # format in place

# Frontend type-check and unit tests (CI runs these alongside the build)
cd frontend && npm run check
cd frontend && npm run test    # vitest
```

## Architecture

This is a Python CLI tool and FastAPI REST API for generating standup summaries from git history. The CLI is standalone (prints/writes formatted log, optionally AI-summarized). The API persists commits in Postgres and exposes them with filtering and summary endpoints.

**Data flow:**

```
CLI:  git.get_raw_log()  →  git.parse_log()  →  formatter.format_log()  →  stdout / file
                                                                        ↘  summarizer.summarize_commits()  →  LLM provider

API:  POST /repos  →  create repo + per-repo BackgroundTask ingest (clone/fetch + git log → CommitRow upsert)
      (lifespan)  →  background asyncio task runs _ingest_all_repos() every INGEST_INTERVAL seconds
      GET /summary  →  SQLAlchemy query (pure read; freshness owned by the scheduler above)  →  JSON
      GET /summary?ai=true[&provider=]  →  formatter.format_log  →  summarizer (async, httpx)  →  LLM provider (rate-limited)
      GET /summary/stream  →  same, streamed token-by-token as SSE
      GET /commits, /commits/{hash}, /providers  →  SQLAlchemy query / provider registry  →  JSON
      POST/GET /summaries, GET /s/{slug}  →  shareable summary links
```

- `backend/models.py` — `Commit` dataclass (`hash`, `date`, `author`, `message`, optional `repo`, `ingested_at`)
- `backend/git.py` — runs `git log` via subprocess; `get_raw_log()` supports `since`, `until`, `author`, and `since_commit` (auto-detects whether `until` is a git ref); `parse_log()` returns `list[Commit]`
- `backend/formatter.py` — formats `Commit` objects to `[date] message (author) <short_hash>` strings
- `backend/summarizer.py` — model-agnostic summarization. A `Provider` dataclass + `PROVIDERS` registry support **anthropic** (Messages API, default), **groq**, and **deepseek** (both OpenAI-compatible chat); all calls go over plain HTTP via `httpx.AsyncClient` (no provider SDK). It's **async**: `generate_summary()` is a coroutine returning `{summary, provider, model}`; `generate_summary_per_repo()` fans out concurrently over `asyncio.gather` with a bounded semaphore (and accepts `settings_by_repo` for per-repo prompt overrides); `stream_summary()` is an async generator of text deltas for SSE; `summarize_commits()` is the CLI's sync text-only wrapper (drives the coroutine via `asyncio.run`); `provider_status()` powers `GET /providers`. Provider is chosen by `LLM_PROVIDER` or per call; identity injected via `STANDUP_USER`/`STANDUP_ROLE`
- `backend/standup.py` — argparse CLI entry point; registered as the `standup` console script in `pyproject.toml`. A local `repo_path` runs offline; `--registered <name>` instead pulls a repo from a running API (`STANDUP_API_URL` / `STANDUP_API_TOKEN`)
- `backend/config.py` — loads `DATABASE_URL` (required), `API_HOST`, `API_PORT`, `SHARE_TTL_DAYS` from env via `python-dotenv` (provider keys are read in `summarizer` at call time)
- `backend/db.py` — SQLAlchemy engine, `Base`, ORM models: `CommitRow`, `RepoRow`, `PromptSettingsRow` (now with a nullable `repo_id` FK — one row per repo plus a global `NULL` row), `SharedSummaryRow` (slug → params JSON + expiry), and the `get_session()` factory
- `backend/schemas.py` — Pydantic request models (`RepoCreate`, `PromptSettingsUpdate`, `ShareCreate`)
- `backend/api.py` — FastAPI app with routes:
  - `POST /repos` — creates a repo and immediately ingests it as a `BackgroundTask` (clone + git log → CommitRow upsert); ingest failures are logged but don't block creation. A lifespan-managed scheduler task also runs `_ingest_all_repos` every `INGEST_INTERVAL` seconds so the DB stays fresh without anyone hitting `/summary`
  - `GET /commits` — paginated list with `since`/`until`/`author`/`repo`/`limit`/`offset` filters
  - `GET /commits/{hash}` — lookup by full or prefix hash; 400 for invalid hex, 404 for not found, 409 for ambiguous prefix
  - `GET /summary` — async, pure read against the DB; aggregates by repo and day. `ai=true` runs the summarizer (capped at `AI_SUMMARY_MAX_COMMITS = 500` to bound token cost) behind a per-IP rate limit; optional `provider=` overrides the default; per-repo summaries use that repo's prompt settings, falling back to the global default. The raw `commits` list is omitted unless `commits=true`. Unknown provider or missing key → 400; provider HTTP failure → 502; rate limit exceeded → 429
  - `GET /summary/stream` — the AI summary as Server-Sent Events: a `meta` frame (stats), per-repo `delta` token frames, a `repo_done`/`repo_error` per repo, then `done`. Same preconditions as `/summary?ai=true`
  - `GET /providers` — lists providers, their default model, and whether each has a key configured (for a UI/CLI to offer a choice)
  - `GET`/`PUT /settings/prompt` — read/update prompt settings; `?repo_id=` scopes to one repo (GET falls back to the global row; PUT 404s on an unknown repo)
  - `POST /summaries` — persist the current summary params behind a slug; `GET /summaries/{slug}` resolves it (404 once expired); `GET /s/{slug}` serves the SPA shell for the read-only share view
  - `GET /health/deep` — DB + `git ls-remote` against one registered repo + provider reachability; 503 names the failing component (`no_repos`/`missing_key` aren't failures)
  - `SQLAlchemyError` is mapped to a 503 globally
- `backend/logging_config.py` — `configure_logging()` sets the root logger from `LOG_LEVEL` (default INFO) and `LOG_FORMAT` (default human-readable; set to `json` for log-shipping-friendly output). Extras on a `LogRecord` are flattened into top-level JSON keys.
- `backend/rate_limit.py` — hand-rolled per-IP token-bucket guard for `/summary?ai=true` (default 5 req / 60 s; override with `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS`). Trusts the first `X-Forwarded-For` entry; the project sits behind Traefik in production.
- `scripts/backup.sh` / `scripts/restore.sh` — `pg_dump` / `psql` over `docker compose exec db` by default; `BACKUP_MODE=local` for a host-side Postgres. `backup.sh` rotates `BACKUP_KEEP` (default 14) dated dumps.
- `alembic/` — migrations; `e5e311c2e5f0_create_commits_table.py` is the initial schema
- `tests/` — pytest suite covering the API; `conftest.py` swaps in a temp SQLite DB and clears tables between tests

- `frontend/` — SvelteKit SPA (Svelte 5 + Tailwind v4) for managing repos and generating summaries; built to static assets and served same-origin by FastAPI via the `StaticFiles` mount at the end of `backend/api.py`

## Planned upgrades

- See [docs/0.4.0-plan.md](docs/0.4.0-plan.md) for the current roadmap (the 0.3.0 release closed out the items in [docs/performance-ui-audit.md](docs/performance-ui-audit.md))

## Environment Variables

| Variable | Notes |
|---|---|
| `DATABASE_URL` | **Required.** `postgresql://standup:standup@localhost:5432/standup` for local dev; the test suite overrides this with a temp SQLite file in `tests/conftest.py` |
| `LLM_PROVIDER` | Summary provider: `anthropic` (default), `groq`, or `deepseek` |
| `ANTHROPIC_API_KEY` / `GROQ_API_KEY` / `DEEPSEEK_API_KEY` | Key for the chosen provider; required for `--summarize` and `GET /summary?ai=true` |
| `ANTHROPIC_MODEL` / `GROQ_MODEL` / `DEEPSEEK_MODEL` | Optional per-provider model override (defaults: `claude-haiku-4-5-20251001`, `llama-3.1-8b-instant`, `deepseek-chat`) |
| `API_HOST` | Defaults to `127.0.0.1` |
| `API_PORT` | Defaults to `8000` |
| `INGEST_INTERVAL` | Seconds between automatic background ingests of all registered repos. Set to `0` to disable the scheduler. |
| `LOG_LEVEL` | Root logger level (default `INFO`). |
| `LOG_FORMAT` | Set to `json` for structured logs (Loki / vector / fluentbit); default is human-readable. |
| `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS` | Per-IP guard on `/summary?ai=true` (default `5` / `60`). |
| `SHARE_TTL_DAYS` | Lifetime of a shared-summary `/s/<slug>` link (default `7`). |
| `STANDUP_API_URL` / `STANDUP_API_TOKEN` | Target API + optional bearer for the CLI's `--registered` mode (default URL `http://localhost:8000`). |
| `STANDUP_USER` | Name injected into the summarizer prompt (e.g. `Alice`); defaults to `the developer` |
| `STANDUP_ROLE` | Optional role description (e.g. `backend engineer at Acme`) appended to the identity in the prompt |

The CLI loads `.env` via `python-dotenv` on startup (and `backend.config` does the same for the API).
