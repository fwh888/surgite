from surgite.models import Commit


def format_commit(commit: Commit) -> str:
    return f"[{commit.date}] {commit.message} ({commit.author}) <{commit.hash[:7]}>"


def format_log(commits: list[Commit]) -> str:
    return "\n".join(format_commit(c) for c in commits)
