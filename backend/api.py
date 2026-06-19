import asyncio
import json
import logging
import os
import secrets
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend import config, summarizer
from backend.auth import (
    clear_session_cookie,
    create_session,
    create_user,
    ensure_bootstrap_invite,
    get_current_user,
    get_optional_user,
    normalize_email,
    purge_expired_sessions,
    revoke_session,
    set_session_cookie,
    verify_password,
)
from backend.config import SHARE_TTL_DAYS
from backend.db import (
    CommitRow,
    InviteRow,
    PromptSettingsRow,
    RepoRow,
    SharedSummaryRow,
    UserRow,
    get_db,
    session_scope,
)
from backend.formatter import format_log
from backend.git import get_raw_log, ls_remote, parse_log
from backend.logging_config import configure_logging
from backend.models import Commit
from backend.rate_limit import check_rate_limit
from backend.schemas import (
    LoginRequest,
    PromptSettingsUpdate,
    RedeemInviteRequest,
    RepoCreate,
    ShareCreate,
)
from backend.summarizer import ProviderError

configure_logging()
log = logging.getLogger(__name__)

# Cap on commits sent to the LLM in /summary?ai=true to bound token cost.
AI_SUMMARY_MAX_COMMITS = 500


def _ingest_all_repos() -> list[dict]:
    """Ingest every registered repo. The background scheduler calls this on
    a timer (see `_scheduler_loop`); the /summary endpoint itself stays a
    pure read against the DB. The per-repo ingest (`_ingest_repo`) is still
    wired up as a FastAPI BackgroundTask on `POST /repos` so newly added
    repos show up immediately rather than waiting up to INGEST_INTERVAL
    seconds. Returns list of per-repo result/error dicts."""
    results: list[dict] = []
    with session_scope() as s:
        repo_data = [
            (r.id, r.name, r.clone_url, r.owner_id) for r in s.scalars(select(RepoRow)).all()
        ]

    for repo_id, repo_name, clone_url, owner_id in repo_data:
        try:
            results.append(_ingest_repo(repo_id, repo_name, clone_url, owner_id))
        except Exception as exc:
            log.warning("Ingest failed for repo %s: %s", repo_name, exc, extra={"repo": repo_name})
            results.append({"repo": repo_name, "error": str(exc)})

    return results


def _ingest_repo(
    repo_id: int,
    repo_name: str,
    clone_url: str,
    owner_id: str,
    since: date | None = None,
    until: date | None = None,
    session: Session | None = None,
) -> dict:
    """Ingest commits for a single repo. Commits inherit the repo's owner.
    Returns a result dict."""
    from backend.config import REPO_CACHE_DIR
    from backend.git import ensure_repo

    actual_path = ensure_repo(repo_name, clone_url, REPO_CACHE_DIR)

    since_str = (since or date.today() - timedelta(days=7)).isoformat()
    until_str = (until or date.today()).isoformat()

    raw = get_raw_log(actual_path, since_str, until_str)
    commits = parse_log(raw)
    inserted = updated = unchanged = 0

    with session_scope(session) as s:
        existing: dict[str, CommitRow] = {}
        if commits:
            existing = {
                row.hash: row
                for row in s.scalars(
                    select(CommitRow).where(CommitRow.hash.in_([c.hash for c in commits]))
                )
            }
        now = datetime.now(UTC)
        for c in commits:
            row = existing.get(c.hash)
            if row is None:
                s.add(
                    CommitRow(
                        hash=c.hash,
                        short_hash=c.hash[:7],
                        date=c.date,
                        author=c.author,
                        message=c.message,
                        repo=repo_name,
                        repo_id=repo_id,
                        owner_id=owner_id,
                        ingested_at=now,
                    )
                )
                inserted += 1
            elif row.repo_id != repo_id:
                row.repo_id = repo_id
                row.repo = repo_name
                row.ingested_at = now
                updated += 1
            else:
                unchanged += 1

        repo_row = s.get(RepoRow, repo_id)
        if repo_row:
            repo_row.last_ingested_at = now
        s.commit()

    return {"repo": repo_name, "inserted": inserted, "updated": updated, "unchanged": unchanged}


