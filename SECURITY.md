# Security Policy

## Reporting a vulnerability

Please do not open a public issue for security vulnerabilities.

Report them privately by email to **nhcoleman@proton.me**. Include enough detail
to reproduce — affected component, steps, and impact. You can expect an
acknowledgement within a few days. Once a fix is available, the issue can be
disclosed publicly with credit if you'd like it.

## Supported versions

This project is pre-1.0. Security fixes land on `main`; please test against the
latest `main` before reporting.

## Trust model

standup-gen is designed to run as a **personal, self-hosted tool on a trusted
network** — not as a public, multi-tenant service. Operators should understand:

- **No authentication.** The API and web UI have no built-in auth. Do not expose
  them directly to the public internet; put them behind your own network, VPN, or
  an authenticating reverse proxy.
- **It runs `git` against paths and URLs you give it.** `POST /ingest` runs
  `git log` on a local `repo_path`, and registered repos are cloned from their
  `clone_url` into `REPO_CACHE_DIR` via `git clone`/`fetch`. Treat repo paths and
  URLs as trusted input — only register repositories you control or trust.
- **Provider API keys live in the environment** (`ANTHROPIC_API_KEY`, etc.). Keep
  your `.env` out of version control (it is git-ignored) and protect the host.

Reports that amount to "the unauthenticated API can be abused when exposed to the
internet" are expected behavior given the trust model above, not vulnerabilities.
Reports of a way to escape that model — e.g. injection beyond the documented
`git` surface, reading arbitrary files, or leaking keys — are very much in scope.
