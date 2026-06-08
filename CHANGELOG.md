# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