def _delete_expired_summaries() -> int:
    """Sweep shared-summary slugs past their expiry. Read-path also rejects
    expired slugs, so this is just housekeeping to keep the table small.
    Returns the number of rows deleted."""
    now = datetime.now(UTC)
    with session_scope() as s:
        rows = s.scalars(select(SharedSummaryRow).where(SharedSummaryRow.expires_at <= now)).all()
        for row in rows:
            s.delete(row)
        s.commit()
        return len(rows)


def _scheduler_tick() -> None:
    """One pass of the background work: ingest every repo, prune expired share
    slugs, and purge expired sessions. Runs in a thread (sync DB + git) off
    the event loop."""
    _ingest_all_repos()
    _delete_expired_summaries()
    purge_expired_sessions()


async def _scheduler_loop(interval: int) -> None:
    """Background task: every `interval` seconds, ingest all registered repos
    and prune expired share slugs.

    Runs `_scheduler_tick` in a thread (it's sync, talks to git + DB) so
    the event loop stays responsive. Any exception is logged and the loop
    continues — a transient git failure must not stop the scheduler. Stops
    cleanly when the task is cancelled at app shutdown."""
    log.info("Background ingest scheduler started (interval=%ds)", interval)
    loop = asyncio.get_running_loop()
    try:
        while True:
            try:
                await loop.run_in_executor(None, _scheduler_tick)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Defence in depth: _ingest_all_repos already swallows per-repo
                # failures, so anything reaching here is unexpected.
                log.exception("Background ingest loop failed: %s", exc)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        log.info("Background ingest scheduler stopped")
        raise


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Start the background ingest scheduler on app startup, cancel it on
    shutdown. Disabled (interval<=0) for tests and one-off CLI runs where
    a background task would never be observed.

    INGEST_INTERVAL is read fresh from the environment on every startup so
    tests can flip it without reloading the config module."""
    if config.AUTH_MODE == "multi_user":
        with session_scope() as s:
            token = ensure_bootstrap_invite(s)
        if token:
            log.warning(
                "No admin account exists. Bootstrap an admin by redeeming this "
                "invite for %s:  standup --redeem-invite %s",
                config.BOOTSTRAP_OWNER_EMAIL,
                token,
            )

    interval = int(os.environ.get("INGEST_INTERVAL", "300"))
    task: asyncio.Task | None = None
    if interval > 0:
        task = asyncio.create_task(_scheduler_loop(interval))
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(lifespan=_lifespan)

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


def _escape_like(s: str) -> str:
    """Escape SQL LIKE wildcards so user input is treated literally."""
    return s.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def _repo_to_dict(row: RepoRow) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "clone_url": row.clone_url,
        "added_at": row.added_at.isoformat() if row.added_at else None,
        "last_ingested_at": row.last_ingested_at.isoformat() if row.last_ingested_at else None,
    }


def _owned_repo(session: Session, repo_id: int, owner_id: str) -> RepoRow | None:
    """Fetch a repo by id only if `owner_id` owns it. Returns None otherwise,
    so callers turn cross-owner access into a 404."""
    repo = session.get(RepoRow, repo_id)
    return repo if repo is not None and repo.owner_id == owner_id else None


def _row_to_dict(row: CommitRow) -> dict:
    """Convert a CommitRow to a dictionary."""
    return {
        "hash": row.hash,
        "short_hash": row.short_hash,
        "date": row.date.isoformat(),
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
    owner_id: str,
    session: Session | None = None,
) -> tuple[int, list[dict]]:
    """Run the filtered commits query, scoped to `owner_id`. limit=None returns
    all matching rows."""
    with session_scope(session) as s:
        q = select(CommitRow).where(CommitRow.owner_id == owner_id)
        if since:
            q = q.where(CommitRow.date >= since)
        if until:
            q = q.where(CommitRow.date <= until)
        if author:
            q = q.where(CommitRow.author.ilike(f"%{_escape_like(author)}%", escape="\\"))
        if repo:
            repo_row = s.scalar(
                select(RepoRow).where(RepoRow.name == repo, RepoRow.owner_id == owner_id)
            )
            if repo_row is None:
                return 0, []
            q = q.where(CommitRow.repo_id == repo_row.id)

        total = s.scalar(select(func.count()).select_from(q.subquery())) or 0
        q = q.order_by(CommitRow.date.desc()).offset(offset)
        if limit is not None:
            q = q.limit(limit)
        rows = s.scalars(q).all()
        return total, [_row_to_dict(r) for r in rows]


@app.get("/health")
def health(session: Session = Depends(get_db)):
    """Liveness + DB readiness, for monitoring and the container healthcheck.
    A failed DB connection raises SQLAlchemyError, mapped to 503 above."""
    session.execute(select(1))
    return {"status": "ok"}


async def _check_providers() -> dict[str, str]:
    """Per-provider reachability: missing_key (no key, not a failure), ok (key
    set + host answered), or unreachable (key set but the network call failed).
    Reachability only — we don't spend a token validating the key."""
    out: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=5) as client:
        for name, provider in summarizer.PROVIDERS.items():
            if provider.api_key is None:
                out[name] = "missing_key"
                continue
            try:
                await client.get(provider.base_url)
                out[name] = "ok"
            except httpx.HTTPError:
                out[name] = "unreachable"
    return out


