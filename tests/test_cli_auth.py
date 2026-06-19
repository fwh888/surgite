"""Tests for the CLI-side auth helpers (backend/cli_auth.py).

The network commands (cmd_login etc.) are thin httpx wrappers; the logic worth
testing is the session jar, the API-key precedence, and the deprecation shim.
"""

import os
import stat

import pytest

from backend import cli_auth


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    """Point the session jar at a temp dir and clear auth env vars."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    for var in ("STANDUP_API_KEY", "STANDUP_API_TOKEN", "STANDUP_EMAIL", "STANDUP_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    yield


def test_save_load_clear_session(tmp_path):
    assert cli_auth.load_session() is None
    cli_auth.save_session("http://api", "__Host-standup_session", "abc123")
    sess = cli_auth.load_session()
    assert sess == {
        "api_url": "http://api",
        "cookie_name": "__Host-standup_session",
        "cookie_value": "abc123",
    }
    cli_auth.clear_session()
    assert cli_auth.load_session() is None


def test_session_file_is_0600():
    cli_auth.save_session("http://api", "n", "v")
    mode = stat.S_IMODE(os.stat(cli_auth.session_file()).st_mode)
    assert mode == 0o600


def test_load_session_tolerates_corruption():
    path = cli_auth.session_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json{")
    assert cli_auth.load_session() is None


@pytest.mark.parametrize(
    "header,expected",
    [
        ("__Host-standup_session=xyz; HttpOnly; Secure", ("__Host-standup_session", "xyz")),
        ("session=abc", ("session", "abc")),
        ("", (None, None)),
        (None, (None, None)),
        ("no-equals-sign; Path=/", (None, None)),
    ],
)
def test_parse_set_cookie(header, expected):
    assert cli_auth._parse_set_cookie(header) == expected


def test_resolve_api_key_prefers_new_var(monkeypatch):
    monkeypatch.setenv("STANDUP_API_KEY", "new-key")
    monkeypatch.setenv("STANDUP_API_TOKEN", "old-token")
    assert cli_auth.resolve_api_key() == "new-key"


def test_resolve_api_key_falls_back_to_legacy_with_warning(monkeypatch, capsys):
    monkeypatch.setenv("STANDUP_API_TOKEN", "old-token")
    assert cli_auth.resolve_api_key() == "old-token"
    assert "deprecated" in capsys.readouterr().err.lower()


def test_resolve_api_key_none_when_unset():
    assert cli_auth.resolve_api_key() is None


def test_auth_headers_prefers_matching_session():
    cli_auth.save_session("http://api", "__Host-standup_session", "sid42")
    headers = cli_auth.auth_headers("http://api")
    assert headers == {"Cookie": "__Host-standup_session=sid42"}


def test_auth_headers_ignores_session_for_other_url(monkeypatch):
    cli_auth.save_session("http://other", "n", "v")
    monkeypatch.setenv("STANDUP_API_KEY", "k")
    assert cli_auth.auth_headers("http://api") == {"Authorization": "Bearer k"}


def test_auth_headers_empty_when_nothing_configured():
    assert cli_auth.auth_headers("http://api") == {}


def test_cmd_login_saves_session(monkeypatch):
    """cmd_login parses the Set-Cookie from a stubbed response and saves it."""

    class FakeResp:
        status_code = 200
        headers = {"set-cookie": "__Host-standup_session=tok99; HttpOnly; Secure"}

        @staticmethod
        def json():
            return {"email": "nick@example.com"}

    monkeypatch.setattr(cli_auth.httpx, "post", lambda *a, **k: FakeResp())
    rc = cli_auth.cmd_login("http://api", email="nick@example.com", password="pw")
    assert rc == 0
    assert cli_auth.load_session()["cookie_value"] == "tok99"


def test_cmd_login_failure_returns_1(monkeypatch):
    class FakeResp:
        status_code = 401
        text = "nope"
        headers: dict = {}

    monkeypatch.setattr(cli_auth.httpx, "post", lambda *a, **k: FakeResp())
    assert cli_auth.cmd_login("http://api", email="a@b.c", password="x") == 1
    assert cli_auth.load_session() is None


def test_cmd_logout_clears_session(monkeypatch):
    cli_auth.save_session("http://api", "n", "v")
    monkeypatch.setattr(cli_auth.httpx, "post", lambda *a, **k: None)
    assert cli_auth.cmd_logout("http://api") == 0
    assert cli_auth.load_session() is None
