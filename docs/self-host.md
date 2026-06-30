# Self-hosting standup-gen

standup-gen is a small, self-hostable standup summary tool. You give it a Postgres
and a handful of env vars and it runs: a CLI for local use, a FastAPI + Postgres
backend that ingests git history on a schedule, and a SvelteKit web UI for repo
management and summary generation. First-party sessions and email + password login
— no third-party tracking, no telemetry, no phone-home.

This page is the end-to-end guide. The deep dives live in
[`docs/security.md`](security.md) (threat model) and
[`docs/migrations/0.4.0-to-0.5.0.md`](migrations/0.4.0-to-0.5.0.md)
(upgrading a 0.4.0 install).

## Hardware sizing

A small team (under 20 users, under 100 repos, daily summaries) runs fine on
**1 vCPU, 512 MB RAM, 2 GB disk** — that's a $4/month VPS. Postgres is the only
real consumer; the API itself is mostly idle. No GPU, no exotic hardware.

Step up to **2 vCPU, 1 GB RAM** for a larger team (50+ users, more repos, AI
summaries running frequently) and you won't need to think about it again. Disk
grows with the `commits` table; budget ~50 KB per commit and you'll be over-
provisioned.

Single shared Postgres is fine. Don't bother with read replicas until you have
hundreds of users actively hitting `/summary?ai=true` at once.

## Quickstart

Five minutes, three commands, one env var:

```bash
git clone https://codeberg.org/ncoleman/standup-gen.git
cd standup-gen
cp .env.example .env
```

Edit `.env`: set `BOOTSTRAP_OWNER_EMAIL=you@example.com`. The first start with no
admin account logs an invite token for that address; you'll redeem it in a
moment. Leave everything else at its default.

```bash
docker compose up -d
docker compose logs -f app   # watch for the invite token
```

When you see the log line `No admin account exists. Bootstrap an admin by
redeeming this invite for you@example.com:  standup --redeem-invite <token>`,
redeem it from the same checkout:

```bash
uv run standup --redeem-invite <token> --email you@example.com
```

That's it. The app created the database, ran migrations, generated a Fernet
master key for at-rest encryption, wrote it to `.secrets_key` (chmod 600, owned
by the API process — back it up), minted the admin invite, and on redeem created
your account with a password you set in the prompt. You're logged in; invite
the rest of your team from the web UI (admins land in slice 2; until then the
API endpoints are in `docs/security.md`).

## TLS

`multi_user` mode **refuses to start over plain HTTP** — the session cookie uses
the `__Host-` prefix, which the browser will only accept on a `Secure` cookie,
which requires HTTPS. Pick one:

**Traefik + step-ca (homelab).** The step-ca ACME issuer hands out real
certificates to anything on your tailnet; Traefik terminates TLS and forwards
plain HTTP to the app. Configure the router for the standup-gen hostname and
the `X-Forwarded-For` header is set correctly out of the box.

**Caddy + Let's Encrypt (external).** The shortest Caddyfile that works:

```caddyfile
standup.example.com {
    reverse_proxy localhost:8000
}
```

Caddy fetches and renews the cert automatically.

