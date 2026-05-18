from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import select, func
from standup.db import get_session, CommitRow
from standup.git import get_raw_log, parse_log
from standup.summarizer import summarize_commits
from standup.config import GROQ_API_KEY
from datetime import date, datetime, timezone, timedelta

# FastAPI instance 

app = FastAPI()

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


@app.get("/commits")
def list_commits(
    since: date | None = None,
    until: date | None = None,
    author: str | None = None,
    repo: str | None = None,
    limit: int = Query(50, ge=1, le=500), # Limit the number of commits returned
    offset: int = Query(0, ge=0), # Offset for pagination
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

        total = session.scalar(select(func.count()).select_from(q.subquery())) # Get total count for pagination
        rows = session.scalars(q.order_by(CommitRow.date.desc()).limit(limit).offset(offset)).all() # Apply ordering, limit, and offset for pagination

    return {
        "total": total,
        "commits": [_row_to_dict(r) for r in rows],
    }