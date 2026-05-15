# Step 4: Verify the CLI end-to-end

**The instruction:** "Already implemented end-to-end. Verify it still works after the Step 2 delimiter change before touching the database."

No new code. This is a checkpoint — confirm the entire existing CLI pipeline works before you build anything on top of it.

## What to test

### Basic output

```bash
uv run standup /path/to/any/local/repo --since 2026-05-01
```

You should see formatted commit lines printed to stdout:

```
[2026-05-14] your commit message (Your Name) <a1b2c3d>
```

### Date filtering

```bash
uv run standup /path/to/repo --since 2026-05-01 --until 2026-05-07
```

Only commits in that window should appear.

### Author filtering

```bash
uv run standup /path/to/repo --since 2026-05-01 --author "Your Name"
```

Only commits by that author should appear.

### File output

```bash
uv run standup /path/to/repo --since 2026-05-01 --output /tmp/standup.txt
cat /tmp/standup.txt
```

Nothing printed to stdout. The file should contain the same lines you'd see otherwise.

### AI summarize (optional — requires GROQ_API_KEY)

If your `.env` has a valid `GROQ_API_KEY`:

```bash
uv run standup /path/to/repo --since 2026-05-01 --summarize
```

Should print a plain-English summary instead of the raw commit lines.

## What the data flow looks like

```
repo_path + flags
     ↓
get_raw_log()   → raw git output (one line per commit, \x1f delimited after Step 2)
     ↓
parse_log()     → list[Commit]
     ↓
format_log()    → formatted string
     ↓
stdout / file / summarize_commits()
```

Understanding this flow now will help you in Step 7, where `api.py` reuses `get_raw_log()` and `parse_log()` directly for `POST /ingest`.

## What you're not doing yet

- Do not add `--ingest` yet (Step 8)
- Do not create `config.py` yet (Step 5 is next)

---

**Step 4 is done when:** all the flags work correctly and the output looks right.

**Next:** [Step 5](step-5-config.md) — create `config.py` to centralize environment variable loading before the database and API layers need them.
