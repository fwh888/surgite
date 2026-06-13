"""Tests for the per-IP rate limit on /summary?ai=true."""

import pytest
from fastapi import HTTPException

from backend import rate_limit


@pytest.fixture(autouse=True)
def _reset_buckets():
    """Each test starts with a clean bucket; the global module state is
    process-local, and the /summary ai tests would otherwise contaminate
    this module's view of the world."""
    rate_limit._reset_for_tests()
    yield
    rate_limit._reset_for_tests()


class _StubRequest:
    """Minimal stand-in for a starlette Request, exercising the same code
    path the real handler uses (headers + client.host)."""

    def __init__(self, ip="1.2.3.4", fwd=None):
        self.headers = {"x-forwarded-for": fwd} if fwd else {}
        self.client = type("C", (), {"host": ip})()


def test_allows_up_to_limit():
    for _ in range(rate_limit._LIMIT):
        rate_limit.check_rate_limit(_StubRequest())


def test_blocks_request_over_limit():
    for _ in range(rate_limit._LIMIT):
        rate_limit.check_rate_limit(_StubRequest())
    with pytest.raises(HTTPException) as exc:
        rate_limit.check_rate_limit(_StubRequest())
    assert exc.value.status_code == 429
    assert "Retry-After" in exc.value.headers


def test_separate_buckets_per_ip():
    for _ in range(rate_limit._LIMIT):
        rate_limit.check_rate_limit(_StubRequest(ip="1.1.1.1"))
    # Different IP must still get a fresh budget.
    rate_limit.check_rate_limit(_StubRequest(ip="2.2.2.2"))


def test_honors_x_forwarded_for():
    for _ in range(rate_limit._LIMIT):
        rate_limit.check_rate_limit(_StubRequest(fwd="9.9.9.9"))
    # Direct peer can keep going; only the proxied IP is throttled.
    rate_limit.check_rate_limit(_StubRequest(ip="127.0.0.1"))


def test_window_expiry_resets_bucket(monkeypatch):
    """After the window passes, the bucket is empty again. We push the
    synthetic clock forward past the window length so the oldest entry
    is no longer inside the window."""
    fake_now = [1000.0]
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: fake_now[0])
    for _ in range(rate_limit._LIMIT):
        rate_limit.check_rate_limit(_StubRequest())
    fake_now[0] += rate_limit._WINDOW + 0.1
    rate_limit.check_rate_limit(_StubRequest())


# --- wired into the /summary handler ---


def test_summary_without_ai_is_not_rate_limited(client):
    """Cheap read endpoints are unmetered — only ai=true costs money."""
    for _ in range(rate_limit._LIMIT + 5):
        assert client.get("/summary").status_code == 200


def test_summary_with_ai_returns_429_after_limit(client, monkeypatch):
    # 400 fires first when the key is missing — that's a fine 4xx, but the
    # rate-limit guard runs before it, so a 429 still proves the limit hit.
    for _ in range(rate_limit._LIMIT):
        r = client.get("/summary?ai=true&provider=groq")
        assert r.status_code == 400  # GROQ_API_KEY empty in conftest
    r = client.get("/summary?ai=true&provider=groq")
    assert r.status_code == 429
    assert r.headers.get("retry-after")