@app.get("/health/deep")
async def health_deep(
    session: Session = Depends(get_db),
    user: UserRow | None = Depends(get_optional_user),
):
    """Deep health for a real uptime check: DB connectivity, a remote-reachable
    probe against one registered repo, and provider-key reachability. Returns
    503 if any *checked* component is down (no_repos / missing_key are not
    failures), else 200.

    The git probe is scoped to a repo the *caller* owns and the response never
    names a specific repo, so an exposed multi_user deployment can't be used to
    enumerate other users' repos via /health/deep (issue #64). An anonymous
    caller in multi_user mode gets `git: no_repos` — the probe is skipped
    rather than run against an arbitrary user's repo."""
    components: dict[str, object] = {}
    healthy = True

    try:
        session.execute(select(1))
        components["db"] = "ok"
    except SQLAlchemyError:
        components["db"] = "error"
        healthy = False

    repo = None
    if user is not None:
        repo = session.scalar(
            select(RepoRow).where(RepoRow.owner_id == user.id).limit(1)
        )
    if repo is None:
        components["git"] = "no_repos"
    else:
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, ls_remote, repo.clone_url)
            components["git"] = "ok"
        except Exception as exc:
            log.warning("Deep health git probe failed: %s", exc, extra={"repo": repo.name})
            components["git"] = "error"
            healthy = False

    providers = await _check_providers()
    components["providers"] = providers
    if any(state == "unreachable" for state in providers.values()):
        healthy = False

    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "degraded", "components": components},
    )


@app.get("/providers")
def providers(current_user: UserRow = Depends(get_current_user)):
    """List summary providers, their default model, and whether each is
    configured. A client (UI/CLI) can use this to let the user pick one.

    In multi_user mode this is admin-only: provider-key presence is an
    information-disclosure surface on an exposed deployment, and per-user
    provider keys arrive in slice 2, so a non-admin has no business reading
    the global status (issue #65). In off/single_user mode it's open as
    before."""
    if config.AUTH_MODE == "multi_user" and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return {"default": summarizer.default_provider(), "providers": summarizer.provider_status()}


# --- Auth (multi_user only) -------------------------------------------------
# The login/logout/redeem flow only exists in multi_user mode. In off and
# single_user mode there's no login concept, so these routes 404 — the auth
# machinery is still exercised by single_user (sessions, hashing) but the user
# never reaches these handlers.


def _require_multi_user() -> None:
    if config.AUTH_MODE != "multi_user":
        raise HTTPException(status_code=404, detail="Not found")


def _user_to_dict(user: UserRow) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "is_admin": user.is_admin,
    }


