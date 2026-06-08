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
# Summary provider keys (ANTHROPIC_API_KEY / GROQ_API_KEY / DEEPSEEK_API_KEY)
# are read by backend.summarizer at call time, not here.
