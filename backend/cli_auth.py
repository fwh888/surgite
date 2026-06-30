"""CLI-side auth for `standup` (0.5.0 slice 1, item 8).

The CLI is the bootstrap path for a multi_user deployment: an operator redeems
the invite the server logs on first run, which creates their account and drops
a session cookie into a local 0600 jar. Subsequent `standup --registered`
calls reuse that session. `--login` / `--logout` switch users.

Auth precedence for `--registered` calls:
  1. a saved session cookie for the target API URL (interactive operator), else
  2. a long-lived API key from STANDUP_API_KEY (CI / scripts).

STANDUP_API_TOKEN (0.4.0) is accepted as a deprecated alias for
STANDUP_API_KEY with a one-time warning.

Session storage (0.6.0): the cookie lives in the OS keyring by default —
the login keychain on macOS, the Secret Service on Linux (GNOME Keyring,
KWallet, KeePassXC), the Credential Manager on Windows. When no keyring
backend is available (a headless box with no D-Bus) or `--keyring-file`
is passed, it falls back to a 0600 file at $XDG_CONFIG_HOME/standup/session
(default ~/.config/standup/session). An existing 0600 file from <=0.5.0 is
migrated into the keyring on first read, then shredded.
"""

import getpass
import json
import os
import sys
from pathlib import Path

import httpx
import keyring
import keyring.errors

_KEYRING_SERVICE = "standup-gen"
_KEYRING_USER = "session"

# Set by the CLI's --keyring-file flag (and by tests). When True we skip the
# keyring entirely and use the 0600 file — for headless servers, CI, and the
# test suite, which must not touch the developer's real login keychain.
_force_file = False


def use_file_fallback(force: bool) -> None:
    """Force (or unforce) the 0600-file backend instead of the OS keyring."""
    global _force_file
    _force_file = force


def _keyring_available() -> bool:
    """True if a real OS keyring backend is configured. keyring installs a
    no-op `fail` backend when nothing real is present (headless, no D-Bus);
    we treat that as 'use the file fallback'."""
    if _force_file:
        return False
    try:
        from keyring.backends.fail import Keyring as _FailKeyring

        return not isinstance(keyring.get_keyring(), _FailKeyring)
    except Exception:
        return False


def _config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "standup"


def session_file() -> Path:
    return _config_dir() / "session"


def _write_session_file(blob: str) -> None:
    d = _config_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = session_file()
    # Create with restrictive perms from the start, then write.
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_text(blob)


def _read_session_file() -> dict | None:
    path = session_file()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError, OSError:
        return None


def _shred_session_file() -> None:
    """Overwrite then unlink the 0600 file. ponytail: a single overwrite is
    best-effort — on an SSD/CoW filesystem wear-levelling may leave the old
    block readable; the real protection is the keyring, this just avoids a
    plaintext cookie lingering at a well-known path."""
    path = session_file()
    if not path.exists():
        return
    try:
        with open(path, "r+b") as f:
            f.write(os.urandom(max(path.stat().st_size, 1)))
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        pass
    path.unlink(missing_ok=True)


def save_session(api_url: str, cookie_name: str, cookie_value: str) -> None:
    """Persist the session cookie for `api_url` (keyring, or 0600 file)."""
    blob = json.dumps(
        {"api_url": api_url, "cookie_name": cookie_name, "cookie_value": cookie_value}
    )
    if _keyring_available():
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_USER, blob)
        _shred_session_file()  # don't leave a stale plaintext copy behind
        return
    _write_session_file(blob)


def load_session() -> dict | None:
    if not _keyring_available():
        return _read_session_file()
    blob = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USER)
    if blob is None:
        # Migration: a 0600 file from <=0.5.0. Move it into the keyring once,
        # then shred the file so the plaintext cookie stops lingering on disk.
        migrated = _read_session_file()
        if migrated is None:
            return None
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_USER, json.dumps(migrated))
        _shred_session_file()
        print("Migrated CLI session from the 0600 file into the OS keyring.", file=sys.stderr)
        return migrated
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return None