**Local dev.** `caddy trust` (Caddy's local CA) or `mkcert` for a browser-
trusted localhost cert. As a last resort, `DEBUG=true` drops the `__Host-` prefix
and `Secure` flag on the cookie so the app runs over plain HTTP — but only in
`off` or `single_user` mode, and never in production.

If you serve this on the public internet over plain HTTP, your session cookies
travel in cleartext. Don't.

## Backup and restore

`scripts/backup.sh` dumps the database to a gzip file in `BACKUP_DIR` (default
`./backups`), rotating the last `BACKUP_KEEP` (default 14) days of dumps.
`scripts/restore.sh <file>` drops the database and loads a dump back in.

```bash
scripts/backup.sh                          # one dump, keep last 14
BACKUP_KEEP=30 scripts/backup.sh           # keep last 30
scripts/restore.sh backups/standup-…sql.gz # point-in-time restore
```

Both default to running `pg_dump` / `psql` inside the compose `db` container
(`BACKUP_MODE=docker`). Set `BACKUP_MODE=local` to run them against a host-side
Postgres. Wire this into a daily cron on a Proxmox Backup Server (PBS) — the
named volume `pgdata` plus the dated dumps in `BACKUP_DIR` is the whole
recovery story.

Back up `.secrets_key` **separately** — it is the Fernet master that decrypts
`provider_keys`, and the backup script does not include it. If you lose it, the
ciphertext in any DB backup is unreadable.

## Upgrade

Coming from 0.4.0? Read [`docs/migrations/0.4.0-to-0.5.0.md`](migrations/0.4.0-to-0.5.0.md).
The short version: the migration is one-shot, it backfills every existing row
to one bootstrap owner, and on the first start with the new image the app mints
an admin invite for `BOOTSTRAP_OWNER_EMAIL`. `scripts/upgrade-from-0.4.sh` runs
the whole thing interactively (or non-interactively with
`STANDUP_BOOTSTRAP_PASSWORD` in the environment).

Upgrading 0.5.x → 0.5.y is a normal `docker compose pull && docker compose up -d`
followed by `uv run alembic upgrade head` (the API runs it on startup, so this
is usually implicit). Migrations are forward-only.

## CLI session storage

`standup --login` / `--redeem-invite` save a session cookie so later
`standup --registered <name>` calls reuse it. Where that cookie lives:

- **By default, the OS keyring** — the login keychain on macOS, the Secret
  Service on Linux (GNOME Keyring, KWallet, KeePassXC — whatever you have),
  the Credential Manager on Windows. Nothing to configure.
- **A 0600 file** at `$XDG_CONFIG_HOME/standup/session` (default
  `~/.config/standup/session`) when no keyring backend is available — a
  headless server or CI runner with no D-Bus / Secret Service falls back to
  this automatically.
- **Forced file mode** with `standup --login --keyring-file`, for headless
  boxes where you'd rather not depend on keyring detection, or for scripted
  setups.

Upgrading from 0.5.x: an existing 0600 session file is migrated into the
keyring the first time the CLI reads it (then the file is overwritten and
removed). No action needed. The 0600 file remains fully supported in 0.6.0;
per [`docs/api-stability.md`](api-stability.md) any future change to this
behaviour goes through the deprecation cycle.

## Email configuration

Email is used for self-serve password reset (`POST /auth/password-reset`).
You don't have to configure it:

- **Unconfigured (default).** With `SMTP_HOST` unset, the app uses the
  *logging mailer*: the reset email — including the reset link — is written
  to the structured log stream instead of being sent. A self-hoster who
  hasn't set up mail still gets working password reset; the link lands where
  they already look for operational signals (`docker compose logs`).
- **SMTP.** Set the `SMTP_*` vars to send real mail:

  ```bash
  SMTP_HOST=smtp.example.com
  SMTP_PORT=587                 # 587 for STARTTLS, 465 for implicit TLS
  SMTP_USERNAME=apikey
  SMTP_PASSWORD=...
  SMTP_FROM="standup-gen <no-reply@example.com>"
  SMTP_TLS=starttls             # starttls | ssl | none
  PUBLIC_URL=https://standup.example.com   # used to build the reset link
  ```

  A transactional provider (Mailgun, Postmark, SES) is the right choice for
  a real deployment; a personal Gmail app-password works for a tiny team.
  `PUBLIC_URL` defaults to the request's own origin, so a single-host
  deployment behind one hostname needs no extra config.

If your SMTP credentials leak, rotate `SMTP_PASSWORD` — it's independent of
the Fernet master key, so `provider_keys` are unaffected. See
[`docs/security-support.md`](security-support.md) for the broader
incident-response policy.

## Threat model

The full threat model is in [`docs/security.md`](security.md) — what we
defend against, what we explicitly don't, the rate-limit matrix, the cookie
format, the encryption-at-rest story, and the audit log. The short version:
argon2id passwords, `__Host-` cookies with `HttpOnly` + `SameSite=Lax`, CSRF
defence in depth, per-user rate limits on AI summaries, per-user account
lockout on login failures, Fernet-encrypted provider keys, and an admin-only
audit log. Designed to be safe to expose to the public internet behind TLS.

## Operational runbook

**Revoke a user's sessions.** Connect to Postgres and delete their session rows
— the next request with their cookie is rejected and they have to log in again:

```sql
DELETE FROM sessions WHERE user_id = 'the-user-uuid';
```

**Revoke all sessions globally** (suspected cookie theft, after a deploy, etc.):

```sql
DELETE FROM sessions;
```

Everyone logs in again. The lifespan scheduler will recreate the cleanup pass
on the next tick.

**Rotate the Fernet master key.** `scripts/rotate-secrets.sh` re-encrypts every
active `provider_keys` row in place under a new key, atomically. The running
API keeps using the old key until you restart it. Back up the new
`.secrets_key` and delete the old one from wherever you stored it.

```bash
scripts/rotate-secrets.sh                    # generates a new key for you
scripts/rotate-secrets.sh 'my-new-passphrase'  # or use a specific passphrase
```

**Read the audit log.** Admin-only, paginated, filterable by `action` (exact
match) and `since` (timestamp, inclusive):

```
GET /admin/audit?action=auth.login.fail&since=2026-06-20T00:00:00
```

`auth.login.fail`, `auth.login.lockout`, `admin.user.create`, `secrets.rotate`
— see `backend/audit.py` for the full list of action strings.

**Unlock a user** after a lockout (admin only):

```
POST /admin/users/{id}/unlock
```

**Reset a user's password** (admin only; there is no email delivery in 0.5.0):

```
POST /admin/users/{id}/reset-password
```

The response is a one-time token with a 15-minute expiry. Deliver it to the
user out of band; they redeem it at `/password-reset?token=...` in the browser
or `POST /auth/password-reset/confirm` from the CLI. Email-delivered reset is
0.6.0.

## What 0.5.0 is not

Deliberate omissions, all on the 0.6.0+ roadmap:

- **No OIDC / SSO.** The auth backend is designed so an OIDC provider can
  replace the password branch in a future slice.
- **No orgs, teams, or billing.** 0.5.0 is user-scoped.
- **No email-delivered invites.** Invites are admin-mediated
  (`POST /admin/invites`).
- **No email-delivered password reset.** Admin-mediated reset, above.
- **No PWA / mobile UI.** The web UI is desktop-first.

If any of those are showstoppers, stay on 0.4.0 and wait.
