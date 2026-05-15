# Step 7: Create `api.py`

**The instruction:** Implement routes in this order: `GET /commits`, then `GET /commits/{hash}`, then `POST /ingest`, then `GET /summary`. Add `fastapi` and `uvicorn` to `pyproject.toml`.

## 1. Add dependencies

In `pyproject.toml`:

```toml
dependencies = [
    "groq>=1.2.0",
    "python-dotenv>=1.2.2",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "fastapi>=0.115",
    "uvicorn>=0.30",
]
```

```bash
uv sync
```

## 2. Build `api.py` one route at a time

Create `standup/api.py`. Add routes in the order below — start the server after each one and test it before moving to the next.

### Skeleton

```python
from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import select, func
from standup.db import get_session, CommitRow
from standup.git import get_raw_log, parse_log
from standup.summarizer import summarize_commits
from standup.config import GROQ_API_KEY
from datetime import date, datetime, timezone, timedelta

app = FastAPI()
```

### Route 1: `GET /commits`

```python
@app.get("/commits")
def list_commits(
    since: date | None = None,
    until: date | None = None,
    author: str | None = None,
    repo: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    with get_session() as session:
        q = select(CommitRow)
        if since:
            q = q.where(CommitRow.date >= since.isoformat())
        if until:
            q = q.where(CommitRow.date <= until.isoformat())
        if author:
            q = q.where(CommitRow.author.ilike(f"%{author}%"))
        if repo:
            q = q.where(CommitRow.repo == repo)

        total = session.scalar(select(func.count()).select_from(q.subquery()))
        rows = session.scalars(q.order_by(CommitRow.date.desc()).limit(limit).offset(offset)).all()

    return {
        "total": total,
        "commits": [_row_to_dict(r) for r in rows],
    }
```

### Route 2: `GET /commits/{hash}`

```python
@app.get("/commits/{hash}")
def get_commit(hash: str):
    if len(hash) < 7:
        raise HTTPException(status_code=400, detail="Hash prefix must be at least 7 characters")

    with get_session() as session:
        if len(hash) == 40:
            row = session.get(CommitRow, hash)
            if not row:
                raise HTTPException(status_code=404, detail="Commit not found")
            return _row_to_dict(row)

        rows = session.scalars(
            select(CommitRow).where(CommitRow.hash.startswith(hash))
        ).all()

        if not rows:
            raise HTTPException(status_code=404, detail="Commit not found")
        if len(rows) > 1:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Prefix matches multiple commits",
                    "candidates": [r.hash for r in rows],
                },
            )
        return _row_to_dict(rows[0])
```

### Route 3: `POST /ingest`

```python
from pydantic import BaseModel
import os

class IngestRequest(BaseModel):
    repo_path: str
    since: str | None = None
    until: str | None = None

@app.post("/ingest")
def ingest(req: IngestRequest):
    if not os.path.isdir(req.repo_path):
        raise HTTPException(status_code=400, detail="repo_path does not exist")

    since = req.since or (date.today() - timedelta(days=7)).isoformat()
    until = req.until or date.today().isoformat()
    repo_name = os.path.basename(req.repo_path.rstrip("/"))

    try:
        raw = get_raw_log(req.repo_path, since, until)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=f"Not a git repo or git error: {e}")

    commits = parse_log(raw)
    inserted = updated = unchanged = 0

    with get_session() as session:
        for c in commits:
            existing = session.get(CommitRow, c.hash)
            if existing is None:
                session.add(CommitRow(
                    hash=c.hash,
                    short_hash=c.hash[:7],
                    date=c.date,
                    author=c.author,
                    message=c.message,
                    repo=repo_name,
                    ingested_at=datetime.now(timezone.utc),
                ))
                inserted += 1
            elif (existing.author, existing.message, existing.date) != (c.author, c.message, c.date):
                existing.author = c.author
                existing.message = c.message
                existing.date = c.date
                existing.ingested_at = datetime.now(timezone.utc)
                updated += 1
            else:
                unchanged += 1
        session.commit()

    return {"repo": repo_name, "inserted": inserted, "updated": updated, "unchanged": unchanged}
```

### Route 4: `GET /summary`

```python
from collections import defaultdict

@app.get("/summary")
def summary(
    since: date | None = None,
    until: date | None = None,
    author: str | None = None,
    repo: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    ai: bool = False,
):
    result = list_commits(since=since, until=until, author=author, repo=repo, limit=limit, offset=offset)
    commits = result["commits"]

    by_repo: dict[str, int] = defaultdict(int)
    by_day: dict[str, int] = defaultdict(int)
    for c in commits:
        by_repo[c["repo"]] += 1
        by_day[c["date"]] += 1

    ai_summary = None
    if ai:
        if not GROQ_API_KEY:
            raise HTTPException(status_code=400, detail="GROQ_API_KEY is not set")
        from standup.formatter import format_log
        from standup.models import Commit
        commit_objs = [Commit(hash=c["hash"], date=c["date"], author=c["author"], message=c["message"]) for c in commits]
        formatted = format_log(commit_objs)
        ai_summary = summarize_commits(formatted)

    return {
        "period": {
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
        },
        "total_commits": result["total"],
        "by_repo": dict(by_repo),
        "by_day": dict(sorted(by_day.items())),
        "commits": commits,
        "ai_summary": ai_summary,
    }
```

### Helper function (add near the top, after imports)

```python
def _row_to_dict(row: CommitRow) -> dict:
    return {
        "hash": row.hash,
        "short_hash": row.short_hash,
        "date": row.date,
        "author": row.author,
        "message": row.message,
        "repo": row.repo,
        "ingested_at": row.ingested_at.isoformat() if row.ingested_at else None,
    }
```

## 3. Start the server and test each route

```bash
uv run uvicorn standup.api:app --reload --host 127.0.0.1 --port 8000
```

FastAPI generates interactive docs at `http://127.0.0.1:8000/docs` — use it to test every route without writing curl commands.

Basic smoke tests:

```bash
# Ingest a repo
curl -s -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"repo_path": "/path/to/your/repo", "since": "2026-05-01"}' | python3 -m json.tool

# List commits
curl -s "http://localhost:8000/commits?since=2026-05-01" | python3 -m json.tool

# Get a single commit (use a real hash from the previous response)
curl -s "http://localhost:8000/commits/a1b2c3d" | python3 -m json.tool

# Summary
curl -s "http://localhost:8000/summary?since=2026-05-01" | python3 -m json.tool
```

## Note on `get_session()`

For `get_session()` to work as a context manager (the `with get_session() as session:` pattern above), update `db.py` to return a `Session` via `sessionmaker` or use SQLAlchemy's built-in context manager. The simplest approach:

```python
from sqlalchemy.orm import sessionmaker

SessionLocal = sessionmaker(bind=engine)

def get_session():
    return SessionLocal()
```

Then use it as:
```python
with get_session() as session:
    ...
```

SQLAlchemy's `Session` supports the context manager protocol natively — it commits on exit and rolls back on exception.

---

**Step 7 is done when:** all four routes return correct responses and the interactive docs at `/docs` work.

**Next:** [Step 8](step-8-ingest-flag.md) — add `--ingest <url>` to the CLI so it can POST to the API instead of printing.
