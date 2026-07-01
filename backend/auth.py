"""Auth primitives for 0.5.0: password hashing, server-side sessions, and the
`get_current_user` FastAPI dependency.

The dependency is the single gate the rest of the API leans on — route handlers
take `current_user: UserRow = Depends(get_current_user)` and scope their queries
to `current_user.id` rather than sprinkling auth checks through every handler.

Three modes, selected by `AUTH_MODE` (read fresh from `backend.config` on every
call so tests can flip it):

  off         — anonymous; resolves to the bootstrap user. 0.4.0 behaviour.
  single_user — resolves to the bootstrap user; the machinery is exercised but
                no login flow is exposed.
  multi_user  — full session-cookie or Bearer API-key auth; an absent/expired/
                invalid session or key is a 401.

Designed so OIDC can be added in 0.6.0 by replacing only the multi_user branch
of `get_current_user` with one that consults an OIDC verifier first, falling
back to the cookie.
"""

import ipaddress
import logging
import re
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import config
from backend.db import (
    ApiKeyRow,
    InviteRow,
    OrgMemberRow,
    OrgRow,
    PasswordResetRow,
    SessionRow,
    UserRow,
    get_db,
    session_scope,
)

log = logging.getLogger(__name__)

# argon2id with the library defaults. The 0.5.0 plan calls for tuning the
# parameters to ~250 ms on the target server; that tuning is deferred to the
# security slice once there's a real box to measure against. The defaults are
# already a safe, modern argon2id configuration.
_ph = PasswordHasher()

# A 256-bit opaque session id, url-safe so it's a valid cookie value as-is.
_SESSION_ID_BYTES = 32


# --- Passwords --------------------------------------------------------------


def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """True iff `plain` matches `hashed`. Never raises on a bad password or a
    malformed hash — both are just a failed verification."""
    try:
        return _ph.verify(hashed, plain)
    except VerifyMismatchError, InvalidHashError:
        return False


def normalize_email(email: str) -> str:
    return email.strip().lower()


# --- API keys (Bearer) -------------------------------------------------------


# A full key is `sk_<prefix>_<secret>` where prefix is 8 chars and secret is
# 32 chars. The DB stores an argon2id hash of the *full* key plus the prefix
# for a fast lookup index (argon2 is intentionally slow — we don't want to
# hash every incoming Bearer just to identify the key).
_API_KEY_PREFIX_LEN = 8
_API_KEY_SECRET_LEN = 32
_API_KEY_PREFIX_BYTES = 4  # 4 bytes -> 6 chars urlsafe; pad to 8 with sk_
_API_KEY_SECRET_BYTES = 24  # 24 bytes -> 32 chars urlsafe


def _generate_api_key() -> tuple[str, str, str]:
    """Mint a new (full_key, prefix, secret) triple. The full key is what the
    caller stores; only the prefix and the argon2id hash of the full key hit
    the DB. The secret portion is the second half of the key, returned as
    part of `full_key` so the CLI can present it to the user once."""
    prefix = "sk_" + secrets.token_urlsafe(_API_KEY_PREFIX_BYTES)[:_API_KEY_PREFIX_LEN]
    secret = secrets.token_urlsafe(_API_KEY_SECRET_BYTES)[:_API_KEY_SECRET_LEN]
    full = f"{prefix}_{secret}"
    return full, prefix, secret


def issue_api_key(
    user_id: str,
    *,
    name: str,
    expires_at: datetime | None = None,
) -> tuple[str, str]:
    """Create a new API key for `user_id`. Returns ``(full_key, key_id)``.
    ``full_key`` is shown to the caller exactly once (they need to put it
    in their CI secret); only the argon2id hash is persisted."""
    full, prefix, _secret = _generate_api_key()
    kid = secrets.token_urlsafe(8)
    now = datetime.now(UTC)
    with session_scope() as s:
        row = ApiKeyRow(
            id=kid,
            user_id=user_id,
            org_id=personal_org_id(s, user_id),
            name=name,
            prefix=prefix,
            key_hash=hash_password(full),
            expires_at=expires_at,
            created_at=now,
        )
        s.add(row)
        s.commit()
    return full, kid


