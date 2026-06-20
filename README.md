# standup-gen

Self-hostable, multi-user standup summaries from your git history.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
<!-- TODO slice 4: add a build-status badge once the forgejo workflow runs on a public host -->

standup-gen reads your git history and writes your standup. Local CLI for a
quick daily summary, FastAPI + Postgres for a team. Self-host the whole thing
on a $4/month VPS. First-party auth, no third-party tracking.

Lean principles: one binary, no SPA framework, no slowapi, no Celery, no Redis.
Reads like a script.

## Quickstart

Two paths. Pick one.

**Self-host the web app** — three commands, full team UI:

```bash
git clone https://codeberg.org/ncoleman/standup-gen.git
cd standup-gen
cp .env.example .env       # set BOOTSTRAP_OWNER_EMAIL=you@example.com
docker compose up -d
```

On first start the app mints an admin invite and logs the token; redeem it
with `uv run standup --redeem-invite <token> --email you@example.com` and
you're in. Full guide: [`docs/self-host.md`](docs/self-host.md).

**One-off summary from a local repo** — no database, no server:

```bash
uv tool install .
standup /path/to/your/repo --since 7.days.ago
```

Add `--summarize` to get AI-written prose (set `ANTHROPIC_API_KEY` first).

## Screenshots

<!-- TODO slice 4: add demo GIF and screenshots of /admin/users, the summary panel, and the share view -->

The demo GIF lands in 0.5.1; until then, see [`docs/self-host.md`](docs/self-host.md)
for the deployment story.

## Why?

- **Self-hostable** — your data, your VPS, your auth. No SaaS account, no
  vendor lock-in.
- **Multi-user** — email + password login, per-user repos and summaries,
  per-user provider keys. (This is the 0.5.0 headline.)
- **No telemetry** — first-party auth, no analytics, no phone-home.
- **Lean** — FastAPI + Postgres + SvelteKit, the whole thing reads
  top-to-bottom.

## Documentation

- [`docs/self-host.md`](docs/self-host.md) — end-to-end self-hosting guide
  (sizing, quickstart, TLS, backup, runbook).
- [`docs/security.md`](docs/security.md) — the threat model and the security
  controls.
- [`docs/migrations/0.4.0-to-0.5.0.md`](docs/migrations/0.4.0-to-0.5.0.md) —
  upgrading a 0.4.0 install.
- [`.env.example`](.env.example) — every configuration variable, with
  defaults.
- [`CHANGELOG.md`](CHANGELOG.md) — release history.

## Development

```bash
uv sync --group dev                 # install deps (incl. dev tools)
docker compose up -d db             # Postgres for local dev
uv run alembic upgrade head         # run migrations
uv run uvicorn backend.api:app --reload
cd frontend && npm install && npm run dev
uv run pytest                       # tests
uv run ruff check . && uv run ruff format --check .   # lint + format
```

See [`AGENTS.md`](AGENTS.md) for the canonical dev quickstart and the
architecture overview.

## Contributing

Contributions are welcome. The project is deliberately minimalist — see the
principles in [`AGENTS.md`](AGENTS.md). Start with
[`CONTRIBUTING.md`](CONTRIBUTING.md) for dev setup and the PR workflow; please
also read [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). For anything
security-sensitive, see [`SECURITY.md`](SECURITY.md).

The canonical repository is on Codeberg:
<https://codeberg.org/ncoleman/standup-gen>.

## License

[MIT](LICENSE) © 2026 Nick Coleman
