# Contributing to surgite

Thanks for your interest in contributing. This project is a small, self-hostable
tool for generating standup summaries from git history. Contributions of all
sizes are welcome — bug reports, docs, tests, and features.

The canonical repository is on GitHub:
<https://github.com/nicoleman0/surgite>.

## Philosophy

surgite is deliberately minimalist and easy to maintain. For agents (and humans)
before writing code, please skim [AGENTS.md](AGENTS.md) — it documents the architecture
and the principles we hold the line on:

- **No dead code, no bloat, no "just in case" branches.**
- **No duplicated logic** — extract a shared helper instead of copy-pasting.
- **Use dataclasses / Pydantic models** for structured data, not ad-hoc dicts.
- **Fewer lines is better, all else equal.**

A change that adds surface area should earn it. When in doubt, open an issue to
discuss before building something large.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (manages Python 3.14+ and dependencies)
- [Task](https://taskfile.dev) (the `task` binary, used for command shortcuts
  like `task openapi-snapshot` and `task openapi-snapshot-check` — see
  [Taskfile.yml](Taskfile.yml) for the full list)
- Node.js 22+ (for the frontend)
- Docker + Docker Compose (for Postgres and the full-app path)

## Development setup

### Backend / CLI

```bash
uv sync --group dev               # install deps incl. dev tools
docker compose up -d db           # start Postgres
uv run alembic upgrade head       # run migrations
uv run uvicorn surgite.api:app --reload   # API at http://127.0.0.1:8000
```

Run the CLI without any of the above:

```bash
uv run surgite /path/to/repo --since 7.days.ago
```

### Frontend

```bash
cd frontend
npm install
npm run dev                       # Vite dev server on :5173, talks to the API on :8000
```

### Full app in one command

```bash
docker compose up --build         # http://localhost:8000
```

## Before you open a PR

Please make sure these all pass locally — CI runs the same checks:

```bash
uv run ruff check .               # lint (add --fix to auto-fix)
uv run ruff format .              # format
uv run mypy surgite/              # type check
uv run pytest                     # backend tests
task openapi-snapshot-check       # OpenAPI snapshot drift gate (see below)

cd frontend
npm run check                     # svelte-check (types + a11y)
npm run test                      # vitest
```

If you add behavior, add a test for it. If you fix a bug, add a test that would
have caught it.

### OpenAPI snapshot

The committed `docs/openapi.json` is the canonical baseline for the project's
public API surface. The CI snapshot gate (`.forgejo/workflows/openapi-snapshot.yml`)
regenerates the dump on every PR and fails the build if the committed baseline
drifts from a fresh dump. This is the 0.6.0 API-stability promise: a route that
exists in the baseline must continue to exist, byte-for-byte, in the dump.

If you change a route, response model, or anything that affects `app.openapi()`:

1. Run `task openapi-snapshot` to regenerate `docs/openapi.json`.
2. Commit the updated `docs/openapi.json` alongside your route change.
3. Push — the workflow will re-run and pass.

`task` is the [Taskfile](https://taskfile.dev) runner. Install with
`brew install go-task` (macOS), `go install github.com/go-task/task/v3/cmd/task@latest`
(Go), or `uv tool install go-task-bin` (any platform with [uv](https://docs.astral.sh/uv/));
see the [Taskfile.yml](Taskfile.yml) for the full task list. `task` is
intentionally preferred over Makefile (declarative YAML, no shell-escaping
gotchas, file-watch sources that skip up-to-date tasks).

## Pull request process

1. Branch off `main` (e.g. `feat/short-description` or `fix/short-description`).
2. Keep PRs focused — one logical change per PR is easier to review.
3. This repo follows [Conventional Commits](https://www.conventionalcommits.org/)
   (`feat:`, `fix:`, `docs:`, `test:`, `build:`, `refactor:`…). Match the style of
   recent history.
4. Update docs when behavior changes — `README.md` for users, `AGENTS.md` for
   architecture, and add a `CHANGELOG.md` entry under `[Unreleased]`.
5. Open the PR against `main` and make sure CI is green.

## Reporting bugs and requesting features

Use the issue templates. For anything security-sensitive, **do not open a public
issue** — see [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions will be licensed under the
project's [MIT License](LICENSE).
