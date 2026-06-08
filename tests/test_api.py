import io

import pytest

from backend.standup import main


@pytest.fixture(autouse=True)
def _mock_ingest(monkeypatch):
    from backend import api as api_module

    monkeypatch.setattr(
        api_module,
        "_ingest_repo",
        lambda *a, **kw: {"repo": "mocked", "inserted": 0, "updated": 0, "unchanged": 0},
    )
    monkeypatch.setattr(
        api_module,
        "_ingest_all_repos",
        lambda *a, **kw: [],
    )


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_commits_empty(client):
    r = client.get("/commits")
    assert r.status_code == 200
    assert r.json() == {"total": 0, "commits": []}


def test_commits_returns_inserted_rows(client, add_commit):
    add_commit(hash="b" * 40, short_hash="bbbbbbb", author="Bob")
    r = client.get("/commits")
    body = r.json()
    assert body["total"] == 1
    assert body["commits"][0]["author"] == "Bob"


def test_commits_filter_by_repo_substring(client, add_commit):
    add_commit(hash="1" * 40, short_hash="1111111", repo="standup-gen")
    add_commit(hash="2" * 40, short_hash="2222222", repo="other-project")
    r = client.get("/commits?repo=standup")
    body = r.json()
    assert body["total"] == 1
    assert body["commits"][0]["repo"] == "standup-gen"


def test_commit_by_short_hash(client, add_commit):
    add_commit(hash="abc1234" + "0" * 33, short_hash="abc1234")
    r = client.get("/commits/abc1234")
    assert r.status_code == 200
    assert r.json()["short_hash"] == "abc1234"


def test_commit_hash_too_short_returns_400(client):
    assert client.get("/commits/abc12").status_code == 400


def test_commit_hash_not_found(client):
    assert client.get("/commits/" + "0" * 40).status_code == 404


def test_commit_ambiguous_prefix_returns_409(client, add_commit):
    add_commit(hash="abc1234" + "1" * 33, short_hash="abc1234")
    add_commit(hash="abc1234" + "2" * 33, short_hash="abc1234")
    r = client.get("/commits/abc1234")
    assert r.status_code == 409
    assert len(r.json()["detail"]["candidates"]) == 2


def test_summary_counts_all_matching_commits(client, add_commit):
    """Regression: /summary used to inherit list_commits' default limit=50,
    so by_repo/by_day undercounted whenever total > 50."""
    for i in range(60):
        add_commit(hash=f"{i:040x}", short_hash=f"{i:07x}", repo="demo", date="2026-05-19")
    body = client.get("/summary").json()
    assert body["total_commits"] == 60
    assert sum(body["by_repo"].values()) == 60
    assert body["by_day"]["2026-05-19"] == 60


def test_summary_by_day_is_chronologically_sorted(client, add_commit):
    for i, d in enumerate(["2026-05-21", "2026-05-19", "2026-05-20"]):
        add_commit(hash=f"{i:040x}", short_hash=f"{i:07x}", date=d)
    assert list(client.get("/summary").json()["by_day"].keys()) == [
        "2026-05-19",
        "2026-05-20",
        "2026-05-21",
    ]


def test_summary_ai_without_key_returns_400(client):
    r = client.get("/summary?ai=true")
    assert r.status_code == 400


def test_providers_lists_all_with_anthropic_default(client):
    body = client.get("/providers").json()
    assert body["default"] == "anthropic"
    names = {p["name"] for p in body["providers"]}
    assert {"anthropic", "groq", "deepseek"} <= names
    # conftest clears every key, so nothing is available in tests.
    assert all(p["available"] is False for p in body["providers"])


def test_summary_ai_unknown_provider_returns_400(client, add_commit):
    add_commit()
    assert client.get("/summary?ai=true&provider=bogus").status_code == 400


def test_summary_ai_uses_selected_provider(client, add_commit, monkeypatch):
    add_commit()
    from backend import summarizer

    def fake_generate(commit_log, provider=None, model=None):
        return {"summary": "## Features\n- shipped it", "provider": "groq", "model": "x"}

    monkeypatch.setattr(summarizer, "generate_summary", fake_generate)
    body = client.get("/summary?ai=true&provider=groq").json()
    assert body["ai_summary"].startswith("## Features")
    assert body["ai_provider"] == "groq"
    assert body["ai_model"] == "x"


# --- /repos ---


def test_list_repos_empty(client):
    r = client.get("/repos")
    assert r.status_code == 200
    assert r.json() == {"repos": []}


def test_create_repo_returns_201(client):
    r = client.post("/repos", json={"url": "https://github.com/user/repo.git"})
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "repo"
    assert body["clone_url"] == "https://github.com/user/repo.git"
    assert body["last_ingested_at"] is None
    assert body["id"] is not None


def test_create_repo_appears_in_list(client):
    client.post("/repos", json={"url": "https://github.com/user/repo.git"})
    repos = client.get("/repos").json()["repos"]
    assert len(repos) == 1
    assert repos[0]["clone_url"] == "https://github.com/user/repo.git"


def test_create_repo_duplicate_url_returns_409(client):
    client.post("/repos", json={"url": "https://github.com/user/repo.git"})
    r = client.post("/repos", json={"url": "https://github.com/user/repo.git"})
    assert r.status_code == 409


def test_create_repo_non_remote_url_returns_400(client):
    r = client.post("/repos", json={"url": "/some/local/path"})
    assert r.status_code == 400


def test_delete_repo(client, add_repo):
    repo_id = add_repo()
    r = client.delete(f"/repos/{repo_id}")
    assert r.status_code == 204
    assert client.get("/repos").json()["repos"] == []


def test_delete_repo_not_found_returns_404(client):
    assert client.delete("/repos/999").status_code == 404


def test_cli_without_ingest_prints_formatted_log(monkeypatch):
    monkeypatch.setattr(
        "backend.standup.get_raw_log", lambda *a, **kw: "abc1234\x1f2026-06-01\x1fAlice\x1ffix bug"
    )
    monkeypatch.setattr("sys.argv", ["standup", "/r"])
    stdout = io.StringIO()
    monkeypatch.setattr("sys.stdout", stdout)

    main()

    assert "Alice" in stdout.getvalue()
    assert "abc1234" in stdout.getvalue()


def test_cli_summarize_runs_the_summarizer(monkeypatch):
    monkeypatch.setattr(
        "backend.standup.get_raw_log", lambda *a, **kw: "abc1234\x1f2026-06-01\x1fAlice\x1ffix bug"
    )
    monkeypatch.setattr(
        "backend.standup.summarize_commits", lambda text, **kw: "Accomplishments:\n- fixed a bug"
    )
    monkeypatch.setattr("sys.argv", ["standup", "/r", "--summarize"])
    stdout = io.StringIO()
    monkeypatch.setattr("sys.stdout", stdout)

    main()

    assert "Accomplishments:" in stdout.getvalue()


def test_cli_output_writes_to_file(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "backend.standup.get_raw_log", lambda *a, **kw: "abc1234\x1f2026-06-01\x1fAlice\x1ffix bug"
    )
    out_file = tmp_path / "summary.txt"
    monkeypatch.setattr("sys.argv", ["standup", "/r", "--output", str(out_file)])

    main()

    written = out_file.read_text()
    assert "fix bug" in written
    assert "Alice" in written
