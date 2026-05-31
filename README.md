# standup-gen

Generates standup summaries from git commit history. Started as a CLI and is growing into a small self-hosted web app for managing repos, ingesting commits on a schedule, and grabbing a daily or weekly summary from the browser instead of re-running CLI flags.

## What this is meant to be

Three layers, built in order:

1. **CLI** (`standup`) — point it at a git repo, get a formatted log or an AI-written prose summary. Standalone, no database required for this path.
2. **REST API** (FastAPI + Postgres) — ingests commits into a `commits` table and exposes filterable read endpoints plus an AI summary endpoint. Backs both the automation scripts and the web UI.
3. **Web frontend** — a browser UI for registering repos, triggering ingests, and generating copy-pasteable standup summaries (for Slack/email) without touching the terminal. See [docs/v2-frontend.md](docs/v2-frontend.md) for the sketch.

The CLI stays first-class. The API and UI exist so the tool can be run as a small personal service across multiple repos without re-running commands by hand.

## Components

| Component | Status | Entry point |
|---|---|---|
| CLI | working | `standup` / `uv run standup` |
| REST API | working (commit ingest + read + summary) | `uv run uvicorn standup.api:app --reload` |
| Repo management routes (`/repos`) | planned | see [docs/v2-frontend.md](docs/v2-frontend.md) |
| Web UI | planned | see [docs/v2-frontend.md](docs/v2-frontend.md) |

## Setup

1. Install [uv](https://docs.astral.sh/uv/) if you don't have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. Clone the repo and install `standup` as a global command:

```bash
git clone https://github.com/nicoleman0/standup-gen.git
cd standup-gen
uv tool install .
```

3. Add `uv`'s tool bin to your PATH (only needed once):

```bash
uv tool update-shell
```

Restart your terminal or `source ~/.zshrc` — after that, `standup` will be available anywhere.

4. Set a provider API key (only needed for `--summarize` / `?ai=true`). The default provider is Anthropic; set `LLM_PROVIDER` to `groq` or `deepseek` to switch:

**zsh** (`~/.zshrc`):

```zsh
echo 'export ANTHROPIC_API_KEY=your_key_here' >> ~/.zshrc
source ~/.zshrc
```

Or create a `.env` file in the repo root:

```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_key_here
DATABASE_URL=postgresql://standup:standup@localhost:5432/standup
```

5. For the API / web app path, start Postgres and run migrations:

```bash
docker compose up -d
uv run alembic upgrade head
uv run uvicorn standup.api:app --reload
```

## CLI usage

```bash
standup /path/to/your/repo --since 1.day.ago --summarize
```

| Flag | Default | Description |
|------|---------|-------------|
| `repo_path` | *(required)* | Path to the git repository |
| `--since` | `7.days.ago` | How far back to look |
| `--until` | `now` | End of the range |
| `--author` | *(none)* | Filter to a specific author |
| `--summarize` | off | Use AI to write a prose summary |
| `--output` | *(stdout)* | Write output to a file instead |

## API endpoints (current)

- `POST /ingest` — runs `git log` against a repo path and upserts commits
- `GET /commits` — paginated list with `since`/`until`/`author`/`repo` filters
- `GET /commits/{hash}` — lookup by full or prefix hash
- `GET /summary` — aggregate by repo and day; `?ai=true` runs the AI summarizer (optional `&provider=anthropic|groq|deepseek`)
- `GET /providers` — list available summary providers and the default

See [AGENTS.md](AGENTS.md) for the full architecture overview.