@app.post("/auth/login")
def auth_login(
    req: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
):
    """Verify credentials, open a session, set the hardened cookie. A bad email
    or password is an indistinguishable 401 (no account enumeration)."""
    _require_multi_user()
    user = session.scalar(select(UserRow).where(UserRow.email == normalize_email(req.email)))
    if (
        user is None
        or not user.is_active
        or user.password_hash is None
        or not verify_password(req.password, user.password_hash)
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    sess = create_session(
        user.id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        session=session,
    )
    set_session_cookie(response, sess.id)
    user.last_login_at = datetime.now(UTC)
    session.commit()
    return _user_to_dict(user)


@app.post("/auth/logout")
def auth_logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
):
    """Revoke the current session and clear the cookie. Idempotent — logging
    out without a session is still a 200."""
    _require_multi_user()
    sid = request.cookies.get(config.SESSION_COOKIE_NAME)
    if sid:
        revoke_session(sid, session=session)
    clear_session_cookie(response)
    return {"status": "logged out"}


@app.post("/auth/redeem-invite", status_code=201)
def auth_redeem_invite(
    req: RedeemInviteRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
):
    """Claim a single-use invite: create the account, set its password, mark
    the invite used, and log the new user straight in (sets the session
    cookie). This is the no-auth bootstrap path the CLI drives."""
    _require_multi_user()
    invite = session.scalar(select(InviteRow).where(InviteRow.token == req.token))
    now = datetime.now(UTC)
    if invite is None or invite.used_at is not None or _as_utc(invite.expires_at) <= now:
        raise HTTPException(status_code=400, detail="Invalid or expired invite")

    email = invite.email or (normalize_email(req.email) if req.email else None)
    if not email:
        raise HTTPException(status_code=400, detail="This invite requires an email")
    if session.scalar(select(UserRow).where(UserRow.email == normalize_email(email))):
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = create_user(
        session,
        email=email,
        password=req.password,
        display_name=req.display_name or "",
        is_admin=(invite.role == "admin"),
    )
    invite.used_at = now
    invite.used_by = user.id
    sess = create_session(
        user.id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        session=session,
    )
    user.last_login_at = now
    session.commit()
    set_session_cookie(response, sess.id)
    return _user_to_dict(user)


@app.get("/auth/me")
def auth_me(current_user: UserRow = Depends(get_current_user)):
    """The current user, for the SPA's 'logged in as' indicator and to let the
    CLI verify a stored session is still valid."""
    return _user_to_dict(current_user)


def _get_prompt_setting(
    session: Session, repo_id: int | None, owner_id: str
) -> PromptSettingsRow | None:
    """The settings row for `owner_id` scoped to `repo_id` (or the owner's
    global row for None). No fallback — returns None when this exact scope has
    no row yet."""
    return session.scalar(
        select(PromptSettingsRow).where(
            PromptSettingsRow.repo_id == repo_id,
            PromptSettingsRow.owner_id == owner_id,
        )
    )


def _get_or_create_prompt_setting(
    owner_id: str, session: Session | None = None, repo_id: int | None = None
) -> PromptSettingsRow:
    with session_scope(session) as s:
        row = _get_prompt_setting(s, repo_id, owner_id)
        if row is None:
            row = PromptSettingsRow(repo_id=repo_id, owner_id=owner_id)
            s.add(row)
            s.commit()
            s.refresh(row)
        return row


def _resolve_settings_dict(session: Session, repo_id: int | None, owner_id: str) -> dict:
    """Settings that apply to `repo_id` for `owner_id`: its own row if it has
    one, else the owner's global default. This is the lookup the summarizer
    uses per repo."""
    row = _get_prompt_setting(session, repo_id, owner_id) if repo_id is not None else None
    if row is None:
        row = _get_or_create_prompt_setting(owner_id, session, repo_id=None)
    return _settings_row_to_dict(row)


