# Surgite Migration Plan

**Status:** phases 0–3 complete (2026-08-31). GitHub is canonical
(`github.com/nicoleman0/surgite`, `main` protected); the self-hosted Forgejo
instance mirrors it (pull mirror, 8h); Codeberg is synced by the push-mirror
Action (`CODEBERG_MIRROR_TOKEN` configured; verified working after the
repo-path fix in PR #5 — the initial run 404'd on a misspelled path). The
Phase 4 pipeline (publish workflow, `pypi` environment, RELEASING.md) is in
place; remaining: trusted-publisher registration on pypi.org, then cut
`v1.0.0` once the orgs work lands. This document is the authoritative
resume point if a working session is lost mid-migration.

## Context

The PyPI name `standup-gen` is taken by an unrelated project
(`mansourmatta/standup-gen`, 0.1.0). The project is renamed to **surgite**
(Latin: "stand up / arise") — distribution, package, CLI, env vars, infra
defaults, and repo names all become `surgite`. Hosting follows the
touchneedle pattern: **GitHub canonical**, with mirrors on the self-hosted
Forgejo instance and on Codeberg for visibility. First PyPI release is
**v1.0.0**, cut after the orgs work lands. `surgite` was verified free on
PyPI; the old, outdated `nicoleman0/standup-gen` GitHub repo was deleted.

## Decisions (all locked)

| Decision | Choice |
|---|---|
| PyPI distribution | `surgite` |
| Package layout | `backend/` → `surgite/`, `standup.py` → `cli.py`, entry `surgite.cli:main` |
| Env vars | Clean break `STANDUP_*` → `SURGITE_*` (8 vars) at 1.0.0, no aliases; the deprecated `STANDUP_API_TOKEN` alias removed |
| User-state names | Session cookie `__Host-surgite_session`, keyring service `surgite` (with one-time migration shim from `standup-gen`), `~/.config/surgite/` (old-dir session pickup), CSRF value `surgite-web` (frontend+backend atomically). One-time re-login for users |
| Infra defaults | Postgres db/user `surgite`, volume `surgite-repos`, `/var/surgite/repos`, image `surgite-app`, Komodo stack `surgite`, backup glob `surgite-*.sql.gz`; migration notes in `docs/self-host.md` |
| Repos | `surgite` everywhere (GitHub, Forgejo, Codeberg) |
| Tags | Normalized to `vX.Y.Z` (`v0.2.0`–`v0.6.0`) |
| Wheel contents | `surgite` module only; full web app stays Docker/clone |
| Deploy pipeline | Paused; revisit after migration. `.forgejo/workflows/deploy.yml` stays in-repo as the dormant LAN reference |
| First PyPI release | `v1.0.0`, fresh tag post-rename (the publish workflow builds from the release tag, so old tags can't ship the new metadata) |

Historical docs (`docs/releases/*`, `docs/migrations/*`, `docs/0.5.0/0.6.0
plans`, old CHANGELOG entries) keep the old names — they are records of their
era. English prose ("standup summary/update") stays: that is what the tool
produces.

## Phase 0 — Rename — DONE (Forgejo PR #104)

- [x] `git mv backend surgite`; `standup.py` → `cli.py`; imports rewritten
      (incl. lazy imports, `alembic/env.py`, `scripts/dump_openapi.py`, the
      heredoc in `scripts/rotate-secrets.sh`); `keyring.backends` untouched.
- [x] pyproject: `surgite`, entry point, module-name, authors, license,
      classifiers, `[project.urls]` → GitHub; per-file-ignores; `uv lock`.
- [x] Env vars → `SURGITE_*`; `STANDUP_API_TOKEN` alias removed.
- [x] User-state renames incl. keyring/XDG migration shims + tests.
- [x] Infra defaults (compose, Dockerfile, backup/restore, deploy.yml,
      config.py, `SMTP_FROM`).
- [x] Frontend branding; canonical URLs → GitHub; `FastAPI(title="surgite")`;
      OpenAPI snapshot regenerated.
- [x] CHANGELOG `[Unreleased]` entry; `docs/self-host.md` "Upgrading from
      standup-gen" section; cleanup (egg-info, pngs, stale `.claude` ref).
- [x] Full gate green; `uv build` + `twine check` PASSED (wheel ships
      `surgite/` + templates + LICENSE + entry point).
- [x] `cryptography` bumped 49.0.0 → 50.0.1 (PYSEC-2026-3552).

## Phase 1 — GitHub canonical — DONE

- [x] Old `nicoleman0/standup-gen` deleted (user).
- [x] Tags normalized locally; dup `0.2.0`/`v0.2.0` confirmed then dropped.
- [x] `nicoleman0/surgite` created (public, topics, default branch `main`);
      pushed `main` + tags + `feat/1.0.0-invite-org-role` (parked WIP,
      rebased clean onto the rename).
- [x] `main` protected: PRs required, **enforced for admins**, no
      force-pushes/deletions.
- [x] Local remotes: single `origin` → GitHub.

## Phase 2 — Mirrors — DONE (Codeberg token pending)

- [x] Forgejo: old repo deleted; `ncoleman/surgite` is a true **pull mirror**
      (API: `mirror: true`, 8h interval; main + tags verified in sync).
- [x] Codeberg: pull mirrors are **disabled instance-wide** on Codeberg.org
      ("Pull mirrors have been disabled by your site administrator"), so the
      initial migration came over as a static copy. It is kept in sync by the
      `mirror` GitHub Action (push mirror on every push) instead.
- [x] Add `CODEBERG_MIRROR_TOKEN` (Codeberg access token, repository write
      scope) to GitHub repo secrets — configured 2026-08-31; first real
      mirror push verified after the path fix (PR #5).
- [x] Local remote cleanup (done in Phase 1).

## Phase 3 — GitHub Actions CI — DONE

- [x] `.github/workflows/ci.yml`: quality (uv lock check, ruff ×2, mypy,
      pip-audit, pytest) + frontend (npm ci, svelte-check, vitest, build) +
      OpenAPI snapshot gate (`task openapi-snapshot-check`), on push + PR.
- [x] `.forgejo/workflows/ci.yml` + `openapi-snapshot.yml` removed
      (superseded); `deploy.yml` kept as the dormant LAN reference.
- [x] `.github/dependabot.yml` (github-actions ecosystem, monthly).
- [x] README CI badge (resolves the old "build-status badge" TODO).

## Phase 4 — PyPI v1.0.0 — PIPELINE READY, release pending

- [x] `.github/workflows/publish.yml` (touchneedle shape): on
      `release: [published]` → build job (`python -m build`, `twine check`,
      artifact) → publish job (`environment: pypi`, `id-token: write`,
      `pypa/gh-action-pypi-publish@release/v1`). Validated locally: both
      `uv build` and `python -m build` + `twine check` pass; the wheel ships
      `surgite/` + templates + LICENSE + entry point.
- [x] `pypi` GitHub environment created.
- [x] `RELEASING.md` runbook (adapted from touchneedle): gate → bump
      pyproject + `uv lock` → changelog → PR → tag from main → GitHub
      release → auto-publish → verify.
- [ ] One-time (user): register the trusted publisher at
      `pypi.org/manage/account/publishing` — owner `nicoleman0`, repo
      `surgite`, workflow `publish.yml`, env `pypi`. It registers as a
      *pending* publisher; the first successful upload (v1.0.0) creates the
      project on PyPI.
- [ ] README: `pip install surgite` + PyPI/pyversions badges — ride with
      the v1.0.0 release PR (nothing is installable until then).
- [ ] Cut `v1.0.0` once the orgs work lands (invite-org-role WIP parked on
      `feat/1.0.0-invite-org-role`, rebased and ready).

## Standing notes

- Forgejo PR numbers baked into merge messages (`#102`–`#104`) dangle on
  GitHub — accepted.
- `requires-python >= 3.14` is an aggressive floor for a public package;
  revisit if reach matters.
- `psycopg2-binary` is a hard dep even for CLI-only installs — candidate for
  a `postgres` extra someday.
- Old `standup-*.sql.gz` backups won't match the new rotation glob — clean
  or keep manually, once.
- Komodo stack/image rename takes effect when deployment resumes.
- Optional cosmetic: rename the local checkout dir (`standup-gen` →
  `surgite`); needs `git worktree repair` for the linked `austin` worktree
  at `/Users/nicholas/conductor/workspaces/standup-gen/austin`.
