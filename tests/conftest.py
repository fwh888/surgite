"""
Test config. DATABASE_URL and the provider API keys must be set BEFORE any
`standup.*` import, because `standup.config` reads them at module-load time and
`standup.db` creates the engine at module-load time.
"""
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_db_file = Path(tempfile.gettempdir()) / "standup_test.db"
if _db_file.exists():
    _db_file.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_db_file}"
# Force every provider key empty so ai-summary tests see "not set" regardless of
# the developer's .env. load_dotenv() in standup.config respects pre-existing
# env vars and won't override these.
os.environ["GROQ_API_KEY"] = ""
os.environ["DEEPSEEK_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient

from standup.api import app
from standup.db import Base, CommitRow, RepoRow, engine, get_session


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    with get_session() as s:
        s.query(CommitRow).delete()
        s.query(RepoRow).delete()
        s.commit()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def add_commit():
    def _add(**overrides):
        defaults = {
            "hash": "a" * 40,
            "short_hash": "aaaaaaa",
            "date": "2026-05-19",
            "author": "Alice",
            "message": "init",
            "repo": "demo",
            "ingested_at": datetime.now(timezone.utc),
        }
        defaults.update(overrides)
        with get_session() as s:
            s.add(CommitRow(**defaults))
            s.commit()

    return _add


@pytest.fixture
def add_repo():
    def _add(**overrides):
        defaults = {
            "name": "demo",
            "path": "/tmp/demo",
            "added_at": datetime.now(timezone.utc),
            "last_ingested_at": None,
        }
        defaults.update(overrides)
        with get_session() as s:
            repo = RepoRow(**defaults)
            s.add(repo)
            s.commit()
            s.refresh(repo)
            return repo.id

    return _add
