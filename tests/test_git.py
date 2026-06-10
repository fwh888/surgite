import subprocess
from datetime import date
from pathlib import Path

import pytest

from backend.git import _repo_name_from_url, get_raw_log, is_remote_url, parse_log
from backend.models import Commit


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/u/r.git",
        "http://forge/u/r.git",
        "git@github.com:u/r.git",
        "git://host/u/r.git",
        "ssh://git@host/u/r.git",
    ],
)
def test_is_remote_url_true(url):
    assert is_remote_url(url) is True


@pytest.mark.parametrize("path", ["/home/user/repo", "./repo", "repo", "C:\\repo"])
def test_is_remote_url_false(path):
    assert is_remote_url(path) is False


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/user/repo.git", "repo"),
        ("git@github.com:user/repo.git", "repo"),
        ("https://github.com/user/repo", "repo"),
        ("https://github.com/user/repo/", "repo"),
        ("ssh://git@host/group/sub/repo.git", "repo"),
    ],
)
def test_repo_name_from_url(url, expected):
    assert _repo_name_from_url(url) == expected


def test_parse_log_empty_returns_empty_list():
    assert parse_log("") == []


def test_parse_log_single_commit():
    raw = "a1b2c3d\x1f2026-06-01\x1fAlice\x1ffix bug"
    assert parse_log(raw) == [
        Commit(hash="a1b2c3d", date=date(2026, 6, 1), author="Alice", message="fix bug")
    ]


def test_parse_log_multiple_commits():
    raw = "h1\x1f2026-06-01\x1fA\x1fone\nh2\x1f2026-06-02\x1fB\x1ftwo"
    commits = parse_log(raw)
    assert [c.hash for c in commits] == ["h1", "h2"]
    assert [c.message for c in commits] == ["one", "two"]


def test_parse_log_keeps_message_intact_past_three_splits():
    # split(maxsplit=3): anything after the 3rd separator stays in the message.
    raw = "h1\x1f2026-06-01\x1fA\x1ffix: a\x1fb"
    [commit] = parse_log(raw)
    assert commit.message == "fix: a\x1fb"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.t", "-c", "user.name=Tester", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def test_get_raw_log_roundtrips_on_a_real_repo(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "f.txt").write_text("hi")
    _git(tmp_path, "add", "f.txt")
    _git(tmp_path, "commit", "-q", "-m", "initial commit")

    raw = get_raw_log(str(tmp_path), "1970-01-01", "now")
    [commit] = parse_log(raw)
    assert commit.message == "initial commit"
    assert commit.author == "Tester"
    assert len(commit.hash) == 40


def test_get_raw_log_raises_runtimeerror_outside_a_repo(tmp_path):
    with pytest.raises(RuntimeError):
        get_raw_log(str(tmp_path), "1970-01-01", "now")
