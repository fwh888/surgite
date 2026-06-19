"""Auth foundation tests (0.5.0 slice 1).

Covers the password/session primitives directly and the AUTH_MODE behaviour
through the API: off/single_user stay anonymous-equivalent, multi_user gates
on a session cookie and isolates data per owner.

The session cookie is `__Host-`-prefixed and Secure in the test config (DEBUG
is unset), so the TestClient's cookie jar won't store or replay it over plain
HTTP. Authenticated requests therefore send the cookie via an explicit Cookie
header, and the login/redeem responses are checked through their Set-Cookie
header rather than the jar.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from backend import config
from backend.auth import (
    create_invite,
    create_session,
    create_user,
    hash_password,
    purge_expired_sessions,
    revoke_session,
    verify_password,
)
from backend.db import SessionRow, UserRow, get_session

COOKIE = config.SESSION_COOKIE_NAME


@pytest.fixture
def multi_user(monkeypatch):
    monkeypatch.setattr(config, "AUTH_MODE", "multi_user")


def _cookie_header(sid: str) -> dict:
    return {"Cookie": f"{COOKIE}={sid}"}


def _make_user(email="a@example.com", password="pw-correct-horse", is_admin=False):
    with get_session() as s:
        return create_user(s, email=email, password=password, is_admin=is_admin).id


def _make_session(user_id: str) -> str:
    return create_session(user_id, session=None).id


# --- password hashing -------------------------------------------------------


def test_password_roundtrip():
    h = hash_password("s3cret-passphrase")
    assert h != "s3cret-passphrase"  # not plaintext
    assert verify_password("s3cret-passphrase", h)


def test_password_wrong_is_false():
    h = hash_password("right")
    assert not verify_password("wrong", h)


def test_verify_malformed_hash_is_false_not_raise():
    assert verify_password("anything", "not-a-real-argon2-hash") is False


# --- sessions ---------------------------------------------------------------


def test_create_and_revoke_session():
    uid = _make_user()
    sid = _make_session(uid)
    with get_session() as s:
        assert s.get(SessionRow, sid) is not None
    revoke_session(sid)
    with get_session() as s:
        assert s.get(SessionRow, sid) is None


def test_purge_expired_sessions():
    uid = _make_user()
    live = _make_session(uid)
    with get_session() as s:
        expired = SessionRow(
            id="expired-sid",
            user_id=uid,
            created_at=datetime.now(UTC) - timedelta(days=30),
            expires_at=datetime.now(UTC) - timedelta(days=1),
            last_seen_at=datetime.now(UTC) - timedelta(days=2),
        )
        s.add(expired)
        s.commit()
    assert purge_expired_sessions() == 1
    with get_session() as s:
        assert s.get(SessionRow, live) is not None
        assert s.get(SessionRow, "expired-sid") is None


def test_session_ip_is_truncated():
    uid = _make_user()
    sess = create_session(uid, ip="192.168.0.55", user_agent="x" * 500)
    assert sess.ip == "192.168.0.0/24"
    assert len(sess.user_agent or "") <= 256


# --- AUTH_MODE=off (default) keeps 0.4.0 behaviour --------------------------


def test_off_mode_no_auth_required(client, add_commit):
    add_commit()
    assert client.get("/repos").status_code == 200
    assert client.get("/commits").status_code == 200
    # /providers is open in off mode
    assert client.get("/providers").status_code == 200


def test_off_mode_auth_routes_404(client):
    assert client.post("/auth/login", json={"email": "a@b.c", "password": "x"}).status_code == 404
    assert client.post("/auth/logout").status_code == 404


# --- AUTH_MODE=multi_user ---------------------------------------------------


def test_multi_user_requires_session(client, multi_user):
    assert client.get("/repos").status_code == 401
    assert client.get("/commits").status_code == 401
    assert client.get("/summary").status_code == 401


def test_multi_user_login_and_authenticated_request(client, multi_user):
    _make_user(email="nick@example.com", password="correct-horse-battery")
    r = client.post(
        "/auth/login", json={"email": "nick@example.com", "password": "correct-horse-battery"}
    )
    assert r.status_code == 200
    assert r.json()["email"] == "nick@example.com"
    set_cookie = r.headers.get("set-cookie", "")
    assert COOKIE in set_cookie
    assert "HttpOnly" in set_cookie
    assert "samesite=lax" in set_cookie.lower()
    assert "Secure" in set_cookie  # DEBUG unset -> production cookie
    assert "Path=/" in set_cookie

    # Extract the session id and use it on a protected route.
    sid = set_cookie.split(f"{COOKIE}=", 1)[1].split(";", 1)[0]
    assert client.get("/repos", headers=_cookie_header(sid)).status_code == 200


def test_multi_user_login_bad_password_401(client, multi_user):
    _make_user(email="nick@example.com", password="the-right-one")
    r = client.post("/auth/login", json={"email": "nick@example.com", "password": "wrong"})
    assert r.status_code == 401


def test_multi_user_login_unknown_user_401(client, multi_user):
    r = client.post("/auth/login", json={"email": "ghost@example.com", "password": "x"})
    assert r.status_code == 401


def test_expired_session_rejected(client, multi_user):
    uid = _make_user()
    with get_session() as s:
        s.add(
            SessionRow(
                id="stale-sid",
                user_id=uid,
                created_at=datetime.now(UTC) - timedelta(days=30),
                expires_at=datetime.now(UTC) - timedelta(days=1),
                last_seen_at=datetime.now(UTC) - timedelta(days=2),
            )
        )
        s.commit()
    assert client.get("/repos", headers=_cookie_header("stale-sid")).status_code == 401


def test_logout_revokes_session(client, multi_user):
    uid = _make_user()
    sid = _make_session(uid)
    assert client.get("/repos", headers=_cookie_header(sid)).status_code == 200
    assert client.post("/auth/logout", headers=_cookie_header(sid)).status_code == 200
    assert client.get("/repos", headers=_cookie_header(sid)).status_code == 401


# --- invite redemption ------------------------------------------------------


def test_redeem_pinned_invite_creates_user_and_logs_in(client, multi_user):
    admin = _make_user(email="admin@example.com", is_admin=True)
    with get_session() as s:
        token = create_invite(s, email="newbie@example.com", role="user", created_by=admin).token
    r = client.post("/auth/redeem-invite", json={"token": token, "password": "brand-new-pass"})
    assert r.status_code == 201
    assert r.json()["email"] == "newbie@example.com"
    assert r.json()["is_admin"] is False
    sid = r.headers["set-cookie"].split(f"{COOKIE}=", 1)[1].split(";", 1)[0]
    assert client.get("/auth/me", headers=_cookie_header(sid)).json()["email"] == "newbie@example.com"


def test_redeem_admin_invite_grants_admin(client, multi_user):
    with get_session() as s:
        token = create_invite(s, email="boss@example.com", role="admin").token
    r = client.post("/auth/redeem-invite", json={"token": token, "password": "boss-pass-1234"})
    assert r.status_code == 201
    assert r.json()["is_admin"] is True


def test_redeem_used_invite_rejected(client, multi_user):
    with get_session() as s:
        token = create_invite(s, email="once@example.com").token
    assert client.post(
        "/auth/redeem-invite", json={"token": token, "password": "first-pass-123"}
    ).status_code == 201
    # Second redemption of the same token fails.
    r = client.post("/auth/redeem-invite", json={"token": token, "password": "second-pass-12"})
    assert r.status_code == 400


def test_redeem_unknown_invite_rejected(client, multi_user):
    r = client.post("/auth/redeem-invite", json={"token": "nope", "password": "whatever-123"})
    assert r.status_code == 400


# --- owner isolation --------------------------------------------------------


def test_repos_isolated_between_owners(client, multi_user, add_repo):
    alice = _make_user(email="alice@example.com")
    bob = _make_user(email="bob@example.com")
    add_repo(name="alice-repo", clone_url="https://example.com/alice.git", owner_id=alice)
    add_repo(name="bob-repo", clone_url="https://example.com/bob.git", owner_id=bob)

    alice_sid = _make_session(alice)
    bob_sid = _make_session(bob)

    alice_repos = client.get("/repos", headers=_cookie_header(alice_sid)).json()["repos"]
    bob_repos = client.get("/repos", headers=_cookie_header(bob_sid)).json()["repos"]
    assert [r["name"] for r in alice_repos] == ["alice-repo"]
    assert [r["name"] for r in bob_repos] == ["bob-repo"]


def test_commits_isolated_between_owners(client, multi_user, add_commit):
    alice = _make_user(email="alice@example.com")
    bob = _make_user(email="bob@example.com")
    add_commit(hash="a" * 40, repo="alice-repo", owner_id=alice)
    add_commit(hash="b" * 40, repo="bob-repo", owner_id=bob)

    alice_sid = _make_session(alice)
    out = client.get("/commits", headers=_cookie_header(alice_sid)).json()
    assert out["total"] == 1
    assert out["commits"][0]["repo"] == "alice-repo"


def test_cannot_delete_another_users_repo(client, multi_user, add_repo):
    alice = _make_user(email="alice@example.com")
    bob = _make_user(email="bob@example.com")
    alice_repo = add_repo(name="alice-repo", clone_url="https://example.com/a.git", owner_id=alice)
    bob_sid = _make_session(bob)
    # Bob can't see or delete Alice's repo -> 404 (not 403, no existence leak).
    assert client.delete(f"/repos/{alice_repo}", headers=_cookie_header(bob_sid)).status_code == 404


# --- /providers admin gating (#65) ------------------------------------------


def test_providers_admin_only_in_multi_user(client, multi_user):
    admin = _make_user(email="admin@example.com", is_admin=True)
    regular = _make_user(email="user@example.com", is_admin=False)
    assert client.get("/providers", headers=_cookie_header(_make_session(admin))).status_code == 200
    assert (
        client.get("/providers", headers=_cookie_header(_make_session(regular))).status_code == 403
    )


# --- bootstrap invite (startup) ---------------------------------------------


def test_bootstrap_invite_minted_when_no_admin(multi_user):
    from backend.auth import ensure_bootstrap_invite
    from backend.db import InviteRow

    with get_session() as s:
        token = ensure_bootstrap_invite(s)
        assert token is not None
        invite = s.scalar(select(InviteRow).where(InviteRow.token == token))
        assert invite is not None and invite.role == "admin"
    # Idempotent: a second call returns the same still-unused token.
    with get_session() as s:
        assert ensure_bootstrap_invite(s) == token


def test_bootstrap_invite_skipped_when_admin_exists(multi_user):
    _make_user(email="admin@example.com", is_admin=True)
    from backend.auth import ensure_bootstrap_invite

    with get_session() as s:
        assert ensure_bootstrap_invite(s) is None


def test_off_mode_no_bootstrap_invite():
    # AUTH_MODE defaults to off here; ensure_bootstrap_invite is a no-op.
    from backend.auth import ensure_bootstrap_invite

    with get_session() as s:
        assert ensure_bootstrap_invite(s) is None
