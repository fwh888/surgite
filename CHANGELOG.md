# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

In progress toward 0.2.0: UI/UX improvements, additional features, and visual polish
on the way to a 1.0.0 release.

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