def verify_api_key(full_key: str, *, session: Session) -> UserRow | None:
    """Resolve a Bearer key to its user. Returns None on any failure (no
    key, unknown prefix, bad hash, expired, revoked). Updates
    ``last_used_at`` on success."""
    if not full_key or not full_key.startswith("sk_"):
        return None
    parts = full_key.split("_", 2)
    if len(parts) != 3:
        return None
    prefix = parts[0] + "_" + parts[1]
    row = session.scalar(select(ApiKeyRow).where(ApiKeyRow.prefix == prefix))
    if row is None or row.revoked_at is not None:
        return None
    if row.expires_at is not None and _as_utc(row.expires_at) <= datetime.now(UTC):
        return None
    if not verify_password(full_key, row.key_hash):
        return None
    row.last_used_at = datetime.now(UTC)
    session.commit()
    user = session.get(UserRow, row.user_id)
    return user if user is not None and user.is_active else None


def revoke_api_key(key_id: str, *, user_id: str | None = None) -> bool:
    """Revoke a key by id. If ``user_id`` is given, only revoke keys owned
    by that user (the per-user DELETE path). Returns True iff a row was
    updated."""
    with session_scope() as s:
        q = select(ApiKeyRow).where(ApiKeyRow.id == key_id)
        if user_id is not None:
            q = q.where(ApiKeyRow.user_id == user_id)
        row = s.scalar(q)
        if row is None or row.revoked_at is not None:
            return False
        row.revoked_at = datetime.now(UTC)
        s.commit()
        return True


# --- Login lockout (plan #69) -----------------------------------------------


def is_locked(user: UserRow) -> bool:
    """True iff `user.locked_until` is set and in the future. The check is
    pure read; the caller is responsible for deciding how to surface it
    (the auth_login handler turns it into a 423 with a Retry-After)."""
    if user.locked_until is None:
        return False
    return _as_utc(user.locked_until) > datetime.now(UTC)


def record_login_failure(user: UserRow, *, session: Session) -> None:
    """Bump the per-user failure counter. Trips a lockout window if the
    count crosses ``LOGIN_LOCKOUT_THRESHOLD`` within
    ``LOGIN_LOCKOUT_WINDOW_MINUTES`` of the first failure. The window is
    observed by clearing the counter when the gap to the *last* failure
    exceeds the window — the implementation here is "increment and
    re-evaluate", which over-locks slightly in the corner case of a
    slow-but-steady attacker. The over-lock is bounded by the window
    length and is preferable to under-locking."""
    user.failed_login_count += 1
    if user.failed_login_count >= config.LOGIN_LOCKOUT_THRESHOLD:
        user.locked_until = datetime.now(UTC) + timedelta(
            minutes=config.LOGIN_LOCKOUT_DURATION_MINUTES
        )
        user.failed_login_count = 0  # reset so a fresh attempt after unlock starts at 0
    session.commit()


def record_login_success(user: UserRow, *, session: Session) -> None:
    """Reset the failure counter and clear the lockout on a successful
    login. Belt-and-braces: the lockout check rejects locked users
    regardless, but resetting the count on success means a user who
    eventually types their password right isn't still sitting on 9
    failed attempts."""
    user.failed_login_count = 0
    user.locked_until = None
    session.commit()


def unlock_user(user: UserRow, *, session: Session) -> None:
    """Admin action: clear the lockout and the failure counter."""
    user.failed_login_count = 0
    user.locked_until = None
    session.commit()


# --- Users ------------------------------------------------------------------


def slugify_org(local_part: str) -> str:
    """Turn an email local-part into a URL-safe org slug base (lowercase,
    [a-z0-9-], 3–32 chars). Pure, no DB — the 1.0.0 org backfill migration
    re-implements the same rule inline (kept trivial so it can't drift far)."""
    s = re.sub(r"[^a-z0-9]+", "-", local_part.lower()).strip("-")[:32].strip("-")
    if len(s) < 3:
        s = f"{s}-org" if s else "org"
    return s


def create_personal_org(session: Session, user: UserRow) -> OrgRow:
    """Create the user's personal org + owner membership and point
    ``user.personal_org_id`` at it. Idempotent: returns the existing personal
    org if one is already set. Called from both user-creation paths so the
    slug/role invariants match the migration backfill (1.0.0 slice 1)."""
    if user.personal_org_id is not None:
        existing = session.get(OrgRow, user.personal_org_id)
        if existing is not None:
            return existing
    base = slugify_org(normalize_email(user.email).split("@")[0])
    slug, n = base, 1
    while session.scalar(select(OrgRow.slug).where(OrgRow.slug == slug)) is not None:
        n += 1
        slug = f"{base}-{n}"
    org = OrgRow(name=user.display_name or base, slug=slug)
    session.add(org)
    session.flush()  # assign org.id before the membership/back-reference
    session.add(OrgMemberRow(org_id=org.id, user_id=user.id, role="owner"))
    user.personal_org_id = org.id
    session.commit()
    session.refresh(user)
    return org


