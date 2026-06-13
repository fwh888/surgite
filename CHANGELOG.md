# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] - 2026-06-13

Operational hardening plus a round of real features: a background ingest
scheduler, structured logging, rate limiting, backup/restore, streaming AI
summaries, shareable links, per-repo prompt overrides, a CLI↔API bridge, and
a deep health check.

### Added

- A background ingest scheduler (asyncio task started in the FastAPI lifespan)
  that runs `_ingest_all_repos` every `INGEST_INTERVAL` seconds (default 300,
  set to `0` to disable). The DB now stays fresh without anyone hitting
  `/summary`, and the endpoint is a pure read.
- Structured logging: `LOG_LEVEL` (default `INFO`) and `LOG_FORMAT=json`
  controls. In JSON mode, `LogRecord` extras are flattened to top-level keys
  for log-shipping pipelines.
- Per-IP rate limit on `/summary?ai=true` (hand-rolled token bucket; default
  5 requests / 60 s, configurable via `RATE_LIMIT_REQUESTS` and
  `RATE_LIMIT_WINDOW_SECONDS`). Trusts the first `X-Forwarded-For` entry.
- `scripts/backup.sh` and `scripts/restore.sh` for off-host `pg_dump` /
  `pg_restore`. Default mode runs `pg_dump` inside the `db` container via
  `docker compose exec`; `BACKUP_MODE=local` runs against a host-side
  Postgres. `backup.sh` keeps the most recent `BACKUP_KEEP` dumps
  (default 14) and prunes older ones.
- Streaming AI summaries over SSE (`GET /summary/stream`). The web UI fills
  each repo card in token-by-token as the provider streams, instead of
  blocking on a spinner for the whole fan-out; cancellation still works
  mid-stream.
- Shareable summary links. "share link" copies a `/s/{slug}` URL that
  re-runs the saved query in a read-only view; "copy markdown" puts the whole
  summary on the clipboard for pasting into Slack/Jira. Slugs live in a
  `shared_summaries` table and expire after `SHARE_TTL_DAYS` (default 7),
  swept by the scheduler and rejected on read once expired.
- Per-repo prompt settings. `prompt_settings` gains a `repo_id` so a repo can
  carry its own tone/identity/format, falling back to the global default;
  `GET`/`PUT /settings/prompt?repo_id=` and a scope selector in the config
  panel drive it.
- `standup --registered <name>` pulls a repo registered in a running API
  (`STANDUP_API_URL`, optional bearer `STANDUP_API_TOKEN`) instead of a local
  clone, so the CLI can reuse what the web app already ingested.
- `GET /health/deep` — DB connectivity, a `git ls-remote` probe against one
  registered repo, and provider reachability, returning 503 with the failing
  component. A meatier target for an uptime check than `/health`.

### Changed

- `/summary` no longer triggers a git fetch. Freshness is owned by the
  scheduler; the per-repo ingest on `POST /repos` still runs as a FastAPI
  `BackgroundTask` so newly added repos show up immediately.
- The `INGEST_TTL` / `_INGEST_CACHE` band-aid and the `repo=` filter on
  `_ingest_all_repos` are gone. A user opening the app now gets fresh data
  on the first click without paying the fetch cost, and a re-rendered
  summary no longer hits the network.
- The summarizer is now async: provider calls go through `httpx.AsyncClient`
  and the per-repo fan-out runs on `asyncio.gather` instead of a
  `ThreadPoolExecutor`, so a burst of concurrent `/summary?ai=true` requests
  no longer exhausts FastAPI's request threadpool. `requests` is dropped from
  the runtime dependencies in favour of `httpx`.
- `/summary` omits the full `commits` list by default (it was hundreds of KB
  the UI never rendered). Pass `commits=true` to include it, or use
  `/commits`.

### Fixed

- Dead link rot: `AGENTS.md` and `README.md` no longer reference
  `docs/production-readiness-plan.md` (deleted during 0.2.0 cleanup).
  The current roadmap is `docs/0.4.0-plan.md`, and
  `docs/performance-ui-audit.md` carries a closed-out banner.
- The `repo_id` backfill migration (`b2c3d4e5f6a7`) aborted with a
  `NotNullViolation` on databases holding commits orphaned by the pre-0.3.0
  delete bug (a repo's commits weren't removed with it). Those orphans are now
  dropped before the `NOT NULL` is enforced, unblocking the upgrade.

## [0.3.0] - 2026-06-11

UI polish, configurable AI prompts, and a sweep of performance and correctness
fixes ahead of 1.0.0.

### Added

- A summary stats block above the generated cards: total commits, repos touched,
  and active days, a per-repo commit-count bar chart, and a daily-activity
  sparkline (with quiet days filled in) over the selected period.
- User-configurable AI prompt settings — a dedicated `prompt_settings` table and
  UI panel for customising the system prompt and identity fields used during
  summarization.
- Loading skeletons for the repo list and prompt settings panel while data is
  being fetched.
- Markdown rendering enhancements in summaries: ordered lists, links, and
  fenced code blocks now render properly.
