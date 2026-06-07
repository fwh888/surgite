import asyncio
import logging
import os
import subprocess
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError

import requests

from backend.config import INGEST_INTERVAL
from backend.db import get_session, CommitRow, RepoRow
from backend.formatter import format_log
from backend.git import get_raw_log, parse_log
from backend.models import Commit
from backend.schemas import IngestRequest, RepoCreate
from backend import summarizer
from backend.summarizer import ProviderError

log = logging.getLogger(__name__)

# Cap on commits sent to the LLM in /summary?ai=true to bound token cost.
AI_SUMMARY_MAX_COMMITS = 500


def _ingest_all_repos() -> list[dict]:
    """Ingest every registered repo. Returns list of per-repo result/error dicts."""
    from backend.git import is_remote_url, ensure_repo
    from backend.config import REPO_CACHE_DIR

    results: list[dict] = []
    with get_session() as session:
        repos = session.scalars(select(RepoRow)).all()
        repo_data = [(r.id, r.name, r.path, r.clone_url) for r in repos]

    for repo_id, repo_name, repo_path, clone_url in repo_data:
        try:
            result = _ingest_repo(repo_id, repo_name, repo_path, clone_url)
            results.append(result)
        except Exception as exc:
            log.warning("Ingest failed for repo %s: %s", repo_name, exc)
            results.append({"repo": repo_name, "error": str(exc)})

    return results


def _ingest_repo(
    repo_id: int,
    repo_name: str,
    repo_path: str,
    clone_url: str | None,
    since: date | None = None,
    until: date | None = None,
) -> dict:
    """Ingest commits for a single repo. Returns a result dict."""
    from backend.git import is_remote_url, ensure_repo
    from backend.config import REPO_CACHE_DIR

    if clone_url:
        actual_path = ensure_repo(repo_name, clone_url, REPO_CACHE_DIR)
    else:
        if not os.path.isdir(repo_path):
            raise RuntimeError(f"Repo path no longer exists on disk: {repo_path}")
        actual_path = repo_path

    since_str = (since or date.today() - timedelta(days=7)).isoformat()
    until_str = (until or date.today()).isoformat()

    raw = get_raw_log(actual_path, since_str, until_str)
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

        repo_row = session.get(RepoRow, repo_id)
        if repo_row:
            repo_row.last_ingested_at = datetime.now(timezone.utc)
        session.commit()

    return {"repo": repo_name, "inserted": inserted, "updated": updated, "unchanged": unchanged}


async def _auto_ingest_loop():
    """Background task that periodically ingests all repos."""
    while True:
        await asyncio.sleep(INGEST_INTERVAL)
        try:
            log.info("Auto-ingest: starting")
            await asyncio.to_thread(_ingest_all_repos)
            log.info("Auto-ingest: complete")
        except Exception:
            log.exception("Auto-ingest failed")


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(_auto_ingest_loop())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)

# Allow the Vite dev server (separate origin) to call the API during development.
# In production the frontend is served same-origin from the static mount below, so
# these origins simply go unused.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(SQLAlchemyError)
async def _sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
    return JSONResponse(status_code=503, content={"detail": "Database unavailable"})


def _repo_to_dict(row: RepoRow) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "path": row.path,
        "clone_url": row.clone_url,
        "remote": row.clone_url is not None,
        "added_at": row.added_at.isoformat() if row.added_at else None,
        "last_ingested_at": row.last_ingested_at.isoformat() if row.last_ingested_at else None,
    }


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