def personal_org_id(session: Session, user_id: str) -> str | None:
    """The user's personal org id, for insert sites that only carry a user_id
    (the plain functions below have no Request to resolve a full scope from).
    None only for pre-migration data with no personal org."""
    return session.scalar(select(UserRow.personal_org_id).where(UserRow.id == user_id))


def ensure_bootstrap_user(session: Session) -> UserRow:
    """Return the BOOTSTRAP_OWNER_EMAIL user, creating it (as an admin with no
    password) if it doesn't exist. This is the account that owns all data in
    off/single_user mode and the backfill target for the 0.4.0 migration."""
    email = normalize_email(config.BOOTSTRAP_OWNER_EMAIL)
    user = session.scalar(select(UserRow).where(UserRow.email == email))
    if user is None:
        user = UserRow(email=email, display_name="owner", is_admin=True, is_active=True)
        session.add(user)
        session.commit()
        session.refresh(user)
    create_personal_org(session, user)  # idempotent; ensures a personal org exists
    return user


def create_user(
    session: Session,
    *,
    email: str,
    password: str | None,
    display_name: str = "",
    is_admin: bool = False,
) -> UserRow:
    user = UserRow(
        email=normalize_email(email),
        password_hash=hash_password(password) if password else None,
        display_name=display_name or normalize_email(email).split("@")[0],
        is_admin=is_admin,
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    create_personal_org(session, user)  # every account gets a personal org (1.0.0)
    return user


def create_invite(
    session: Session,
    *,
    email: str | None = None,
    role: str = "user",
    created_by: str | None = None,
    ttl_days: int = 14,
) -> InviteRow:
    invite = InviteRow(
        token=secrets.token_urlsafe(_SESSION_ID_BYTES),
        email=normalize_email(email) if email else None,
        role=role,
        created_by=created_by,
        # Issuing org: the creator's personal org (org-issued invites arrive in
        # slice 2). None for the bootstrap invite, which has no creator yet.
        org_id=personal_org_id(session, created_by) if created_by else None,
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=ttl_days),
    )
    session.add(invite)
    session.commit()
    session.refresh(invite)
    return invite


def ensure_bootstrap_invite(session: Session) -> str | None:
    """In multi_user mode with no active admin yet, mint a single admin invite
    for BOOTSTRAP_OWNER_EMAIL so the operator has a way in on first run. Returns
    the redeem token (new or the still-unused existing one), or None if an
    active admin already exists. Idempotent across restarts."""
    if config.AUTH_MODE != "multi_user":
        return None
    admin = session.scalar(
        select(UserRow).where(UserRow.is_admin.is_(True), UserRow.is_active.is_(True))
    )
    if admin is not None:
        return None
    email = normalize_email(config.BOOTSTRAP_OWNER_EMAIL)
    now = datetime.now(UTC)
    existing = session.scalar(
        select(InviteRow).where(InviteRow.email == email, InviteRow.used_at.is_(None))
    )
    if existing is not None and _as_utc(existing.expires_at) > now:
        return existing.token
    return create_invite(session, email=email, role="admin").token


# --- Sessions ---------------------------------------------------------------