- A help overlay (F1) and a per-commit "view raw log" export option.
- A standalone performance & UI/UX audit document
  (`docs/performance-ui-audit.md`) tracking remaining work toward 1.0.0.

### Changed

- The `commits.date` column has been migrated from `String` to `Date` with
  supporting indexes, replacing string-comparison date filtering in queries.
- The theme system uses a single source of truth: the hardcoded theme list has
  been removed and the DOM `data-theme` attribute is now normalised after
  hydration to prevent flash-of-wrong-theme on first paint.
- The summary panel validates the custom date range and shows user feedback
  when `since` is after `until`.
- The version string surfaced in the status bar is now driven from a single
  source instead of being duplicated across components.

### Fixed

- Deleting a repo now removes all of its commits from the `commits` table
  (previously only the `RepoRow` was deleted, leaving orphaned commits).
- The `repos.name` column has a unique constraint, and `repos` → `commits` now
  cascade on delete to keep referential integrity intact.
- The author filter escapes SQL `LIKE` wildcards (`%`, `_`) in user input, and
  the repo filter now does an exact match instead of a partial `ILIKE`.
- Ingest runs as a background task, so a slow ingest no longer blocks the
  HTTP request that triggered it.
- The summary-generation request now respects `AbortController` cancellation
  when the user navigates away or hits a control mid-request.

### Performance

- Ingest skips repos that are already up to date and bulk-upserts commits in
  batches, cutting wall-clock time on large repos.
- Per-repo AI summaries are generated in parallel; a combined cross-repo
  summary is now opt-in rather than the default, removing the cost when it's
  not wanted.
- A single SQLAlchemy session is injected per request via FastAPI `Depends`,
  removing per-call session churn.

## [0.2.0] - 2026-06-08

UI/UX improvements, additional summary controls, and a terminal-inspired visual
rework on the way to a 1.0.0 release.

### Added

- Toast notifications for repo add / delete actions and clipboard errors,
  so successful actions now give clear feedback instead of failing silently.
- Empty-state hint and a "No commits in this period" state in the summary panel.
- Summary controls: a custom date range (in addition to the 7/14/30-day presets)
  and an optional author filter.
- Export a repo's summary to a file — Markdown for AI summaries, text for raw logs.
- An app icon / logo mark and a descriptive page title, replacing the default
  SvelteKit scaffolding favicon.

### Changed

- **Terminal aesthetic rework:** the web UI is now a pseudo-terminal — monospace
  (JetBrains Mono), terminal-window chrome, prompt-style section headers
  (`~/repos ❯`, `~/summary ❯`), command-style buttons (`❯ generate`,
  `❯ add-repo`), and a CLI command echo above each generated summary.
- Commits are now fetched automatically when a summary is generated; the separate
  manual ingest step (endpoint and button) has been removed.
- **Multi-theme colorschemes:** replaced the light/dark toggle with six
  colorschemes switched by a `data-theme` attribute: GitHub Dark (default),
  Light, Nord, Catppuccin Mocha, Solarized Dark, and a classic green/amber
  Terminal scheme. All components use semantic CSS tokens (`bg-surface`,
  `text-fg`, `border-border`, etc.) — no more `dark:` variants.
- **Personality:** log-line toasts (`[ ok ]` / `[fail]`), a vim/tmux-style
  status bar (`[standup] scheme: nord │ v0.2.0`), braille spinners (`⣾⣽⣻…`)
  for loading states, typewriter fade-in for AI summaries, a help overlay
  (F1), and a Konami-code CRT scanline easter egg. All animations respect
  `prefers-reduced-motion`.
- AI summaries are now grouped into thematic Markdown sections (`## Theme` + bullets)
  instead of one flat "Accomplishments" list.
- Accessibility and responsive polish: visible keyboard-focus rings on all controls,
  a focus action in place of the `autofocus` attribute, a labelled icon instead of
  the decorative globe emoji, and small-screen layout tweaks.

## [0.1.0] - 2026-06-07

The initial foundation — a working CLI, REST API, and self-hostable web UI, with CI,
tests, and contributor docs in place.

### Added

- CLI (`standup`) to generate a formatted git log or an AI-written prose summary.
- REST API (FastAPI + Postgres) for ingesting commits and serving filtered reads,
  per-repo summaries, and repo management (`/repos` CRUD + ingest).
- Model-agnostic AI summaries with Anthropic (default), Groq, and DeepSeek providers.
- SvelteKit web UI for managing repos and generating summaries, with a light/dark theme.
- One-command self-hosting via `docker compose up --build`.
- `GET /health` liveness + database-readiness endpoint, wired into the container healthcheck.
- CI: ruff lint/format, mypy, pip-audit, pytest, plus a frontend type-check and vitest suite.
- Contributor docs: CONTRIBUTING, SECURITY, CODE_OF_CONDUCT, and issue/PR templates.

### Changed

- `docker-compose.yml` builds from source by default; a pre-built registry image is
  opt-in via `APP_IMAGE`.
- `.env.example` defaults provider keys to empty, so the app runs the non-AI paths
  without any key configured.
