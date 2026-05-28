import os
from collections import defaultdict
from datetime import date, datetime, timezone, timedelta

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError

from standup.db import get_session, CommitRow
from standup.formatter import format_log
from standup.git import get_raw_log, parse_log
from standup.models import Commit
from standup.schemas import IngestRequest
from standup.summarizer import summarize_commits
from standup.config import GROQ_API_KEY

# Cap on commits sent to the LLM in /summary?ai=true to bound token cost.
AI_SUMMARY_MAX_COMMITS = 500

app = FastAPI()


@app.exception_handler(SQLAlchemyError)
async def _sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
    return JSONResponse(status_code=503, content={"detail": "Database unavailable"})


def _row_to_dict(row: CommitRow) -> dict:
    """Convert a CommitRow to a dictionary."""
    return {
        "hash": row.hash,
        "short_hash": row.short_hash,
        "date": row.date,
        "author": row.author,
        "message": row.message,
        "repo": row.repo,
        "ingested_at": row.ingested_at.isoformat() if row.ingested_at else None,
    }


def _query_commits(
    since: date | None,
    until: date | None,
    author: str | None,
    repo: str | None,
    limit: int | None,
    offset: int,
) -> tuple[int, list[dict]]:
    """Run the filtered commits query. limit=None returns all matching rows."""
    with get_session() as session:
        q = select(CommitRow)
        if since:
            q = q.where(CommitRow.date >= since.isoformat())
        if until:
            q = q.where(CommitRow.date <= until.isoformat())
        if author:
            q = q.where(CommitRow.author.ilike(f"%{author}%"))
        if repo:
            q = q.where(CommitRow.repo.ilike(f"%{repo}%"))

        total = session.scalar(select(func.count()).select_from(q.subquery())) or 0
        q = q.order_by(CommitRow.date.desc()).offset(offset)
        if limit is not None:
            q = q.limit(limit)
        rows = session.scalars(q).all()
        return total, [_row_to_dict(r) for r in rows]


@app.get("/commits")
def list_commits(
    since: date | None = None,
    until: date | None = None,
    author: str | None = None,
    repo: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    total, commits = _query_commits(since, until, author, repo, limit, offset)
    return {"total": total, "commits": commits}


def _looks_like_hash(value: str) -> bool:
    return len(value) >= 7 and all(c in "0123456789abcdef" for c in value.lower())


@app.get("/commits/{hash}")
def get_commit(hash: str):
    if not _looks_like_hash(hash):
        raise HTTPException(
            status_code=400,
            detail="Hash must be hex and at least 7 characters",
        )

    with get_session() as session:
        rows = session.scalars(
            select(CommitRow).where(CommitRow.hash.startswith(hash.lower()))
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


@app.get("/summary")
def summary(
    since: date | None = None,
    until: date | None = None,
    author: str | None = None,
    repo: str | None = None,
    ai: bool = False,
):
    total, commits = _query_commits(since, until, author, repo, limit=None, offset=0)

    by_repo: dict[str, int] = defaultdict(int)
    by_day: dict[str, int] = defaultdict(int)
    for c in commits:
        by_repo[c["repo"]] += 1
        by_day[c["date"]] += 1

    ai_summary = None
    if ai:
        if not GROQ_API_KEY:
            raise HTTPException(status_code=400, detail="GROQ_API_KEY is not set")
        if len(commits) > AI_SUMMARY_MAX_COMMITS:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Too many commits for AI summary "
                    f"({len(commits)} > {AI_SUMMARY_MAX_COMMITS}); narrow the date range."
                ),
            )
        commit_objs = [
            Commit(hash=c["hash"], date=c["date"], author=c["author"], message=c["message"])
            for c in commits
        ]
        ai_summary = summarize_commits(format_log(commit_objs))

    return {
        "period": {
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
        },
        "total_commits": total,
        "by_repo": dict(by_repo),
        "by_day": dict(sorted(by_day.items())),
        "commits": commits,
        "ai_summary": ai_summary,
    }


@app.post("/ingest")
def ingest(req: IngestRequest):
    if not os.path.isdir(req.repo_path):
        raise HTTPException(status_code=400, detail="repo_path does not exist")

    since = (req.since or date.today() - timedelta(days=7)).isoformat()
    until = (req.until or date.today()).isoformat()
    repo_name = os.path.basename(os.path.abspath(req.repo_path))

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
            elif existing.repo != repo_name:
                existing.repo = repo_name
                existing.ingested_at = datetime.now(timezone.utc)
                updated += 1
            else:
                unchanged += 1
        session.commit()

    return {"repo": repo_name, "inserted": inserted, "updated": updated, "unchanged": unchanged}