def _settings_row_to_dict(row: PromptSettingsRow) -> dict:
    return {
        "repo_id": row.repo_id,
        "user_name": row.user_name,
        "user_role": row.user_role,
        "tone": row.tone,
        "group_count": row.group_count,
        "output_format": row.output_format,
        "custom_instructions": row.custom_instructions,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@app.get("/settings/prompt")
def get_prompt_settings(
    repo_id: int | None = None,
    session: Session = Depends(get_db),
    current_user: UserRow = Depends(get_current_user),
):
    """Return the prompt settings for `repo_id`. If that repo has no row of its
    own, return the global default (its `repo_id` will be null, signalling the
    UI that the values are inherited rather than repo-specific)."""
    row = _get_prompt_setting(session, repo_id, current_user.id) if repo_id is not None else None
    if row is None:
        row = _get_or_create_prompt_setting(current_user.id, session, repo_id=None)
    return _settings_row_to_dict(row)


@app.put("/settings/prompt")
def update_prompt_settings(
    update: PromptSettingsUpdate,
    repo_id: int | None = None,
    session: Session = Depends(get_db),
    current_user: UserRow = Depends(get_current_user),
):
    if repo_id is not None and _owned_repo(session, repo_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="Repo not found")

    row = _get_prompt_setting(session, repo_id, current_user.id)
    if row is None:
        row = PromptSettingsRow(repo_id=repo_id, owner_id=current_user.id)
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
    session: Session = Depends(get_db),
    current_user: UserRow = Depends(get_current_user),
):
    total, commits = _query_commits(
        since, until, author, repo, limit, offset, current_user.id, session=session
    )
    return {"total": total, "commits": commits}


def _looks_like_hash(value: str) -> bool:
    return len(value) >= 7 and all(c in "0123456789abcdef" for c in value.lower())


@app.get("/commits/{hash}")
def get_commit(
    hash: str,
    session: Session = Depends(get_db),
    current_user: UserRow = Depends(get_current_user),
):
    if not _looks_like_hash(hash):
        raise HTTPException(
            status_code=400,
            detail="Hash must be hex and at least 7 characters",
        )

    rows = session.scalars(
        select(CommitRow).where(
            CommitRow.hash.startswith(hash.lower()),
            CommitRow.owner_id == current_user.id,
        )
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


def _aggregate_commits(
    commits: list[dict],
) -> tuple[dict[str, int], dict[str, int], dict[str, list[Commit]]]:
    """Roll a list of commit dicts up into the per-repo and per-day counts the
    summary view needs, plus the Commit objects grouped by repo for the log."""
    by_repo: dict[str, int] = defaultdict(int)
    by_day: dict[str, int] = defaultdict(int)
    repo_commits: dict[str, list[Commit]] = {}
    for c in commits:
        repo_name = c["repo"]
        by_repo[repo_name] += 1
        by_day[c["date"]] += 1
        repo_commits.setdefault(repo_name, []).append(
            Commit(hash=c["hash"], date=c["date"], author=c["author"], message=c["message"])
        )
    return by_repo, by_day, repo_commits


def _repo_name_to_id(session: Session, owner_id: str) -> dict[str, int]:
    return {
        r.name: r.id
        for r in session.scalars(select(RepoRow).where(RepoRow.owner_id == owner_id)).all()
    }


def _check_ai_preconditions(request: Request, provider: str | None, total: int):
    """Shared gate for the AI paths: rate limit, commit cap, provider/key
    validity. Raises the appropriate HTTPException; returns the resolved
    provider on success."""
    check_rate_limit(request)
    if total > AI_SUMMARY_MAX_COMMITS:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Too many commits for AI summary "
                f"({total} > {AI_SUMMARY_MAX_COMMITS}); narrow the date range."
            ),
        )
    try:
        resolved = summarizer.resolve_provider(provider)
    except ProviderError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if resolved.api_key is None:
        raise HTTPException(status_code=400, detail=f"{resolved.key_env} is not set")
    return resolved


