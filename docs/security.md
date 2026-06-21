# Security model — 0.5.0

This document describes the threat model for 0.5.0 and the design
choices that follow from it. The 0.5.0 release makes standup-gen
**safe to expose to the public internet** behind a TLS terminator
(Traefik + step-ca, Caddy + Let's Encrypt, or anything else that
hands the app a verified connection).

The 0.4.0 model was "single-tenant, no auth, trusted network". 0.5.0
keeps that mode as `AUTH_MODE=off` and `AUTH_MODE=single_user` and
adds `AUTH_MODE=multi_user` as the production default for any
deployment that isn't an internal-only homelab tool.

## Threat model

What we're defending against:

- **Credential stuffing.** An attacker with a list of emails tries to
  log in. Mitigated by per-user account lockout (10 fails → 15 min
  lockout, see `LOGIN_LOCKOUT_*` env vars) and per-IP outer rate
  limiting.
- **Session hijacking.** An attacker captures a session cookie.
  Mitigated by `__Host-` cookie prefix + `Secure` + `HttpOnly` +
  `SameSite=Lax` (the browser won't send it on cross-site POSTs).
  Defence in depth: CSRF header check on every state-changing
  request.
- **Cross-tenant data leak.** One authenticated user reads another
  user's repos / commits / provider keys / shares. Mitigated by
  owner-scoped queries on every table (`owner_id = current_user.id`
  is the only access pattern) and the explicit per-route checks
  documented in `docs/releases/0.5.0-plan.md` (the historical
  plan; the current roadmap is `docs/0.6.0-plan.md`).
- **API key theft.** The CLI's `STANDUP_API_KEY` is stolen. Mitigated
  by `name` on every key (revoke "laptop", keep "CI"), `last_used_at`
  for forensic review, and the fact that keys are argon2id-hashed
  at rest (a DB leak doesn't yield usable keys).
- **At-rest DB theft.** An attacker reads the Postgres data
  directory. Mitigated by Fernet encryption on `provider_keys`; the
  master key is in `SECRETS_ENCRYPTION_KEY` (or `.secrets_key` for
  first-run convenience) and is never in the DB. Other tables
  (commits, repos, sessions) are plaintext — the threat model treats
  Postgres as a trust boundary, like any web app.
- **CSRF.** A malicious site triggers a state-changing request
  against the API. Mitigated by the `SameSite=Lax` cookie (the
  browser won't send the cookie on cross-site POSTs) plus the
  `X-Requested-With: standup-web` header requirement on every
  non-safe request in multi_user mode. The CLI uses Bearer auth and
  is unaffected.
- **Information disclosure via `/health/deep`.** The probe in 0.4.0
  picked an arbitrary repo and could leak repo names to anonymous
  callers. Mitigated by scoping the probe to the caller's own repos
  (or skipping it entirely for anonymous multi_user callers) and
  returning a redacted `{ "components": { ... } }` shape.
- **Information disclosure via `/providers`.** The 0.4.0 endpoint
  returned whether each provider has a key configured — a useful
  reconnaissance surface. Mitigated by making the endpoint
  admin-only in multi_user mode and showing the *calling admin's*
  per-user status (their own `provider_keys` rows + env-var
  fallback), not the global picture.

What we're NOT defending against:

- **A compromised TLS terminator.** The app trusts whatever
  `X-Forwarded-For` header Traefik/Caddy sends; if your reverse
  proxy is compromised, IP-based rate limits and lockout are
  bypassable. This is standard for any reverse-proxied app.
- **A compromised local user.** A user with shell on the host can
  read `.secrets_key` (chmod 600, owned by the API process) and
  derive the master. Run the app as a dedicated user.
- **A compromised Postgres backup.** Backups contain the
  `provider_keys` ciphertext + the audit log + the (now
  de-revoked) `api_keys` argon2id hashes. Treat backup files
  with the same care as `.secrets_key`.

## Auth mode matrix

| Mode | Login flow | Session cookie | Bearer keys | `/login` route | Use when |
|------|------------|----------------|-------------|----------------|----------|
| `off` | none | ignored | ignored | 404 | 0.4.0 behaviour, single-user trusted network |
| `single_user` | none (resolves to bootstrap user) | ignored | ignored | 404 | "I just want auth on the API" / tests |
| `multi_user` | email + password | `__Host-standup_session` | `Authorization: Bearer sk_...` | 200 | exposed deployment |

## Rate limits (multi_user mode)

| Endpoint | Limit | Scope | Env var |
|----------|-------|-------|---------|
| `/summary?ai=true`, `/summary/stream` | 5 / 60s | per user | `SUMMARY_RATE_LIMIT_REQUESTS`, `SUMMARY_RATE_LIMIT_WINDOW_SECONDS` |
| `/summary?ai=true`, `/summary/stream` | 100 / 60s | per IP (outer backstop) | `IP_OUTER_RATE_LIMIT_REQUESTS`, `IP_OUTER_RATE_LIMIT_WINDOW_SECONDS` |
| `/auth/login` (failures) | 10 in 15 min → 15 min lockout | per user | `LOGIN_LOCKOUT_THRESHOLD`, `LOGIN_LOCKOUT_WINDOW_MINUTES`, `LOGIN_LOCKOUT_DURATION_MINUTES` |
| `/auth/api-keys` (issue) | 10 / 24h | per user | `API_KEY_ISSUE_LIMIT`, `API_KEY_ISSUE_WINDOW_HOURS` |

All limits are hand-rolled in-memory token buckets (see
`backend/rate_limit.py`). Process-local is fine: a restart resets
the bucket, which is the lenient behaviour we want for an
accidental button-mash guard. For real abuse protection, sit this
behind Traefik + fail2ban as the project docs already recommend.

## Cookies

- Name: `__Host-standup_session` in production, `standup_session`
  in `DEBUG=true`.
- `__Host-` prefix forces `Secure` + host-only + `path=/` at the
  browser. `Secure` requires HTTPS, so plain-HTTP local dev uses
  `DEBUG=true` to drop the prefix.
- `HttpOnly`: JavaScript can't read it.
- `SameSite=Lax`: the browser won't send it on cross-site POSTs.
  This is the primary CSRF defence; the `X-Requested-With` header
  check is defence in depth.
- Lifetime: `SESSION_TTL_DAYS` (default 14). Sliding refresh
  when within `SESSION_REFRESH_THRESHOLD_DAYS` of expiry (default 7).
- Expiry sweep: the lifespan scheduler runs `purge_expired_sessions`
  alongside the existing ingest loop.

## Passwords

argon2id with library defaults (the parameters are tuned by the
`argon2-cffi` maintainers, not by us; they're already a safe modern
configuration). The 0.5.0 plan called for tuning to ~250 ms on the
target server; that tuning is a follow-up once there's a real box
to measure against.

## API keys

Format: `sk_<8-char-prefix>_<32-char-secret>`. Stored as an
argon2id hash of the full key, plus the prefix as a unique index
for fast lookup. The full key is shown to the user exactly once on
creation; we never return it again.

Revocation: `DELETE /auth/api-keys/{id}`. Revoked rows stay in the
table (with `revoked_at` set) for audit; the lookup rejects them
on `revoked_at IS NOT NULL`.

## Encryption at rest

`provider_keys.encrypted_key` is a Fernet token. The master key
comes from `SECRETS_ENCRYPTION_KEY` (env var) or `.secrets_key`
(generated on first run, chmod 600, see `backend/secrets.py`). The
operator is warned on first run to back the file up. Rotation:
`scripts/rotate-secrets.sh`.

`SECRETS_ENCRYPTION_KEY` accepts either:
- a 44-char urlsafe-b64 Fernet key (the standard form), or
- an arbitrary passphrase (we SHA-256 it to derive a 32-byte key).

The same string set via the env var produces the same Fernet key
on every restart, so dev workflows with a passphrase work fine.

## Audit log

`audit_log` table (slice 2 plan #75). `actor_id` is nullable so
pre-auth events (login failures, invite redemptions) can be
recorded. Read access: `GET /admin/audit` (admin-only, paginated,
filterable by `since` and `action`).

The structured logger mirrors every audit row to the standard log
stream (namespace `audit`), so log shippers see the same events
without a separate database query. The `audit()` helper in
`backend/audit.py` is the only write path; it never raises (an
audit write failure is logged at `ERROR` but does not break the
user-facing request).

## Operational checklist

- **First run on a fresh deployment**: set
  `BOOTSTRAP_OWNER_EMAIL=you@example.com`, start the API, copy
  the bootstrap admin invite out of the logs, redeem via
  `standup --redeem-invite <token>`. Then add the second admin
  with `POST /admin/invites` (role=admin) and revoke any
  long-lived keys you don't need.
- **TLS**: app refuses to start in `multi_user` mode without a
  session cookie over `Secure` — i.e. you need HTTPS. The
  Traefik + step-ca story is the homelab default; Caddy + Let's
  Encrypt for external deployments; `caddy trust` (or `mkcert`)
  for local dev.
- **Backup**: `scripts/backup.sh` (added in 0.4.0) now also
  backs up `provider_keys` and `audit_log`. `.secrets_key` is
  NOT backed up by the script — keep it in a separate, encrypted
  backup (it IS the encryption key for the at-rest data).
- **Key rotation**: `scripts/rotate-secrets.sh` (slice 2 plan
  #74). The script is idempotent on a single run; you need a
  restart to load the new master into the running process.
- **Lockout recovery**: an admin can unlock a user via
  `POST /admin/users/{id}/unlock`.
- **Password reset**: admin uses `POST /admin/users/{id}/reset-password`
  to mint a one-time token, delivers the token out of band, the user
  redeems it at `POST /auth/password-reset/confirm`. 15-minute expiry.
  Email-delivered reset is a 0.6.0 follow-up.
- **Reading the audit log**: `GET /admin/audit?action=auth.login.fail`
  shows every failed login. `?since=2026-06-20T00:00:00` filters
  by time.

## Known limitations

These are 0.6.0+ work, deliberately deferred:

- **OIDC / SSO** (slice 3 of the plan). The auth backend is
  designed so OIDC can replace just the multi_user branch of
  `get_current_user`.
- **Org / team model**. 0.5.0 is user-scoped, not org-scoped.
- **Email-delivered password reset**. Admin-mediated reset
  (`POST /admin/users/{id}/reset-password` + `POST /auth/password-reset/confirm`)
  ships in 0.5.0 slice 3 (issue #77); the email-delivery story is the
  remaining 0.6.0 piece.
- **Rate limit on `/auth/login` (per-user)**. The plan calls for
  a separate per-user login rate limit on top of the lockout;
  slice 2 ships lockout only (the lockout covers the credential
  stuffing case and the per-IP outer covers the fresh-signup
  case). A per-user login rate limit can be added by reusing
  `check_user_rate_limit(request, user_id=user.id, name="login")`
  if it turns out to be needed.
