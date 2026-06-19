import os

from dotenv import load_dotenv

load_dotenv()


def _get_database_url() -> str:
    """Construct DATABASE_URL from POSTGRES_* env vars if not directly set."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    host = os.environ.get("POSTGRES_HOST", "db")
    port = os.environ.get("POSTGRES_PORT", "5432")
    user = os.environ.get("POSTGRES_USER", "standup")
    password = os.environ.get("POSTGRES_PASSWORD", "standup")
    db = os.environ.get("POSTGRES_DB", "standup")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


DATABASE_URL = _get_database_url()
API_HOST = os.environ.get("API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("API_PORT", 8000))
REPO_CACHE_DIR = os.environ.get("REPO_CACHE_DIR", "/var/standup/repos")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_FORMAT = os.environ.get("LOG_FORMAT", "")  # "json" enables JSON logs; default is human-readable
# Seconds between automatic background ingests of every registered repo.
# Set to 0 (or any non-positive value) to disable the scheduler — useful
# for one-off test runs where the lifespan can't actually start a task.
INGEST_INTERVAL = int(os.environ.get("INGEST_INTERVAL", "300"))
# Lifetime of a shared-summary slug (the /s/<slug> links).
SHARE_TTL_DAYS = int(os.environ.get("SHARE_TTL_DAYS", "7"))
# Summary provider keys (ANTHROPIC_API_KEY / GROQ_API_KEY / DEEPSEEK_API_KEY)
# are read by backend.summarizer at call time, not here.

# --- Auth (0.5.0) -----------------------------------------------------------
# AUTH_MODE selects how requests resolve to a user (see backend.auth):
#   off         — anonymous; every request resolves to the bootstrap user.
#                 This is the backward-compatible 0.4.0 behaviour and the
#                 default for the duration of the foundation slice.
#   single_user — every request resolves to the bootstrap user, but the auth
#                 machinery (hashing, sessions) exists and is exercised.
#   multi_user  — full session-cookie auth; /login + /logout exposed.
AUTH_MODE = os.environ.get("AUTH_MODE", "off")
# The account that owns all data in off/single_user mode, and the account the
# 0.4.0 → 0.5.0 migration backfills existing rows to. Created on demand.
BOOTSTRAP_OWNER_EMAIL = os.environ.get("BOOTSTRAP_OWNER_EMAIL", "owner@localhost")
# Session lifetime and sliding-refresh threshold (a session within this many
# days of expiry gets a fresh cookie on the next request).
SESSION_TTL_DAYS = int(os.environ.get("SESSION_TTL_DAYS", "14"))
SESSION_REFRESH_THRESHOLD_DAYS = int(os.environ.get("SESSION_REFRESH_THRESHOLD_DAYS", "7"))
# How often the lifespan scheduler purges expired sessions, in seconds.
SESSION_CLEANUP_INTERVAL = int(os.environ.get("SESSION_CLEANUP_INTERVAL", "3600"))
# The session cookie name. The __Host- prefix forces Secure + host-only +
# path=/ at the browser, which is the hardening we want in production. In
# DEBUG mode (plain-HTTP local dev) the prefix and Secure flag are dropped,
# because __Host- cookies are rejected by browsers over http://.
DEBUG = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")
SESSION_COOKIE_NAME = "standup_session" if DEBUG else "__Host-standup_session"
