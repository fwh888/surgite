# Production Readiness & Open-Source Plan

Status: **Draft** · Owner: @ncoleman · Target: first public-ready release (`v1.0.0`)

The core works: CLI, FastAPI + Postgres backend, and a SvelteKit web UI (with dark
mode) are all functional. This document is the plan to take it from "works on my
machine" to something a stranger can self-host, trust, and contribute to.

Hosting (**decided**): keep the self-hosted **Forgejo** instance (on the maintainer's
LAN) as the canonical dev/CI/CD home, with **Codeberg** as the public mirror and the
project's public face. No infra migration for now — instead, every public-facing file
is kept **host-agnostic** (no LAN hostnames, self-contained compose) so a future flip
to Codeberg-primary needs zero rework. Because the LAN Forgejo URL isn't publicly
reachable, all public docs/links point at the Codeberg mirror
(`codeberg.org/ncoleman/standup-gen`) — never the LAN address, and not `github.com`.

> **Maintainer infra note:** the published `docker-compose.yml` now builds from source
> and reads the registry image from `APP_IMAGE`. The Komodo deploy must set
> `APP_IMAGE=<registry-host>/ncoleman/standup-gen-app:latest` in the stack env, or prod
> will build from source instead of pulling. `deploy.yml` now reads `vars.REGISTRY_HOST`
> and `vars.KOMODO_URL` (set these in Forgejo repo settings → Actions → Variables).

---

## Where we are today

