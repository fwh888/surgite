"""Tests for the ingest path: bulk upsert, freshness cache, and repo filtering.

The git layer is faked (no subprocess calls); everything DB-side is real.
"""

from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import event, select

from backend import api
from backend.db import CommitRow, get_session
from backend.models import Commit


@pytest.fixture(autouse=True)
def _fresh_ingest_cache():
    api._INGEST_CACHE.clear()
    yield
    api._INGEST_CACHE.clear()


@pytest.fixture
def fake_git(monkeypatch):
    """Stub the git layer. Returns a recorder: set .commits to control what
    parse_log yields; .ensured collects every ensure_repo call."""

    class Recorder:
        commits: list[Commit] = []
        ensured: list[str] = []

    rec = Recorder()
    monkeypatch.setattr(
        "backend.git.ensure_repo",
        lambda name, url, cache: rec.ensured.append(name) or f"/fake/{name}",
    )
    monkeypatch.setattr(api, "get_raw_log", lambda *a, **kw: "")
    monkeypatch.setattr(api, "parse_log", lambda raw: list(rec.commits))
    return rec


def make_commits(n: int, commit_date: date = date(2026, 6, 1)) -> list[Commit]:
    return [
        Commit(hash=f"{i:040x}", date=commit_date, author="Alice", message=f"commit {i}")
        for i in range(n)
    ]


@contextmanager
def count_selects():
    """Count SELECT statements hitting the engine (N+1 regression guard)."""
    statements: list[str] = []

    def before(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().lower().startswith("select"):
            statements.append(statement)

    from backend.db import engine

    event.listen(engine, "before_cursor_execute", before)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", before)


# --- _ingest_repo: bulk upsert ---


def test_ingest_inserts_new_commits(add_repo, fake_git):
    repo_id = add_repo()
    fake_git.commits = make_commits(5)

    result = api._ingest_repo(repo_id, "demo", "https://example.com/demo.git")

    assert result == {"repo": "demo", "inserted": 5, "updated": 0, "unchanged": 0}
    with get_session() as s:
        assert len(s.scalars(select(CommitRow)).all()) == 5


def test_reingest_leaves_existing_rows_unchanged(add_repo, fake_git):
    repo_id = add_repo()
    fake_git.commits = make_commits(5)

    api._ingest_repo(repo_id, "demo", "https://example.com/demo.git")
    result = api._ingest_repo(repo_id, "demo", "https://example.com/demo.git")

    assert result == {"repo": "demo", "inserted": 0, "updated": 0, "unchanged": 5}


def test_ingest_reassigns_commit_to_new_repo_name(add_repo, add_commit, fake_git):
    repo_id = add_repo(name="renamed")
    add_commit(hash="0" * 40, short_hash="0000000", repo="oldname")
    fake_git.commits = [Commit(hash="0" * 40, date=date(2026, 6, 1), author="Alice", message="x")]

    result = api._ingest_repo(repo_id, "renamed", "https://example.com/renamed.git")

    assert result["updated"] == 1
    with get_session() as s:
        assert s.get(CommitRow, "0" * 40).repo == "renamed"


def test_ingest_uses_constant_number_of_selects(add_repo, fake_git):
    """Regression: upsert used to do one SELECT per commit (N+1)."""
    repo_id = add_repo()
    fake_git.commits = make_commits(50)

    with count_selects() as statements:
        api._ingest_repo(repo_id, "demo", "https://example.com/demo.git")

    # One bulk hash lookup + one RepoRow get; allow slack for dialect chatter.
    assert len(statements) <= 4, f"expected a constant number of SELECTs, got {len(statements)}"


def test_ingest_updates_last_ingested_at(add_repo, fake_git):
    repo_id = add_repo()
    fake_git.commits = []

    api._ingest_repo(repo_id, "demo", "https://example.com/demo.git")

    with get_session() as s:
        from backend.db import RepoRow

        assert s.get(RepoRow, repo_id).last_ingested_at is not None


# --- _ingest_all_repos: freshness cache + repo filter ---


def test_second_ingest_within_ttl_is_skipped(add_repo, fake_git):
    add_repo()

    first = api._ingest_all_repos()
    second = api._ingest_all_repos()

    assert fake_git.ensured == ["demo"]  # git touched exactly once
    assert "inserted" in first[0]
    assert second == [{"repo": "demo", "skipped": True}]


def test_expired_cache_entry_reingests(add_repo, fake_git):
    add_repo()

    api._ingest_all_repos()
    for key in api._INGEST_CACHE:
        api._INGEST_CACHE[key] = datetime.now(UTC) - api.INGEST_TTL - timedelta(seconds=1)
    api._ingest_all_repos()

    assert fake_git.ensured == ["demo", "demo"]


def test_different_date_range_is_not_considered_fresh(add_repo, fake_git):
    """A repo ingested for one window must still be fetched for a wider one."""
    add_repo()

    api._ingest_all_repos()
    api._ingest_all_repos(since=datetime.now(UTC).date() - timedelta(days=30))

    assert fake_git.ensured == ["demo", "demo"]


def test_failed_ingest_is_not_cached_as_fresh(add_repo, fake_git, monkeypatch):
    add_repo()
    monkeypatch.setattr(
        api, "get_raw_log", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    result = api._ingest_all_repos()

    assert "error" in result[0]
    assert api._INGEST_CACHE == {}


def test_repo_filter_limits_ingest(add_repo, fake_git):
    add_repo(name="standup-gen", clone_url="https://example.com/standup-gen.git")
    add_repo(name="other-project", clone_url="https://example.com/other.git")

    api._ingest_all_repos(repo="standup")

    assert fake_git.ensured == ["standup-gen"]


def test_repo_filter_is_case_insensitive_substring(add_repo, fake_git):
    add_repo(name="Standup-Gen", clone_url="https://example.com/sg.git")

    api._ingest_all_repos(repo="standup")

    assert fake_git.ensured == ["Standup-Gen"]


# --- /summary wiring ---


def test_summary_passes_repo_filter_to_ingest(client, monkeypatch):
    received = {}

    def record(since=None, until=None, repo=None, session=None):
        received.update(since=since, until=until, repo=repo)
        return []

    monkeypatch.setattr(api, "_ingest_all_repos", record)
    client.get("/summary?repo=standup-gen&since=2026-06-01")

    assert received["repo"] == "standup-gen"
    assert received["since"] is not None


def test_summary_uses_single_session(client, add_repo, fake_git, monkeypatch):
    """Regression: /summary used to open a new session for each helper call."""
    from backend import db as db_module

    add_repo()
    fake_git.commits = []

    session_count = 0
    original_get_session = db_module.get_session

    def counting_get_session():
        nonlocal session_count
        session_count += 1
        return original_get_session()

    monkeypatch.setattr(db_module, "get_session", counting_get_session)
    client.get("/summary")

    assert session_count == 1, f"expected 1 session, got {session_count}"
