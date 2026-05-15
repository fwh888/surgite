# Step 2: Update the delimiter in `git.py`

**The instruction:** Update the delimiter from `|` to `\x1f` so commit messages containing `|` don't break parsing.

This is the first real code change. It's small — two lines in `standup/git.py` — but worth understanding before touching.

## Why the delimiter matters

The current `git log` format string is:

```
--pretty=format:%H|%ad|%an|%s
```

Each commit comes back as one line, with fields separated by `|`. Then `parse_log` splits on `|`:

```python
Commit(*line.split("|"))
```

This breaks if a commit message contains a pipe character. For example:

```
a1b2c3d|2026-05-14|Nick Coleman|fix auth|remove old handler
```

That splits into 5 parts, not 4, and the `Commit(...)` constructor crashes.

The fix is to use ASCII unit-separator (`\x1f`) instead — a control character that will never appear in a commit message.

## The two-line change

**In `get_raw_log()`**, change the format string from:

```python
"--pretty=format:%H|%ad|%an|%s",
```

to:

```python
"--pretty=format:%H\x1f%ad\x1f%an\x1f%s",
```

**In `parse_log()`**, change the split character from:

```python
return [Commit(*line.split("|")) for line in lines]
```

to:

```python
return [Commit(*line.split("\x1f")) for line in lines]
```

## Verify it works

After making the change, run the CLI against a local repo and confirm output looks the same as before:

```bash
uv run standup /path/to/any/local/repo --since 2026-05-01
```

If you want to specifically test the `|` edge case, find a commit with a pipe in its message, or make a test commit:

```bash
cd /tmp && git init pipe-test && cd pipe-test
git commit --allow-empty -m "fix: handle x|y edge case"
uv run standup /tmp/pipe-test --since 2020-01-01
```

You should see the full message — including the pipe — printed correctly.

## What you're not doing yet

- Do not touch `formatter.py` (Step 3 confirms it needs no changes)
- Do not touch `standup.py` (Step 4 verifies the CLI end-to-end)

---

**Step 2 is done when:** the delimiter is `\x1f` in both `get_raw_log()` and `parse_log()`, and `uv run standup` still produces correct output.

**Next:** [Step 3](step-3-formatter.md) — confirm `formatter.py` needs no changes, then move on to verifying the full CLI in Step 4.
