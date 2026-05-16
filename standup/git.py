import subprocess
from standup.models import Commit

def _is_git_ref(repo_path: str, value: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", value],
        capture_output=True,
        cwd=repo_path
    )
    return result.returncode == 0

def get_raw_log(repo_path: str, since: str, until: str, author: str | None = None, since_commit: str | None = None) -> str:
    """
    args: repo_path, since, until, author, since_commit

    Fetches the specified raw git logs.
    """
    cmd = ["git", "log",
        "--pretty=format:%H\x1f%ad\x1f%an\x1f%s",
        "--date=short"]

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
        text=True, # necessary to get a usable output 
        capture_output=True,
        cwd=repo_path # Without this, git log runs in whatever directory you're in
    )
    if result.returncode !=0:
        raise RuntimeError(result.stderr)
    return result.stdout

def parse_log(raw_log: str) -> list[Commit]:
    """
    args: raw_log
    
    Parses the raw git log into a list of Commit objects.
    """
    lines = raw_log.splitlines()
    return [Commit(*line.split("\x1f")) for line in lines] # Unpacking the split line directly into the Commit dataclass constructor