def clear_session() -> None:
    if _keyring_available():
        try:
            keyring.delete_password(_KEYRING_SERVICE, _KEYRING_USER)
        except keyring.errors.PasswordDeleteError:
            pass  # nothing stored; clearing is idempotent
    _shred_session_file()  # also remove any file copy (fallback or pre-migration)


def _parse_set_cookie(header: str | None) -> tuple[str | None, str | None]:
    """Pull (name, value) out of a Set-Cookie header, ignoring attributes."""
    if not header:
        return None, None
    first = header.split(";", 1)[0].strip()
    if "=" not in first:
        return None, None
    name, value = first.split("=", 1)
    return name, value


def resolve_api_key() -> str | None:
    key = os.environ.get("STANDUP_API_KEY")
    if key:
        return key
    legacy = os.environ.get("STANDUP_API_TOKEN")
    if legacy:
        print(
            "warning: STANDUP_API_TOKEN is deprecated; rename it to STANDUP_API_KEY.",
            file=sys.stderr,
        )
        return legacy
    return None


def auth_headers(api_url: str) -> dict[str, str]:
    """Headers that authenticate a `--registered` call: the saved session
    cookie if it's for this API URL, else a Bearer API key, else nothing
    (off/single_user deployments need no auth)."""
    sess = load_session()
    if sess and sess.get("api_url") == api_url and sess.get("cookie_value"):
        return {"Cookie": f"{sess['cookie_name']}={sess['cookie_value']}"}
    key = resolve_api_key()
    if key:
        return {"Authorization": f"Bearer {key}"}
    return {}


def cmd_login(api_url: str, email: str | None = None, password: str | None = None) -> int:
    email = email or os.environ.get("STANDUP_EMAIL") or input("Email: ")
    password = password or os.environ.get("STANDUP_PASSWORD") or getpass.getpass("Password: ")
    try:
        resp = httpx.post(
            f"{api_url}/auth/login", json={"email": email, "password": password}, timeout=30
        )
    except httpx.HTTPError as e:
        print(f"Login failed: {e}", file=sys.stderr)
        return 1
    if resp.status_code != 200:
        print(f"Login failed: {resp.status_code} {resp.text}", file=sys.stderr)
        return 1
    name, value = _parse_set_cookie(resp.headers.get("set-cookie"))
    if not value:
        print("Login succeeded but no session cookie was returned.", file=sys.stderr)
        return 1
    save_session(api_url, name or "session", value)
    print(f"Logged in as {resp.json().get('email')}.")
    return 0


def cmd_logout(api_url: str) -> int:
    sess = load_session()
    headers = {}
    if sess and sess.get("cookie_value"):
        headers = {"Cookie": f"{sess['cookie_name']}={sess['cookie_value']}"}
    try:
        httpx.post(f"{api_url}/auth/logout", headers=headers, timeout=30)
    except httpx.HTTPError:
        pass  # Local cookie removal is what matters; best-effort server revoke.
    clear_session()
    print("Logged out.")
    return 0


def cmd_redeem_invite(
    api_url: str, token: str, password: str | None = None, email: str | None = None
) -> int:
    password = (
        password or os.environ.get("STANDUP_PASSWORD") or getpass.getpass("Choose a password: ")
    )
    body: dict[str, str] = {"token": token, "password": password}
    if email or os.environ.get("STANDUP_EMAIL"):
        body["email"] = email or os.environ["STANDUP_EMAIL"]
    try:
        resp = httpx.post(f"{api_url}/auth/redeem-invite", json=body, timeout=30)
    except httpx.HTTPError as e:
        print(f"Invite redemption failed: {e}", file=sys.stderr)
        return 1
    if resp.status_code != 201:
        print(f"Invite redemption failed: {resp.status_code} {resp.text}", file=sys.stderr)
        return 1
    name, value = _parse_set_cookie(resp.headers.get("set-cookie"))
    if value:
        save_session(api_url, name or "session", value)
    print(f"Account created; logged in as {resp.json().get('email')}.")
    return 0