def _as_utc(dt: datetime) -> datetime:
    """Treat a tz-naive datetime as UTC. Postgres returns aware datetimes for
    our timezone=True columns; SQLite (the test DB) hands back naive ones."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _truncate_ip(ip: str | None) -> str | None:
    """Reduce an address to its /24 (v4) or /64 (v6) network so we keep a
    coarse origin for audit without storing a full client address."""
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    prefix = 24 if addr.version == 4 else 64
    return str(ipaddress.ip_network(f"{ip}/{prefix}", strict=False))


def create_session(
    user_id: str,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
    session: Session | None = None,
) -> SessionRow:
    now = datetime.now(UTC)
    row = SessionRow(
        id=secrets.token_urlsafe(_SESSION_ID_BYTES),
        user_id=user_id,
        created_at=now,
        expires_at=now + timedelta(days=config.SESSION_TTL_DAYS),
        last_seen_at=now,
        ip=_truncate_ip(ip),
        user_agent=(user_agent or "")[:256] or None,
    )
    with session_scope(session) as s:
        row.org_id = personal_org_id(s, user_id)
        s.add(row)
        s.commit()
        s.refresh(row)
        s.expunge(row)
    return row


def revoke_session(session_id: str, *, session: Session | None = None) -> None:
    with session_scope(session) as s:
        row = s.get(SessionRow, session_id)
        if row is not None:
            s.delete(row)
            s.commit()


def purge_expired_sessions() -> int:
    """Delete sessions past their expiry. Called by the lifespan scheduler.
    The read path (get_current_user) rejects expired sessions independently,
    so this is housekeeping to keep the table small. Returns rows deleted."""
    now = datetime.now(UTC)
    with session_scope() as s:
        rows = s.scalars(select(SessionRow).where(SessionRow.expires_at <= now)).all()
        for row in rows:
            s.delete(row)
        s.commit()
        return len(rows)


def revoke_all_sessions(user_id: str, *, keep: str | None = None) -> int:
    """Revoke every session for ``user_id``. Optionally keep the session
    with id ``keep`` (used by PUT /auth/password so the user isn't logged
    out mid-change). Returns the number of rows deleted."""
    with session_scope() as s:
        q = select(SessionRow).where(SessionRow.user_id == user_id)
        if keep is not None:
            q = q.where(SessionRow.id != keep)
        rows = s.scalars(q).all()
        for row in rows:
            s.delete(row)
        s.commit()
        return len(rows)


# --- Password change (issue #77) --------------------------------------------


def change_password(user_id: str, *, new_password: str) -> None:
    """Hash ``new_password`` and store it on user ``user_id``. The
    caller is responsible for revoking the user's other sessions
    (see ``revoke_all_sessions``) — keeping that step at the call
    site documents *which* sessions are kept (the calling one)
    right next to the policy decision. We re-fetch the user inside
    our own scope so the caller's request session is untouched."""
    with session_scope() as s:
        user = s.get(UserRow, user_id)
        if user is None:
            return
        user.password_hash = hash_password(new_password)
        s.commit()


# --- Password reset tokens (issue #77) --------------------------------------
# 15-minute expiry; one-time use. The full token is ``pr_<id>_<secret>``;
# we keep only the argon2id hash and the 8-char ``id`` for the lookup
# index, same as the api_keys design.

_PASSWORD_RESET_TTL_MINUTES = 15
_PASSWORD_RESET_ID_BYTES = 4  # token_hex(4) -> 8 hex chars, separator-free
_PASSWORD_RESET_ID_LEN = _PASSWORD_RESET_ID_BYTES * 2
_PASSWORD_RESET_SECRET_BYTES = 32


def _generate_reset_token() -> tuple[str, str]:
    """Mint a new (full_token, id) pair. The full token is what gets emailed
    to the user once; the id is the lookup index.

    The id is hex (``token_hex``), not ``token_urlsafe``: the token format is
    ``pr_<id>_<secret>`` and the id must not contain the ``_``/``-`` that
    ``token_urlsafe`` can emit, or redemption can't reliably split the id
    back out. The secret keeps full url-safe entropy."""
    rid = secrets.token_hex(_PASSWORD_RESET_ID_BYTES)
    secret = secrets.token_urlsafe(_PASSWORD_RESET_SECRET_BYTES)
    return f"pr_{rid}_{secret}", rid


def mint_password_reset(user_id: str) -> tuple[str, datetime]:
    """Create a new reset token for ``user_id``. Returns the (full_token,
    expires_at) pair; the admin delivers the token to the user. The
    full token is argon2id-hashed before persistence; only the id
    prefix and the hash hit the DB."""
    full, rid = _generate_reset_token()
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=_PASSWORD_RESET_TTL_MINUTES)
    with session_scope() as s:
        s.add(
            PasswordResetRow(
                id=rid,
                user_id=user_id,
                org_id=personal_org_id(s, user_id),
                token_hash=hash_password(full),
                expires_at=expires_at,
                created_at=now,
            )
        )
        s.commit()
    return full, expires_at


