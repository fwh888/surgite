from datetime import datetime, timezone
from sqlalchemy import create_engine, String, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session
from standup.config import DATABASE_URL

engine = create_engine(DATABASE_URL)

class Base(DeclarativeBase): # Base class for SQLAlchemy models
    pass

class CommitRow(Base):
    __tablename__ = "commits"

    hash: Mapped[str] = mapped_column(String, primary_key=True)
    short_hash: Mapped[str] = mapped_column(String(7)) # short 7 char git hash
    date: Mapped[str] = mapped_column(String)
    author: Mapped[str] = mapped_column(String)
    message: Mapped[str] = mapped_column(String)
    repo: Mapped[str] = mapped_column(String)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc) # lambda to ensure it's evaluated at insert time, not at class definition time
    )

def get_session():
    return Session(engine)