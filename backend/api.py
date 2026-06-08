import logging
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from backend import summarizer
from backend.db import CommitRow, PromptSettingsRow, RepoRow, get_session
from backend.formatter import format_log
from backend.git import get_raw_log, parse_log
from backend.models import Commit
from backend.schemas import PromptSettingsUpdate, RepoCreate
from backend.summarizer import ProviderError

log = logging.getLogger(__name__)

# Cap on commits sent to the LLM in /summary?ai=true to bound token cost.
AI_SUMMARY_MAX_COMMITS = 500


def _ingest_all_repos(since: date | None = None, until: date | None = None) -> list[dict]:
    """Ingest every registered repo. Returns list of per-repo result/error dicts."""
    results: list[dict] = []
    with get_session() as session:
        repos = session.scalars(select(RepoRow)).all()
        repo_data = [(r.id, r.name, r.clone_url) for r in repos]

    for repo_id, repo_name, clone_url in repo_data:
        try:
            result = _ingest_repo(repo_id, repo_name, clone_url, since, until)
            results.append(result)
        except Exception as exc:
            log.warning("Ingest failed for repo %s: %s", repo_name, exc)
            results.append({"repo": repo_name, "error": str(exc)})

    return results


def _ingest_repo(
    repo_id: int,
    repo_name: str,
    clone_url: str,
    since: date | None = None,
    until: date | None = None,
) -> dict:
    """Ingest commits for a single repo. Returns a result dict."""
    from backend.config import REPO_CACHE_DIR
    from backend.git import ensure_repo

    actual_path = ensure_repo(repo_name, clone_url, REPO_CACHE_DIR)

    since_str = (since or date.today() - timedelta(days=7)).isoformat()
    until_str = (until or date.today()).isoformat()

    raw = get_raw_log(actual_path, since_str, until_str)
    commits = parse_log(raw)
    inserted = updated = unchanged = 0

    with get_session() as session:
        for c in commits:
            existing = session.get(CommitRow, c.hash)
            if existing is None:
                session.add(
                    CommitRow(
                        hash=c.hash,
                        short_hash=c.hash[:7],
                        date=c.date,
                        author=c.author,
                        message=c.message,
                        repo=repo_name,
                        ingested_at=datetime.now(UTC),
                    )
                )
                inserted += 1
            elif existing.repo != repo_name:
                existing.repo = repo_name
                existing.ingested_at = datetime.now(UTC)
                updated += 1
            else:
                unchanged += 1

        repo_row = session.get(RepoRow, repo_id)
        if repo_row:
            repo_row.last_ingested_at = datetime.now(UTC)
        session.commit()

    return {"repo": repo_name, "inserted": inserted, "updated": updated, "unchanged": unchanged}


app = FastAPI()

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
        "clone_url": row.clone_url,
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


@app.get("/health")
def health():
    """Liveness + DB readiness, for monitoring and the container healthcheck.
    A failed DB connection raises SQLAlchemyError, mapped to 503 above."""
    with get_session() as session:
        session.execute(select(1))
    return {"status": "ok"}


@app.get("/providers")
def providers():
    """List summary providers, their default model, and whether each is
    configured. A client (UI/CLI) can use this to let the user pick one."""
    return {"default": summarizer.default_provider(), "providers": summarizer.provider_status()}


def _get_or_create_prompt_settings() -> PromptSettingsRow:
    with get_session() as session:
        row = session.get(PromptSettingsRow, 1)
        if row is None:
            row = PromptSettingsRow(id=1)
            session.add(row)
            session.commit()
            session.refresh(row)
        return row


def _settings_row_to_dict(row: PromptSettingsRow) -> dict:
    return {
        "user_name": row.user_name,
        "user_role": row.user_role,
        "tone": row.tone,
        "group_count": row.group_count,
        "output_format": row.output_format,
        "custom_instructions": row.custom_instructions,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@app.get("/settings/prompt")
def get_prompt_settings():
    row = _get_or_create_prompt_settings()
    return _settings_row_to_dict(row)


@app.put("/settings/prompt")
def update_prompt_settings(update: PromptSettingsUpdate):
    with get_session() as session:
        row = session.get(PromptSettingsRow, 1)
        if row is None:
            row = PromptSettingsRow(id=1)
            session.add(row)

        update_data = update.model_dump(exclude_none=True)
        for field, value in update_data.items():
            setattr(row, field, value)

        row.updated_at = datetime.now(UTC)
        session.commit()
        session.refresh(row)
        return _settings_row_to_dict(row)


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
    _ingest_all_repos(since, until)
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
        settings_row = _get_or_create_prompt_settings()
        settings = _settings_row_to_dict(settings_row)
        ai_summaries = summarizer.generate_summary_per_repo(
            log_by_repo, provider=provider, settings=settings
        )
        all_commit_objs = [
            Commit(hash=c["hash"], date=c["date"], author=c["author"], message=c["message"])
            for c in commits
        ]
        try:
            result = summarizer.generate_summary(
                format_log(all_commit_objs), provider=provider, settings=settings
            )
        except ProviderError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except requests.RequestException as e:
            raise HTTPException(status_code=502, detail=f"Provider request failed: {e}") from e
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
    from backend.git import _repo_name_from_url, is_remote_url

    if not is_remote_url(req.url):
        raise HTTPException(
            status_code=400,
            detail="Must be a remote git URL (https://, git@, git:// or ssh://)",
        )
    name = _repo_name_from_url(req.url)

    with get_session() as session:
        existing = session.scalar(select(RepoRow).where(RepoRow.clone_url == req.url))
        if existing:
            raise HTTPException(status_code=409, detail="Repo already registered")
        repo = RepoRow(
            name=name,
            clone_url=req.url,
            added_at=datetime.now(UTC),
        )
        session.add(repo)
        session.commit()
        session.refresh(repo)
        repo_id = repo.id

    try:
        _ingest_repo(repo_id, name, req.url)
    except Exception as exc:
        log.warning("Initial ingest failed for %s: %s", name, exc)

    with get_session() as session:
        repo = session.get(RepoRow, repo_id)
        return _repo_to_dict(repo)


@app.delete("/repos/{repo_id}", status_code=204)
def delete_repo(repo_id: int):
    with get_session() as session:
        repo = session.get(RepoRow, repo_id)
        if not repo:
            raise HTTPException(status_code=404, detail="Repo not found")
        session.delete(repo)
        session.commit()


# Serve the built SvelteKit SPA same-origin in production. Mounted LAST so it never
# shadows the API routes above, and only when the build exists (in dev the frontend
# runs on the Vite server instead, so this is skipped and startup doesn't fail).
_FRONTEND_BUILD = Path(__file__).resolve().parent.parent / "frontend" / "build"
if _FRONTEND_BUILD.is_dir():
    app.mount("/", StaticFiles(directory=_FRONTEND_BUILD, html=True), name="frontend")
