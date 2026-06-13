"""Per-IP token-bucket rate limit for /summary?ai=true.

The summarizer is the only endpoint that can rack up real cost (network
fetch + N LLM round-trips per request), so it's the only thing this guard
protects. Cheap read endpoints are intentionally unmetered.

Implementation: hand-rolled in-memory bucket keyed on client IP. No external
dep — `slowapi` would pull in `limits` + a redis client we don't otherwise
need, and the project's lean-principles list prefers one fewer transitive.
Process-local is fine: a restart resets the bucket, which is exactly the
lenient behaviour we want for an accidental button-mash guard, not a
hardening boundary. For real abuse protection, sit this behind Traefik +
fail2ban as the project docs already recommend.
"""

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

# Default: 5 requests per 60 seconds per client IP.
_LIMIT = int(os.environ.get("RATE_LIMIT_REQUESTS", "5"))
_WINDOW = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))

# (client_ip) -> deque of request timestamps (epoch seconds).
_buckets: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    """Pick the most plausible client IP. Trusts the first X-Forwarded-For
    entry when present (the app is meant to sit behind Traefik), falling
    back to the direct peer — no proxy-aware enumeration, just what we need
    to bucket the same user behind the same key."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(request: Request) -> None:
    """Allow up to `_LIMIT` requests per `_WINDOW` seconds per client IP.
    Raises 429 (with a `Retry-After` header via HTTPException) when exceeded.
    The eviction sweep is O(1) amortised: each call prunes the bucket's
    expired entries, and a bucket is cleared entirely once it empties."""
    now = time.monotonic()
    cutoff = now - _WINDOW
    ip = _client_ip(request)
    with _lock:
        bucket = _buckets[ip]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= _LIMIT:
            retry_after = max(1, int(_WINDOW - (now - bucket[0])))
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: max {_LIMIT} / {_WINDOW}s per IP",
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)
        if not bucket:
            # Drop the empty deque so the dict doesn't grow unbounded for
            # one-shot visitors.
            del _buckets[ip]


def _reset_for_tests() -> None:
    """Clear all buckets. Tests use this to avoid cross-test pollution."""
    with _lock:
        _buckets.clear()
