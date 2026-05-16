import subprocess
from standup.models import Commit

def get_raw_log(repo_path: str, since: str, until: str, author: str | None = None) -> str:
    """
    args: repo_path, since, until, author

    Fetches the specified raw git logs.
    """
    cmd = ["git", "log",
        f"--since={since}",
        f"--until={until}",
        "--pretty=format:%H\x1f%ad\x1f%an\x1f%s",
        "--date=short"]
    
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