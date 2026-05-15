# Step 3: Confirm `formatter.py` needs no changes

**The instruction:** "Already implemented. No changes needed."

Step 3 is another orientation step, not a coding step. Read the file, understand what it does, and confirm it still works after the Step 2 delimiter change.

## What the file does

Open `standup/formatter.py`. It has two functions:

```python
def format_commit(commit: Commit) -> str:
    return f"[{commit.date}] {commit.message} ({commit.author}) <{commit.hash[:7]}>"

def format_log(commits: list[Commit]) -> str:
    return "\n".join(format_commit(c) for c in commits)
```

- `format_commit` takes a single `Commit` and returns a human-readable string. Note `commit.hash[:7]` — this is where the 7-character short hash is derived. It is never stored; it's always computed here.
- `format_log` joins a list of commits into a single newline-separated string for stdout or file output.

## Why no changes are needed here

The formatter only touches the four fields that already exist on `Commit`: `date`, `message`, `author`, `hash`. The delimiter change in Step 2 affects how `Commit` objects are constructed in `git.py` — by the time a `Commit` reaches `formatter.py`, the fields are already clean strings. This file is unaffected.

The two new fields coming in Step 6 (`repo` and `ingested_at`) will be used by the API responses, not by this formatter. The CLI output format stays exactly as it is.

## Verify it still works after Step 2

If you haven't already, run the CLI once to confirm the formatter still produces correct output:

```bash
uv run standup /path/to/any/local/repo --since 2026-05-01
```

Expected output format:
```
[2026-05-14] add scan systemd timer (Nick Coleman) <a1b2c3d>
[2026-05-13] fix auth middleware (Nick Coleman) <e4f5g6h>
```

---

**Step 3 is done when:** you've read the file, confirmed `hash[:7]` is how short hashes are derived, and the CLI output looks correct.

**Next:** [Step 4](step-4-cli-verify.md) — run the full CLI end-to-end and confirm everything works before touching the database.
