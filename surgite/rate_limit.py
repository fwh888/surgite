"""Per-user and per-IP-outer token-bucket rate limits (plan #68).

Two limits live here:

  - ``check_user_rate_limit(user, request, *, requests, window, name)`` —
    a per-user token bucket. Used by the AI summary and login endpoints.
    Keyed on (user_id, name) so a single user can have separate budgets
    for "/summary" and "/auth/login".
  - ``check_ip_outer_rate_limit(request)`` — a separate, much larger
    per-IP bucket (100/60s default) for the "fresh signup, spam" case
    where a per-user limit doesn't catch a single attacker cycling
    accounts. Wired into the AI summary endpoints as a backstop.

Both are hand-rolled in-memory token buckets keyed on
``(client_ip)`` or ``(user_id, name)``. Process-local is fine: a restart
resets the bucket, which is the lenient behaviour we want for an
accidental button-mash guard, not a hardening boundary. For real abuse
protection, sit this behind Traefik + fail2ban as the project docs
already recommend.
"""

import ipaddress
import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from surgite.config import TRUSTED_PROXIES

# Per-user + per-IP-outer buckets. Defaults match the plan (plan #68):
#   summary:  5 / 60s per user, 100 / 60s per IP outer
# Login throttling is the lockout story (plan #69), not a separate rate
# limit; the per-IP outer guard is the only extra layer on /auth/login.
_SUMMARY_USER_REQUESTS = int(os.environ.get("SUMMARY_RATE_LIMIT_REQUESTS", "5"))
_SUMMARY_USER_WINDOW = int(os.environ.get("SUMMARY_RATE_LIMIT_WINDOW_SECONDS", "60"))
_SUMMARY_IP_REQUESTS = int(os.environ.get("IP_OUTER_RATE_LIMIT_REQUESTS", "100"))
_SUMMARY_IP_WINDOW = int(os.environ.get("IP_OUTER_RATE_LIMIT_WINDOW_SECONDS", "60"))

# (client_ip) -> deque of request timestamps (epoch seconds).
_ip_buckets: dict[str, deque[float]] = defaultdict(deque)
# ((user_id, name)) -> deque
_user_buckets: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    """Pick the most plausible client IP. Only trusts X-Forwarded-For when
    the direct peer is in TRUSTED_PROXIES (set via env var, default empty).
    When no trusted proxies are configured, the header is ignored and the
    direct peer address is used — this is the safe default for deployments
    that expose the app directly (the shipped docker-compose.yml publishes
    the app on the host with no reverse proxy in front)."""
    direct_peer = request.client.host if request.client else "unknown"
    fwd = request.headers.get("x-forwarded-for")
    if fwd and TRUSTED_PROXIES and _is_trusted(direct_peer):
        return fwd.split(",", 1)[0].strip()
    return direct_peer


def _is_trusted(ip: str) -> bool:
    """Check if an IP address is in the TRUSTED_PROXIES allowlist.
    Supports exact matches and CIDR notation (e.g. 10.0.0.0/8)."""
    for entry in TRUSTED_PROXIES:
        if "/" not in entry:
            if ip == entry:
                return True
            continue
        # A malformed peer address or allowlist entry is simply not a match.
        try:
            if ipaddress.ip_address(ip) in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


def _check_bucket(bucket: deque, limit: int, window: int, label: str) -> None:
    """Shared token-bucket implementation. Raises 429 with Retry-After when
    the bucket is over `limit` inside the last `window` seconds."""
    now = time.monotonic()
    cutoff = now - window
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= limit:
        retry_after = max(1, int(window - (now - bucket[0])))
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: max {limit} / {window}s per {label}",
            headers={"Retry-After": str(retry_after)},
        )
    bucket.append(now)


def _drop_empty_ip_bucket(ip: str) -> None:
    """Avoid unbounded growth of the IP-bucket dict for one-shot visitors.
    Caller holds ``_lock``."""
    bucket = _ip_buckets.get(ip)
    if bucket is not None and not bucket:
        del _ip_buckets[ip]


def check_user_rate_limit(
    request: Request, *, user_id: str, limit: int, window: int, name: str
) -> None:
    """Per-user token bucket. ``name`` distinguishes different buckets for
    the same user (e.g. ``"summary"`` vs ``"login"``)."""
    with _lock:
        _check_bucket(_user_buckets[(user_id, name)], limit, window, f"user:{name}")


def check_ip_outer_rate_limit(request: Request) -> None:
    """A larger per-IP bucket (100/60s default) as a backstop. Fires after
    the per-user limit on the AI summary endpoints."""
    ip = _client_ip(request)
    with _lock:
        _check_bucket(_ip_buckets[ip], _SUMMARY_IP_REQUESTS, _SUMMARY_IP_WINDOW, "IP")
        _drop_empty_ip_bucket(ip)


# Convenience preset that matches the documented default (plan #68).
def check_summary_user_limit(request: Request, *, user_id: str) -> None:
    check_user_rate_limit(
        request,
        user_id=user_id,
        limit=_SUMMARY_USER_REQUESTS,
        window=_SUMMARY_USER_WINDOW,
        name="summary",
    )


def _reset_for_tests() -> None:
    """Clear all buckets. Tests use this to avoid cross-test pollution."""
    with _lock:
        _ip_buckets.clear()
        _user_buckets.clear()
