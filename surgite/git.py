import os
import re
import subprocess
from datetime import date
from pathlib import Path

from surgite.models import Commit

REMOTE_PATTERNS = re.compile(r"^(https?://|git@|git://|ssh://)")


def is_remote_url(path: str) -> bool:
    """Detect if a path looks like a remote git URL."""
    return bool(REMOTE_PATTERNS.match(path))


def _repo_name_from_url(url: str) -> str:
    """Extract a human-friendly repo name from a remote URL.
    Examples:
      https://github.com/user/repo.git -> repo
      git@github.com:user/repo.git -> repo
      https://github.com/user/repo -> repo
    """
    name = url.rstrip("/")
    if name.endswith(".git"):
        name = name[:-4]
    if ":" in name and not name.startswith("http"):
        name = name.split(":")[-1]
    name = name.rstrip("/").split("/")[-1]
    return name


def ensure_repo(name: str, url: str, cache_dir: str) -> str:
    """Ensure a remote repo is cloned (shallow). Returns the local path.

    If already cloned, fetches latest. Bounds the shallow clone by time
    (--shallow-since) rather than commit count, so the default 7-day
    query window is always covered regardless of commit volume.
    Depth can be overridden with the CLONE_DEPTH env var (in days,
    default 30).
    """
    dest = os.path.join(cache_dir, name)
    Path(cache_dir).mkdir(parents=True, exist_ok=True)

    clone_since_days = int(os.environ.get("CLONE_DEPTH", "30"))
    since_arg = f"--shallow-since={clone_since_days}.days.ago"

    if os.path.isdir(os.path.join(dest, ".git")):
        subprocess.run(
            ["git", "fetch", since_arg, "origin"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        )
        # Refresh origin/HEAD so a renamed default branch (master -> main)
        # is picked up on the next ingest instead of reading a stale branch.
        subprocess.run(
            ["git", "remote", "set-head", "origin", "-d"],
            cwd=dest,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "reset", "--hard", "origin/HEAD"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        )
    else:
        subprocess.run(
            ["git", "clone", since_arg, url, dest],
            capture_output=True,
            text=True,
            check=True,
        )
    return dest


def ls_remote(url: str, timeout: int = 10) -> None:
    """Cheaply check a remote is reachable without cloning. Runs
    `git ls-remote --heads <url>` and raises RuntimeError on a non-zero exit
    (auth failure, DNS, network) or timeout. Used by the deep health check."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", url],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"git ls-remote timed out after {timeout}s") from exc
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git ls-remote failed")


def _is_git_ref(repo_path: str, value: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", value], capture_output=True, cwd=repo_path
    )
    return result.returncode == 0


def get_raw_log(
    repo_path: str,
    since: str,
    until: str,
    author: str | None = None,
    since_commit: str | None = None,
) -> str:
    """
    args: repo_path, since, until, author, since_commit

    Fetches the specified raw git logs.
    """
    cmd = ["git", "log", "--pretty=format:%H\x1f%ad\x1f%an\x1f%s", "--date=short"]

    until_is_ref = _is_git_ref(repo_path, until)

    if since_commit:
        if until_is_ref:
            cmd.append(f"{since_commit}..{until}")
        else:
            cmd.append(f"{since_commit}..")
            cmd.append(f"--until={until}")
    else:
        if until_is_ref:
            cmd.append(until)
            cmd.append(f"--since={since}")
        else:
            cmd.append(f"--since={since}")
            cmd.append(f"--until={until}")

    if author:
        cmd.append(f"--author={author}")

    result = subprocess.run(
        cmd,
        text=True,  # necessary to get a usable output
        capture_output=True,
        cwd=repo_path,  # Without this, git log runs in whatever directory you're in
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return result.stdout


def parse_log(raw_log: str) -> list[Commit]:
    """
    args: raw_log

    Parses the raw git log into a list of Commit objects.
    """
    lines = raw_log.splitlines()
    commits = []
    for line in lines:
        hash, date_str, author, message = line.split("\x1f", maxsplit=3)
        commits.append(
            Commit(
                hash=hash,
                date=date.fromisoformat(date_str),
                author=author,
                message=message,
            )
        )
    return commits
