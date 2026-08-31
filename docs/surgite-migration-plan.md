# Surgite Migration Plan

**Status:** in progress (branch `feat/1.0.0-surgite-rename`). Started 2026-08-31.
This document is the authoritative plan and resume point if a working session is
lost mid-migration.

## Context

The PyPI name `standup-gen` is taken by an unrelated project
(`mansourmatta/standup-gen`, 0.1.0). The project is renamed to **surgite**
(Latin: "stand up / arise") — distribution, package, CLI, env vars, infra
defaults, and repo names all become `surgite`. Hosting moves to the
touchneedle pattern: **GitHub canonical** (`github.com/nicoleman0/surgite`),
with pull mirrors on the self-hosted Forgejo instance and on Codeberg
(`ncolman/surgite`) for visibility. First PyPI release is **v1.0.0**, cut after
the orgs work lands. `surgite` was verified free on PyPI (404 on the JSON API)
and `nicoleman0/surgite` was verified free on GitHub; the old, outdated
`nicoleman0/standup-gen` GitHub repo (April snapshot, unrelated tag history)
has been deleted.

## Decisions (all locked)

| Decision | Choice |
|---|---|
| PyPI distribution | `surgite` |
| Package layout | `backend/` → `surgite/`, `standup.py` → `cli.py`, entry `surgite.cli:main` |
| Env vars | Clean break `STANDUP_*` → `SURGITE_*` (8 vars) at 1.0.0, no aliases; drop the deprecated `STANDUP_API_TOKEN` alias code |
| User-state names | Rename session cookie (`__Host-surgite_session`), keyring service (`surgite`, with a one-time migration shim from `standup-gen`), `~/.config/surgite/` (old-dir session pickup), CSRF value `surgite-web` (frontend+backend atomically). One-time re-login for users |
| Infra defaults | Rename all: Postgres db/user `surgite`, volume `surgite-repos`, `/var/surgite/repos`, image `surgite-app`, Komodo stack `surgite`, backup glob `surgite-*.sql.gz`; migration notes in `docs/self-host.md` |
| Repos | `surgite` everywhere (GitHub, Codeberg, Forgejo) |
| Tags | Normalize to `vX.Y.Z` before seeding GitHub (add `v0.3.0`/`v0.4.0` at those commits, delete unprefixed + duplicate `0.2.0`) |
| Wheel contents | `surgite` module only; full web app stays Docker/clone |
| Deploy pipeline | Paused (pull-mirrored Forgejo runs no Actions); revisit after migration. `.forgejo/workflows/deploy.yml` stays in-repo as the dormant LAN reference |
| First PyPI release | `v1.0.0`, fresh tag post-rename (the publish workflow builds from the release tag, so old tags can't ship the new metadata) |

Historical docs (`docs/releases/*`, `docs/migrations/*`, `docs/0.5.0-plan.md`,
`docs/0.6.0-plan.md`, old CHANGELOG entries) keep the old names — they are
records of their era. English prose ("standup summary/update") stays: that is
what the tool produces. Only branding and identifiers change.

## Phase 0 — Rename (on Forgejo, its CI validates it) — branch `feat/1.0.0-surgite-rename`

- [ ] `git mv backend surgite`; `git mv surgite/standup.py surgite/cli.py`;
      rewrite `backend` imports in all 25 files — mind the lazy in-function
      imports (`summarizer.py`, `api.py`), `alembic/env.py`,
      `scripts/dump_openapi.py`, the Python heredoc in
      `scripts/rotate-secrets.sh`; **skip** the `keyring.backends` false
      positive in `cli_auth.py`.
- [ ] `pyproject.toml`: `name = "surgite"`, `surgite = "surgite.cli:main"`,
      `module-name = "surgite"`, authors, `license`/`license-files`,
      classifiers, `[project.urls]` → GitHub; fix per-file-ignores paths;
      `uv lock` regen.
- [ ] Env vars → `SURGITE_*` in code, tests, compose, `.env.example`, docs,
      local `.env`.
- [ ] User-state names (cookie/keyring+shim/XDG/CSRF) incl. test pins
      (`test_cli_auth.py:90,219`, `api.test.ts`, `download.test.ts`).
- [ ] Infra defaults (compose, Dockerfile, `backup.sh`, `restore.sh`,
      `rotate-secrets.sh`, `deploy.yml`, `config.py` defaults, `SMTP_FROM`).
- [ ] Frontend branding (~15 files) + `SummaryPanel` CLI echo + `download.ts`
      suffix + `StatusBar` codeberg link → GitHub.
- [ ] Docs: README/AGENTS/CONTRIBUTING/SECURITY/self-host/api-stability/
      security-support/1.0.0-plan + `.forgejo/ISSUE_TEMPLATE`; canonical URLs
      → `github.com/nicoleman0/surgite`; migration notes in `self-host.md`.
- [ ] `FastAPI(title="surgite")`; fix `schemas.py` description; regenerate
      OpenAPI snapshot (`task openapi-snapshot`).
- [ ] CHANGELOG `[Unreleased]` rename entry.
- [ ] Cleanup: stale `standup_gen.egg-info/`, unreferenced
      `docs/{dark,light}-standup.png`, stale `.claude/commands` ref,
      `.gitignore` comment, add `.DS_Store` to root `.gitignore`.
- [ ] Full gate: `uv lock --check`, `uv sync`, `ruff check .`,
      `ruff format --check .`, `mypy surgite/`, `pytest -q`, frontend
      `npm run check`/`test`/`build`, `task openapi-snapshot-check`.
- [ ] Push branch to Forgejo, open PR, merge. Then rebase
      `feat/1.0.0-invite-org-role` (parked WIP) onto renamed main — import
      fixes only.

## Phase 1 — GitHub canonical

- [ ] (Done) Delete outdated `nicoleman0/standup-gen`.
- [ ] Normalize tags locally: create `v0.3.0`/`v0.4.0` at the `0.3.0`/`0.4.0`
      commits; delete `0.2.0`/`0.3.0`/`0.4.0` unprefixed tags.
- [ ] `gh repo create nicoleman0/surgite --public`; rewire remotes: rename
      `origin`→`codeberg` (temporary), GitHub becomes `origin`; push `main`,
      normalized tags, kept branches (seed from local — it is ahead of
      Codeberg); repoint `branch.main.remote`.
- [ ] Protect `main` (require PRs), touchneedle-style.
- [ ] Verify canonical URLs from Phase 0 resolve.

## Phase 2 — Mirrors (pull from GitHub)

- [ ] Forgejo: delete old `standup-gen` repo (kills the push mirror and the
      PRs/issues there — accepted; they survive in merge-commit messages
      only), then Migrate as a **pull mirror** of
      `https://github.com/nicoleman0/surgite` (git-only; default sync ~8h).
- [ ] Codeberg: delete/re-create `ncolman/surgite` as a pull mirror the same
      way (if the name is tombstoned: rename old → create mirror → delete
      old). Check Codeberg's mirror policy while there.
- [ ] Local end state: single `origin` → GitHub; drop mirror remotes.
      Optional dir rename `/Users/nicholas/dev/standup-gen` → `surgite` —
      then `git worktree repair` for the linked `austin` worktree.

## Phase 3 — GitHub Actions CI

- [ ] Port `.forgejo/workflows/ci.yml` + `openapi-snapshot.yml` to
      `.github/workflows/` (setup-uv, setup-node for the frontend job,
      go-task for the snapshot check; `ubuntu-latest` instead of
      `runs-on: host`; `mypy surgite/`).
- [ ] Keep `.forgejo/workflows/deploy.yml` in-repo as the dormant LAN
      self-host reference until deployment is revisited.
- [ ] Dependabot, GitHub Actions ecosystem only, monthly (touchneedle style).

## Phase 4 — PyPI v1.0.0

- [ ] `.github/workflows/publish.yml` (touchneedle shape): on
      `release: [published]` → build job (`python -m build`, `twine check`,
      artifact) → publish job (`environment: pypi`, `id-token: write`,
      `pypa/gh-action-pypi-publish@release/v1`). The `uv_build` backend
      works under `python -m build`. Wheel = `surgite` module only.
- [ ] One-time: register the trusted publisher at
      `pypi.org/manage/account/publishing` (owner `nicoleman0`, repo
      `surgite`, workflow `publish.yml`, env `pypi`); create the `pypi`
      GitHub environment.
- [ ] Adapt touchneedle's `RELEASING.md` (bump pyproject **and uv.lock**,
      changelog, PR, tag `vX.Y.Z` from main, cut the Release → auto-publish,
      verify on the simple index).
- [ ] README: `pip install surgite`, PyPI/pyversions/CI badges; resolve the
      build-status-badge TODO.
- [ ] Cut `v1.0.0` once the orgs work lands.

## Standing notes

- Forgejo PR numbers baked into merge messages (`#102`, `#103`) dangle on
  GitHub — accepted (history rewrite is off the table under mirrors).
- `requires-python >= 3.14` is an aggressive floor for a public package;
  revisit if reach matters.
- `psycopg2-binary` is a hard dep even for CLI-only installs — candidate for
  a `postgres` extra someday.
- Old `standup-*.sql.gz` backups won't match the new rotation glob — clean
  or keep manually, once.
- Komodo stack/image rename takes effect when deployment resumes.
- `frontend/package.json` name stays `frontend` (generic, internal).