@app.get("/summary")
async def summary(
    request: Request,
    since: date | None = None,
    until: date | None = None,
    author: str | None = None,
    repo: str | None = None,
    ai: bool = False,
    provider: str | None = None,
    combined: bool = False,
    commits: bool = False,
    session: Session = Depends(get_db),
    current_user: UserRow = Depends(get_current_user),
):
    """Commit summary for the period. With ai=true, returns one AI summary per
    repo (ai_summaries); the additional whole-log summary (ai_summary) costs an
    extra provider call and is only generated when combined=true.

    The raw `commits` list is omitted by default (it can be hundreds of KB the
    web UI never renders); pass commits=true to include it, or use /commits.

    This is a pure read against the DB; freshness is owned by the background
    ingest scheduler (see _scheduler_loop) and the per-repo BackgroundTask
    on POST /repos. No git fetch happens here."""
    total, commit_rows = _query_commits(
        since, until, author, repo, limit=None, offset=0, owner_id=current_user.id, session=session
    )
    by_repo, by_day, repo_commits = _aggregate_commits(commit_rows)
    log_by_repo = {name: format_log(cs) for name, cs in repo_commits.items()}

    ai_summary = None
    ai_provider = None
    ai_model = None
    ai_summaries = None
    if ai:
        _check_ai_preconditions(request, provider, total)
        name_to_id = _repo_name_to_id(session, current_user.id)
        global_settings = _resolve_settings_dict(session, None, current_user.id)
        settings_by_repo = {
            name: _resolve_settings_dict(session, name_to_id.get(name), current_user.id)
            for name in log_by_repo
        }
        ai_summaries = await summarizer.generate_summary_per_repo(
            log_by_repo,
            provider=provider,
            settings=global_settings,
            settings_by_repo=settings_by_repo,
        )
        if combined:
            all_commit_objs = [c for cs in repo_commits.values() for c in cs]
            try:
                result = await summarizer.generate_summary(
                    format_log(all_commit_objs), provider=provider, settings=global_settings
                )
            except ProviderError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            except httpx.HTTPError as e:
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
        "commits": commit_rows if commits else [],
        "log_by_repo": log_by_repo,
        "ai_summary": ai_summary,
        "ai_provider": ai_provider,
        "ai_model": ai_model,
        "ai_summaries": ai_summaries,
    }


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.get("/summary/stream")
async def summary_stream(
    request: Request,
    since: date | None = None,
    until: date | None = None,
    author: str | None = None,
    repo: str | None = None,
    provider: str | None = None,
    session: Session = Depends(get_db),
    current_user: UserRow = Depends(get_current_user),
):
    """Server-sent-events variant of /summary?ai=true. Emits a `meta` event
    (the same stats/log payload /summary returns) followed by per-repo `delta`
    events as the provider streams tokens, a `repo_done`/`repo_error` per repo,
    and a final `done`. The UI fills each card in as text arrives instead of
    blocking on a spinner for the whole fan-out.

    All DB reads happen up front: the StreamingResponse generator runs after
    the request handler returns and the Depends-injected session is closed, so
    it must only touch the provider, never the DB."""
    total, commit_rows = _query_commits(
        since, until, author, repo, limit=None, offset=0, owner_id=current_user.id, session=session
    )
    _check_ai_preconditions(request, provider, total)

    by_repo, by_day, repo_commits = _aggregate_commits(commit_rows)
    log_by_repo = {name: format_log(cs) for name, cs in repo_commits.items()}
    name_to_id = _repo_name_to_id(session, current_user.id)
    global_settings = _resolve_settings_dict(session, None, current_user.id)
    settings_by_repo = {
        name: _resolve_settings_dict(session, name_to_id.get(name), current_user.id)
        for name in log_by_repo
    }
    resolved = summarizer.resolve_provider(provider)

    meta = {
        "period": {
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
        },
        "total_commits": total,
        "by_repo": dict(by_repo),
        "by_day": dict(sorted(by_day.items())),
        "repos": list(log_by_repo),
        "provider": resolved.name,
        "model": resolved.model(),
    }

    async def event_stream():
        yield _sse("meta", meta)
        async with httpx.AsyncClient() as client:
            for name, log_text in log_by_repo.items():
                try:
                    async for chunk in summarizer.stream_summary(
                        log_text,
                        provider=provider,
                        settings=settings_by_repo.get(name, global_settings),
                        client=client,
                    ):
                        yield _sse("delta", {"repo": name, "text": chunk})
                    yield _sse(
                        "repo_done",
                        {"repo": name, "provider": resolved.name, "model": resolved.model()},
                    )
                except (ProviderError, httpx.HTTPError) as e:
                    log.warning("Stream failed for repo %s: %s", name, e, extra={"repo": name})
                    yield _sse("repo_error", {"repo": name, "detail": str(e)})
        yield _sse("done", {})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/repos")
def list_repos(
    session: Session = Depends(get_db),
    current_user: UserRow = Depends(get_current_user),
):
    rows = session.scalars(select(RepoRow).where(RepoRow.owner_id == current_user.id)).all()
    return {"repos": [_repo_to_dict(r) for r in rows]}


