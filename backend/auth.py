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
  multi_user  — full session-cookie auth; an absent/expired/invalid session is
                a 401.

Designed so OIDC can be added in 0.6.0 by replacing only the multi_user branch
of `get_current_user` with one that consults an OIDC verifier first, falling
back to the cookie.
"""

import ipaddress
import logging
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import config
from backend.db import InviteRow, SessionRow, UserRow, get_db, session_scope

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


# --- Users ------------------------------------------------------------------


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
    exists); in multi_user an absent/expired/invalid session is a 401."""
    mode = config.AUTH_MODE
    if mode in ("off", "single_user"):
        return ensure_bootstrap_user(session)

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
