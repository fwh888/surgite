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
    from standup import summarizer

    def fake_generate(commit_log, provider=None, model=None):
        return {"summary": "Accomplishments:\n- shipped it", "provider": "groq", "model": "x"}

    monkeypatch.setattr(summarizer, "generate_summary", fake_generate)
    body = client.get("/summary?ai=true&provider=groq").json()
    assert body["ai_summary"].startswith("Accomplishments:")
    assert body["ai_provider"] == "groq"
    assert body["ai_model"] == "x"


def test_ingest_rejects_missing_repo_path(client):
    r = client.post("/ingest", json={"repo_path": "/nonexistent/path/xyz"})
    assert r.status_code == 400


def test_ingest_rejects_invalid_date(client):
    r = client.post(
        "/ingest",
        json={"repo_path": "/tmp", "since": "not-a-date"},
    )
    assert r.status_code == 422