@app.get("/providers")
def providers():
    """List summary providers, their default model, and whether each is
    configured. A client (UI/CLI) can use this to let the user pick one."""
    return {"default": summarizer.default_provider(), "providers": summarizer.provider_status()}


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
    provider: str | None = None,
):
    total, commits = _query_commits(since, until, author, repo, limit=None, offset=0)

    by_repo: dict[str, int] = defaultdict(int)
    by_day: dict[str, int] = defaultdict(int)
    repo_commits: dict[str, list[Commit]] = {}
    for c in commits:
        repo_name = c["repo"]
        by_repo[repo_name] += 1
        by_day[c["date"]] += 1
        commit_obj = Commit(
            hash=c["hash"], date=c["date"], author=c["author"], message=c["message"]
        )
        repo_commits.setdefault(repo_name, []).append(commit_obj)

    log_by_repo = {name: format_log(cs) for name, cs in repo_commits.items()}

    ai_summary = None
    ai_provider = None
    ai_model = None
    ai_summaries = None
    if ai:
        if len(commits) > AI_SUMMARY_MAX_COMMITS:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Too many commits for AI summary "
                    f"({len(commits)} > {AI_SUMMARY_MAX_COMMITS}); narrow the date range."
                ),
            )
        ai_summaries = summarizer.generate_summary_per_repo(log_by_repo, provider=provider)
        # Backward-compat combined summary (first available repo, or all joined)
        all_commit_objs = [Commit(hash=c["hash"], date=c["date"], author=c["author"], message=c["message"]) for c in commits]
        try:
            result = summarizer.generate_summary(format_log(all_commit_objs), provider=provider)
        except ProviderError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except requests.RequestException as e:
            raise HTTPException(status_code=502, detail=f"Provider request failed: {e}")
        ai_summary = result["summary"]
        ai_provider = result["provider"]
        ai_model = result["model"]

    return {
        "period": {
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
        },
        "total_commits": total,
        "by_repo": dict(by_repo),
        "by_day": dict(sorted(by_day.items())),
        "commits": commits,
        "log_by_repo": log_by_repo,
        "ai_summary": ai_summary,
        "ai_provider": ai_provider,
        "ai_model": ai_model,
        "ai_summaries": ai_summaries,
    }


@app.get("/repos")
def list_repos():
    with get_session() as session:
        rows = session.scalars(select(RepoRow)).all()
        return {"repos": [_repo_to_dict(r) for r in rows]}


@app.post("/repos", status_code=201)
def create_repo(req: RepoCreate):
    from backend.git import is_remote_url, _repo_name_from_url

    if is_remote_url(req.path):
        clone_url = req.path
        name = _repo_name_from_url(clone_url)
    else:
        if not os.path.isdir(req.path):
            raise HTTPException(status_code=400, detail="path does not exist")
        clone_url = None
        name = os.path.basename(os.path.abspath(req.path))

    with get_session() as session:
        existing = session.scalar(select(RepoRow).where(RepoRow.path == req.path))
        if existing:
            raise HTTPException(status_code=409, detail="Repo already registered")
        repo = RepoRow(
            name=name,
            path=req.path,
            clone_url=clone_url,
            added_at=datetime.now(timezone.utc),
        )
        session.add(repo)
        session.commit()
        session.refresh(repo)
        return _repo_to_dict(repo)


@app.delete("/repos/{repo_id}", status_code=204)
def delete_repo(repo_id: int):
    with get_session() as session:
        repo = session.get(RepoRow, repo_id)
        if not repo:
            raise HTTPException(status_code=404, detail="Repo not found")
        session.delete(repo)
        session.commit()


@app.post("/repos/ingest-all")
def ingest_all():
    results = _ingest_all_repos()
    succeeded = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]
    return {"results": succeeded, "errors": failed}


@app.post("/repos/{repo_id}/ingest")
def ingest_repo_endpoint(
    repo_id: int,
    since: date | None = None,
    until: date | None = None,
):
    with get_session() as session:
        repo = session.get(RepoRow, repo_id)
        if not repo:
            raise HTTPException(status_code=404, detail="Repo not found")
        repo_id = repo.id
        repo_name = repo.name
        repo_path = repo.path
        clone_url = repo.clone_url

    try:
        result = _ingest_repo(repo_id, repo_name, repo_path, clone_url, since, until)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=f"Git error: {e}")
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to clone/fetch remote repo: {e.stderr.strip()}"
        )

    return result


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


# Serve the built SvelteKit SPA same-origin in production. Mounted LAST so it never
# shadows the API routes above, and only when the build exists (in dev the frontend
# runs on the Vite server instead, so this is skipped and startup doesn't fail).
_FRONTEND_BUILD = Path(__file__).resolve().parent.parent / "frontend" / "build"
if _FRONTEND_BUILD.is_dir():
    app.mount("/", StaticFiles(directory=_FRONTEND_BUILD, html=True), name="frontend")
