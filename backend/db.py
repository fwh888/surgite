import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from backend.config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20, pool_pre_ping=True)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):  # Base class for SQLAlchemy models
    pass


class UserRow(Base):
    """An account. In AUTH_MODE=off/single_user a single bootstrap user owns
    everything (see backend.auth.ensure_bootstrap_user); multi_user mode has
    one row per real account.

    `email` is stored lower-cased and is unique. Postgres uses a CITEXT column
    (see the migration) for index-supported case-insensitive lookups; the
    SQLite test DB falls back to a plain String, so the app lower-cases on the
    way in to keep the two backends consistent."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    display_name: Mapped[str] = mapped_column(String, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SessionRow(Base):
    """A server-side session. The opaque `id` is what the cookie carries; the
    cookie never holds user data. Swept by backend.auth.purge_expired_sessions
    on the lifespan scheduler, and rejected on read once past `expires_at`."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    ip: Mapped[str | None] = mapped_column(String, nullable=True)


class InviteRow(Base):
    """A single-use invite token. `email` null means any email can claim it.
    The bootstrap invite (created on first run for BOOTSTRAP_OWNER_EMAIL) has
    a null `created_by` because no user exists yet to author it."""

    __tablename__ = "invites"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    token: Mapped[str] = mapped_column(String, unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, default="user")
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class CommitRow(Base):
    __tablename__ = "commits"

    hash: Mapped[str] = mapped_column(String, primary_key=True)
    short_hash: Mapped[str] = mapped_column(String(7))
    date: Mapped[date] = mapped_column(Date)
    author: Mapped[str] = mapped_column(String)
    message: Mapped[str] = mapped_column(String)
    repo: Mapped[str] = mapped_column(String)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )


class RepoRow(Base):
    __tablename__ = "repos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    clone_url: Mapped[str] = mapped_column(String, unique=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    last_ingested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PromptSettingsRow(Base):
    __tablename__ = "prompt_settings"
    # One settings row per (owner, repo), plus one global row per owner with
    # repo_id IS NULL. The unique constraint stops a repo from getting two
    # rows; the single per-owner global row is maintained by the get-or-create
    # logic in the API (a partial unique index on NULL isn't portable to the
    # SQLite test DB, and NULL repo_id values are distinct under the unique
    # constraint anyway).
    __table_args__ = (
        UniqueConstraint("owner_id", "repo_id", name="uq_prompt_settings_owner_repo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_id: Mapped[int | None] = mapped_column(
        ForeignKey("repos.id", ondelete="CASCADE"), nullable=True
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    user_name: Mapped[str] = mapped_column(String, default="")
    user_role: Mapped[str] = mapped_column(String, default="")
    tone: Mapped[str] = mapped_column(String, default="neutral")
    group_count: Mapped[str] = mapped_column(String, default="2-5")
    output_format: Mapped[str] = mapped_column(String, default="markdown")
    custom_instructions: Mapped[str] = mapped_column(String, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )


class SharedSummaryRow(Base):
    """A saved, shareable summary query. The slug is the only secret; resolving
    it re-runs the stored params. Expired rows are swept by the scheduler and
    rejected on read (see backend.api)."""

    __tablename__ = "shared_summaries"

    slug: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def get_session():
    return Session(engine)


def get_db() -> Generator[Session]:
    with get_session() as session:
        yield session


@contextmanager
def session_scope(session: Session | None = None):
    if session is not None:
        yield session
    else:
        with get_session() as s:
            yield s
