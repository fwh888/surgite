# Step 1: Review `models.py`

**The instruction:** "The `Commit` dataclass already exists. Leave it alone for now."

Step 1 is intentionally a no-op on the code itself. Its purpose is to orient you before you start changing things. Here's what to do:

## 1. Read the current dataclass

Open `standup/models.py`. It's 8 lines:

```python
@dataclass
class Commit:
    hash: str
    date: str
    author: str
    message: str
```

Understand what each field is:
- `hash` — the full 40-char git SHA
- `date` — a `YYYY-MM-DD` string (from `--date=short`)
- `author` — the committer's name string
- `message` — the commit subject line

## 2. Note what's missing (but don't add it yet)

The upgrade plan calls for two new fields in Step 6, when the database is introduced:
- `repo` — the name of the repository the commit came from (e.g. `"Arbiter"`)
- `ingested_at` — a timestamp for when the row was written to the DB

`short_hash` (the 7-char version) will stay **derived**, not stored — it's already handled in `standup/formatter.py` and will appear in API responses computed on the fly.

## 3. Confirm the dataclass is used everywhere it should be

Check that `standup/git.py` line 36 is the only place `Commit` objects are constructed. It is — `Commit(*line.split("|"))` unpacks 4 fields directly into the 4-field dataclass. This is the line you'll touch in Step 2 when switching the delimiter.

## 4. What you're not doing yet

- Do not add `repo` or `ingested_at`
- Do not add SQLAlchemy to this file
- Do not touch `git.py` yet

---

**Step 1 is done when:** you understand the shape of `Commit`, you know it needs two fields added later (in Step 6), and you haven't changed any code.

**Next:** [Step 2](step-2-git.md) is the first real code change — updating the `|` delimiter in `standup/git.py` to `\x1f` so commit messages containing pipes don't corrupt parsing.