| Area | State |
| --- | --- |
| CLI (`standup`) | Working |
| REST API (ingest / commits / summary / providers / repos CRUD) | Working |
| Web UI (SvelteKit SPA, dark mode) | Working |
| CI | mypy · uv.lock drift · pip-audit · pytest · frontend build |
| Tests | API only (`tests/test_api.py`, ~316 lines). No CLI, summarizer, or frontend tests |
| Deploy | Forgejo registry → Komodo (maintainer's private infra; compose + workflow now host-agnostic) |
| Docs | `README.md`, `AGENTS.md`, this plan. `docs/` now exists |
| Contributor files | None (no CONTRIBUTING, CoC, SECURITY, issue/PR templates, CHANGELOG) |
| Linting / formatting | None (no ruff for Python, no lint script for frontend) |

---

## Guiding principles

Carried from `AGENTS.md`: minimalist, no dead code, no bloat, fewer lines is
better. "Professional" here means *trustworthy and approachable*, not *enterprise
heavy*. Every item below should earn its place.

---

## Phase 1 — Truth & trust (docs are correct)

*Goal: nothing in the repo lies to a new reader. This is the cheapest, highest-trust work; do it first.*

- [x] Rewrite `README.md` to reflect reality: UI is shipped, component status table
      updated, "planned/v2" framing dropped.
- [x] Fix the broken `docs/v2-svelte-plan.md` link (removed from `README.md` and
      `AGENTS.md`; the historical plan is superseded by the shipped UI).
- [x] Point clone/install instructions at the canonical Codeberg URL.
- [x] Add a "Quickstart" that gets a user to a running UI via `docker compose up`,
      separate from the CLI-only path. (Added `build: .` to compose so it builds from
      source when the private image isn't reachable.)
- [x] Document the data model / config / LLM-provider story in a user-facing form
      (Configuration table + API endpoints in `README.md`).
- [x] Replace the default `sv` scaffolding boilerplate in `frontend/README.md`.
- [x] Add a **screenshot** of the web UI (light + dark) to the README — both show a
      generated summary and a public (`codeberg.org`) repo URL, no LAN hostnames.
- [ ] `LICENSE` — confirm MIT is the intended license and the year/holder is right
      (currently `2026 Nick Coleman`). *Open question for the maintainer.*

## Phase 2 — Easy self-hosting

*Goal: a stranger clones, runs one or two commands, and has it working — no private infra.*

- [x] **Portable `docker-compose.yml`**: bundles Postgres + the app (which serves the
      built frontend); `docker compose up --build` yields a working app, no `*.lan`.
- [x] Pin/parameterize the published image — builds from source by default, optional
      `APP_IMAGE` override for a registry image.
- [x] **First-run experience**: migrations run automatically (Dockerfile CMD); empty
      `.env` works; missing DB → 503, missing/unknown provider key → graceful (no AI,
      not a crash). The old `.env.example` shipped a fake non-empty `ANTHROPIC_API_KEY`
      placeholder that made first-run AI fail with an auth error — now keys default empty.
- [x] Complete, accurate `.env.example` (root rewritten, compose-first; `frontend/`
      already documented `VITE_API_BASE`).
- [x] Document running **without** an LLM key (README quickstart + `.env.example` note).
- [x] Health/readiness endpoint (`GET /health`, DB-checked) + documented `curl` check
      + container healthcheck wired into compose. Covered by a test.
- [ ] Optional: publish images to a public registry (Codeberg/ghcr) so users don't
      have to build. *(Deferred — depends on the "prebuilt images?" open question.)*

## Phase 3 — Code quality & tests

*Goal: contributions can be reviewed and merged with confidence; CI catches regressions.*

- [x] Add **ruff** (lint + format) for Python; wired into CI (`ruff check` +
      `ruff format --check`) and documented in `AGENTS.md`. Config selects E/F/I/UP/B;
      `conftest.py` gets an E402 per-file ignore for its deliberate env-before-import.
- [x] Add a frontend **typecheck** step — `npm run check` (svelte-check) now runs in
      the CI `frontend` job before the build.
- [x] Expand tests beyond the API (32 → 78 backend tests + a frontend suite):
  - [x] CLI `--summarize` / `--output` paths (`backend/standup.py`).
  - [x] `summarizer.py` provider selection / status / both HTTP paths (mocked) / errors.
  - [x] `git.py` URL detection, repo-name parsing, log parsing, real-repo roundtrip.
  - [x] `formatter.py` formatting.
  - [x] Frontend: vitest + a `renderMarkdown` test (incl. XSS-escaping) — establishes
        the pattern and wires `npm run test` into CI.
- [ ] Tighten mypy (consider `--strict` incrementally) and document the bar.
- [ ] Add a coverage signal (not necessarily a hard gate) so gaps are visible.

## Phase 4 — Contributor onramp

*Goal: a motivated stranger can figure out how to help in one sitting.*

- [x] `CONTRIBUTING.md` — dev setup, the lint/format/type/test commands, PR + commit
      conventions, the minimalist principles; links AGENTS.md and SECURITY.md.
- [x] `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1, contact filled in).
- [x] `SECURITY.md` — private reporting + an explicit trust model (no auth; runs `git`
      against given paths/URLs; keys in env) so operators know it's a trusted-network tool.
- [x] Issue & PR templates under `.forgejo/` (`ISSUE_TEMPLATE/bug_report.md`,
      `feature_request.md`, `PULL_REQUEST_TEMPLATE.md`).
- [x] `CHANGELOG.md` (Keep a Changelog), seeded under `[Unreleased]` toward 1.0.0.
- [x] Link contributor docs from the README; AGENTS.md stays the architecture source.
- [ ] Label a few **good first issues** once the tracker is public. *(Post-merge, manual.)*

## Phase 5 — Product polish

*Goal: it feels finished, not a prototype.*

- [ ] Error / empty / loading states across the UI (no repos yet, ingest failed,
      provider key missing, network error).
- [ ] Accessibility pass (keyboard nav, focus states, color contrast in both themes,
      semantic markup).
- [ ] Copy-to-clipboard polish for the standup summary (the core user action).
- [ ] Responsive/mobile check.
- [ ] Consistent loading + toast/feedback patterns.
- [ ] Optional: a small docs/landing page (could be the README rendered on Codeberg
      Pages) with the screenshot and one-paragraph pitch.

---

## Release gate — what "v1.0.0" requires

A tagged `v1.0.0` ships when:

1. README is accurate and has a screenshot + 5-minute quickstart. *(P1)*
2. `docker compose up` works on a clean machine with no private infra. *(P2)*
3. CI runs lint + typecheck + tests for **both** backend and frontend, green. *(P3)*
4. CONTRIBUTING, CoC, SECURITY, and issue/PR templates exist. *(P4)*
5. No broken links, no "planned" features that are actually shipped (or vice versa).
6. `version` bumped in `pyproject.toml` (0.1.0 → 1.0.0) and `frontend/package.json`,
   with a `CHANGELOG.md` entry and a git tag.

Phase 5 polish can continue past v1.0.0 — it shouldn't block the first public release.

---

## Suggested ordering

P1 (docs truth) → P2 (self-hosting) → P3 (quality/tests) in parallel with P4
(contributor files) → P5 (polish, ongoing). P1 is near-free and removes the most
embarrassing gaps; P2 is what actually lets people *use* it; P3/P4 are what let
people *trust and join* it.

## Open questions

- [x] ~~Forgejo-primary vs Codeberg-primary?~~ **Decided:** stay Forgejo-primary,
      Codeberg as public mirror; keep all public files host-agnostic.
- [ ] Add GitHub as a *second* public mirror too, or Codeberg-only?
- [ ] Publish prebuilt images to a public registry, or build-from-source only, for v1?
- [ ] Is MIT final? Confirm before adding contributor docs that reference it.