@app.post("/repos", status_code=201)
def create_repo(
    req: RepoCreate,
    background: BackgroundTasks,
    session: Session = Depends(get_db),
    current_user: UserRow = Depends(get_current_user),
):
    from backend.git import _repo_name_from_url, is_remote_url

    if not is_remote_url(req.url):
        raise HTTPException(
            status_code=400,
            detail="Must be a remote git URL (https://, git@, git:// or ssh://)",
        )
    name = _repo_name_from_url(req.url)

    existing = session.scalar(select(RepoRow).where(RepoRow.clone_url == req.url))
    if existing:
        raise HTTPException(status_code=409, detail="Repo already registered")
    if session.scalar(select(RepoRow).where(RepoRow.name == name)):
        raise HTTPException(status_code=409, detail="A repo with this name already exists")
    repo = RepoRow(
        name=name,
        clone_url=req.url,
        owner_id=current_user.id,
        added_at=datetime.now(UTC),
    )
    session.add(repo)
    session.commit()
    session.refresh(repo)

    background.add_task(_ingest_repo, repo.id, name, req.url, current_user.id)
    return _repo_to_dict(repo)


@app.delete("/repos/{repo_id}", status_code=204)
def delete_repo(
    repo_id: int,
    session: Session = Depends(get_db),
    current_user: UserRow = Depends(get_current_user),
):
    repo = _owned_repo(session, repo_id, current_user.id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")
    session.delete(repo)
    session.commit()


@app.post("/summaries", status_code=201)
def create_share(
    req: ShareCreate,
    session: Session = Depends(get_db),
    current_user: UserRow = Depends(get_current_user),
):
    """Persist the parameters of a summary behind a short slug. The slug is the
    only secret guarding it — resolving /summaries/{slug} re-runs the query.
    The share records its creator (`owner_id`); read-side ownership enforcement
    lands in slice 2 (issue #71)."""
    now = datetime.now(UTC)
    slug = secrets.token_urlsafe(8)
    row = SharedSummaryRow(
        slug=slug,
        owner_id=current_user.id,
        params=req.model_dump(),
        created_at=now,
        expires_at=now + timedelta(days=SHARE_TTL_DAYS),
    )
    session.add(row)
    session.commit()
    return {"slug": slug, "expires_at": row.expires_at.isoformat()}


def _share_to_dict(row: SharedSummaryRow) -> dict:
    return {
        "slug": row.slug,
        "params": row.params,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
    }


def _as_utc(dt: datetime) -> datetime:
    """Treat a tz-naive datetime as UTC. Postgres returns aware datetimes for
    our timezone=True columns, but SQLite (the test DB) hands back naive ones —
    normalise so the expiry comparison works on both."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


@app.get("/summaries/{slug}")
def get_share(slug: str, session: Session = Depends(get_db)):
    """Resolve a slug to its stored summary params. 404 for unknown or expired
    slugs (the read path enforces expiry independently of the cleanup sweep)."""
    row = session.get(SharedSummaryRow, slug)
    if row is None or _as_utc(row.expires_at) <= datetime.now(UTC):
        raise HTTPException(status_code=404, detail="Share not found or expired")
    return _share_to_dict(row)


# Serve the built SvelteKit SPA same-origin in production. Mounted LAST so it never
# shadows the API routes above, and only when the build exists (in dev the frontend
# runs on the Vite server instead, so this is skipped and startup doesn't fail).
_FRONTEND_BUILD = Path(__file__).resolve().parent.parent / "frontend" / "build"


@app.get("/s/{slug}")
def share_page(slug: str):
    """Serve the SPA shell for a shared-summary deep link so a hard refresh on
    /s/{slug} works. The client-side route reads the slug and re-runs the
    query via GET /summaries/{slug}. In dev (no build) the Vite server handles
    this route instead, so a 404 here is correct."""
    fallback = _FRONTEND_BUILD / "200.html"
    if fallback.is_file():
        return FileResponse(fallback)
    raise HTTPException(status_code=404, detail="Frontend build not available")


if _FRONTEND_BUILD.is_dir():
    app.mount("/", StaticFiles(directory=_FRONTEND_BUILD, html=True), name="frontend")
