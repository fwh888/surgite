from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
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


class Base(DeclarativeBase):  # Base class for SQLAlchemy models
    pass


class CommitRow(Base):
    __tablename__ = "commits"

    hash: Mapped[str] = mapped_column(String, primary_key=True)
    short_hash: Mapped[str] = mapped_column(String(7))
    date: Mapped[date] = mapped_column(Date)
    author: Mapped[str] = mapped_column(String)
    message: Mapped[str] = mapped_column(String)
    repo: Mapped[str] = mapped_column(String)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )


class RepoRow(Base):
    __tablename__ = "repos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    clone_url: Mapped[str] = mapped_column(String, unique=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    last_ingested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PromptSettingsRow(Base):
    __tablename__ = "prompt_settings"
    # One settings row per repo, plus one global row with repo_id IS NULL.
    # The unique constraint stops a repo from getting two rows; the single
    # global row is maintained by the get-or-create logic in the API (a
    # partial unique index on NULL isn't portable to the SQLite test DB).
    __table_args__ = (UniqueConstraint("repo_id", name="uq_prompt_settings_repo_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_id: Mapped[int | None] = mapped_column(
        ForeignKey("repos.id", ondelete="CASCADE"), nullable=True
    )
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