def redeem_password_reset(token: str, *, new_password: str) -> str | None:
    """Validate ``token``, set ``new_password`` on the user, revoke all
    of the user's sessions, and clear the lockout. Returns the user id
    on success, None if the token is unknown / expired / used / the
    user is inactive.

    The token format is ``pr_<id>_<secret>`` where ``<id>`` is exactly
    ``_PASSWORD_RESET_ID_LEN`` chars. We slice the id out by position
    rather than splitting on ``_``: ``token_urlsafe`` can emit ``_`` and
    ``-``, so a split would mis-parse the (~few %) of ids that contain an
    underscore. The full token is still verified against the argon2id hash,
    so a wrong slice fails safe."""
    if not token or not token.startswith("pr_"):
        return None
    rid = token[3 : 3 + _PASSWORD_RESET_ID_LEN]
    if len(rid) != _PASSWORD_RESET_ID_LEN:
        return None
    now = datetime.now(UTC)
    with session_scope() as s:
        row = s.get(PasswordResetRow, rid)
        if row is None or row.used_at is not None or _as_utc(row.expires_at) <= now:
            return None
        if not verify_password(token, row.token_hash):
            return None
        user = s.get(UserRow, row.user_id)
        if user is None or not user.is_active:
            return None
        user.password_hash = hash_password(new_password)
        # Defence in depth: a successful reset clears the lockout so the
        # user isn't sitting on a counter that locks them out moments
        # after they get back in.
        user.failed_login_count = 0
        user.locked_until = None
        row.used_at = now
        s.commit()
        user_id = user.id
    # Revoke the user's sessions out-of-band so a concurrent login
    # can't sneak in between the password change and the next read.
    revoke_all_sessions(user_id)
    return user_id


# --- Cookies ----------------------------------------------------------------


def set_session_cookie(response: Response, session_id: str) -> None:
    """Set the hardened session cookie. `__Host-` prefix + Secure in
    production (see config.SESSION_COOKIE_NAME); plain + insecure only in
    DEBUG so local plain-HTTP dev works."""
    response.set_cookie(
        key=config.SESSION_COOKIE_NAME,
        value=session_id,
        max_age=config.SESSION_TTL_DAYS * 86400,
        httponly=True,
        secure=not config.DEBUG,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(config.SESSION_COOKIE_NAME, path="/")


# --- The dependency ---------------------------------------------------------


def get_current_user(
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
) -> UserRow:
    """Resolve the request to a user per AUTH_MODE. In off/single_user the
    bootstrap user is always returned (so handlers can assume a current user
    exists); in multi_user an absent/expired/invalid session OR API key is
    a 401.

    Auth precedence in multi_user mode:
      1. ``Authorization: Bearer sk_...`` (API key) — used by the CLI
         (`STANDUP_API_KEY`) and any out-of-band caller.
      2. The session cookie (``__Host-standup_session``) — used by the SPA.

    The API key path is checked first because a CLI request that
    mistakenly also sends a stale cookie still authenticates; the cookie
    path is the SPA's only path. A 401 from the API key path does NOT
    fall through to the cookie path (and vice versa) — both are
    independent auth attempts and either one resolving is enough."""
    mode = config.AUTH_MODE
    if mode in ("off", "single_user"):
        return ensure_bootstrap_user(session)

    # Bearer API key (CLI). Stays strictly orthogonal to the cookie path so a
    # caller with a valid key never has to worry about stray cookies.
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        user = verify_api_key(token, session=session)
        if user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return user

    sid = request.cookies.get(config.SESSION_COOKIE_NAME)
    if not sid:
        raise HTTPException(status_code=401, detail="Not authenticated")

    now = datetime.now(UTC)
    sess = session.get(SessionRow, sid)
    if sess is None or _as_utc(sess.expires_at) <= now:
        raise HTTPException(status_code=401, detail="Session expired")

    user = session.get(UserRow, sess.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Sliding sessions: refresh the expiry (and re-issue the cookie) when the
    # session is within SESSION_REFRESH_THRESHOLD_DAYS of expiring.
    sess.last_seen_at = now
    if _as_utc(sess.expires_at) - now < timedelta(days=config.SESSION_REFRESH_THRESHOLD_DAYS):
        sess.expires_at = now + timedelta(days=config.SESSION_TTL_DAYS)
        set_session_cookie(response, sess.id)
    session.commit()
    return user


def get_optional_user(
    request: Request,
    session: Session = Depends(get_db),
) -> UserRow | None:
    """Like get_current_user but never raises — returns None for an anonymous
    multi_user request instead of a 401. Used by the unauthenticated health
    endpoints so they can scope a probe to the caller's own repos when a
    session happens to be present, without ever requiring one."""
    if config.AUTH_MODE in ("off", "single_user"):
        return ensure_bootstrap_user(session)
    sid = request.cookies.get(config.SESSION_COOKIE_NAME)
    if not sid:
        return None
    sess = session.get(SessionRow, sid)
    if sess is None or _as_utc(sess.expires_at) <= datetime.now(UTC):
        return None
    user = session.get(UserRow, sess.user_id)
    return user if user is not None and user.is_active else None
