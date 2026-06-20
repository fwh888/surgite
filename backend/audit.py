"""Audit log helpers (slice 2, plan #75).

A thin wrapper around an append-only ``audit_log`` table. Use ``audit(...)``
from request handlers to record security-relevant events (logins, repo
adds, key revokes, etc.). The structured logger also emits a
``namespace=audit`` record so log shippers see the same event in the
standard stream.

Failures here are intentionally non-fatal: an audit write that throws
must not break the user-facing request. We log the error and move on.
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from backend.db import AuditLogRow, session_scope

log = logging.getLogger("audit")


def _truncate(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    return value[:limit]


def audit(
    action: str,
    *,
    actor_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    metadata: dict[str, Any] | None = None,
    session: Session | None = None,
) -> None:
    """Append a row to the audit log. ``metadata`` is JSON-serialisable;
    other string fields are truncated to sane limits (matching the
    SessionRow/ip truncation policy)."""
    row = AuditLogRow(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=_truncate(target_id, 64),
        ip=_truncate(ip, 64),
        user_agent=_truncate(user_agent, 256),
        metadata_=metadata,
    )
    try:
        with session_scope(session) as s:
            s.add(row)
            s.commit()
    except Exception as exc:  # noqa: BLE001 — audit must never break the caller
        log.error("audit write failed: %s", exc, extra={"action": action})
    # Mirror to the standard log stream so log shippers see the same event.
    log.info(
        "audit %s actor=%s target=%s:%s",
        action,
        actor_id or "-",
        target_type or "-",
        target_id or "-",
    )
