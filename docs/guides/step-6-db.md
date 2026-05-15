# Step 6: Create `db.py` and set up the database

**The instruction:** Define the SQLAlchemy engine, session factory, and ORM model for the `commits` table. Extend the `Commit` dataclass with `repo` and `ingested_at`. Add `alembic` and `sqlalchemy` to `pyproject.toml`, run `alembic init`, and write the first migration.

This is the largest step so far. Take it in order.

## 1. Add dependencies

In `pyproject.toml`, add `sqlalchemy` and `alembic` to the dependencies list:

```toml
dependencies = [
    "groq>=1.2.0",
    "python-dotenv>=1.2.2",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
]
```

Then install:

```bash
uv sync
```

## 2. Extend the `Commit` dataclass in `models.py`

Add `repo` and `ingested_at`. Use `field(default=None)` so the existing CLI code that constructs `Commit` objects without these fields doesn't break:

```python
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class Commit:
    hash: str
    date: str
    author: str
    message: str
    repo: str | None = field(default=None)
    ingested_at: datetime | None = field(default=None)
```

The CLI still constructs `Commit` objects from `parse_log()` with only 4 fields — that still works because `repo` and `ingested_at` default to `None`. The API will populate them when writing to the database.

## 3. Create `standup/db.py`

```python
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session
from standup.config import DATABASE_URL

engine = create_engine(DATABASE_URL)

class Base(DeclarativeBase):
    pass

class CommitRow(Base):
    __tablename__ = "commits"

    hash: Mapped[str] = mapped_column(String, primary_key=True)
    short_hash: Mapped[str] = mapped_column(String(7))
    date: Mapped[str] = mapped_column(String)
    author: Mapped[str] = mapped_column(String)
    message: Mapped[str] = mapped_column(String)
    repo: Mapped[str] = mapped_column(String)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

def get_session() -> Session:
    return Session(engine)
```

A few notes:
- `hash` is the primary key — it's globally unique across all commits from all repos.
- `short_hash` is stored here (unlike in the `Commit` dataclass where it's derived). Storing it makes SQL queries easier and avoids recomputing it on every read.
- `CommitRow` is separate from the `Commit` dataclass. The dataclass is for the CLI/git layer; `CommitRow` is for the database layer. The API will translate between them.

## 4. Set up Alembic

```bash
uv run alembic init alembic
```

This creates an `alembic/` directory and `alembic.ini` in the project root.

### Configure `alembic.ini`

Find this line and leave it blank — you'll set it from code instead:

```ini
sqlalchemy.url =
```

### Configure `alembic/env.py`

Replace the top of the file to import your models and read `DATABASE_URL` from config:

```python
from standup.config import DATABASE_URL
from standup.db import Base

config.set_main_option("sqlalchemy.url", DATABASE_URL)
target_metadata = Base.metadata
```

The rest of `env.py` can stay as Alembic generated it.

## 5. Write the first migration

```bash
uv run alembic revision --autogenerate -m "create commits table"
```

This inspects `Base.metadata` (your `CommitRow` model) and generates a migration file in `alembic/versions/`. Open it and confirm it creates a `commits` table with all the columns you defined.

## 6. Start Postgres and run the migration

```bash
# Start Postgres (uses docker-compose.yml from the project root)
docker compose up -d

# Apply the migration
uv run alembic upgrade head
```

If `docker-compose.yml` doesn't exist yet, create it in the project root using the starter from the upgrade plan:

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: standup
      POSTGRES_PASSWORD: standup
      POSTGRES_DB: standup
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

## 7. Verify

Connect to the database and confirm the table exists:

```bash
docker exec -it $(docker ps -qf "name=db") psql -U standup -d standup -c "\d commits"
```

You should see all the columns: `hash`, `short_hash`, `date`, `author`, `message`, `repo`, `ingested_at`.

---

**Step 6 is done when:** the `commits` table exists in Postgres, `uv run alembic upgrade head` runs clean, and `uv run standup` still works (the CLI should be unaffected).

**Next:** [Step 7](step-7-api.md) — implement `api.py` with all four routes.
