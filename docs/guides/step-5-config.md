# Step 5: Create `config.py`

**The instruction:** Read `DATABASE_URL`, `API_HOST`, `API_PORT`, and `GROQ_API_KEY` from environment variables using `os.environ`, with `python-dotenv` for local dev.

This is a new file. It gives the API and DB layers a single place to read config instead of scattering `os.environ.get(...)` calls across files.

## What to build

Create `standup/config.py`:

```python
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
API_HOST = os.environ.get("API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("API_PORT", "8000"))
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
```

A few deliberate choices here:

- `DATABASE_URL` uses `os.environ["DATABASE_URL"]` (hard brackets, not `.get()`). This raises a `KeyError` at import time if the variable is missing, which gives you a clear error immediately rather than a confusing failure later when the DB is first touched.
- `API_HOST` and `API_PORT` have sensible defaults so you can run the API locally without a full `.env`.
- `GROQ_API_KEY` is `None` if not set — the summarizer and `GET /summary?ai=true` will check for it at call time, not at startup.
- `int(...)` on `API_PORT` is necessary because environment variables are always strings.

## Your `.env` file

You should already have `.env.example` in the project root. Copy it if you haven't:

```bash
cp .env.example .env
```

Then fill in a real `GROQ_API_KEY` and confirm `DATABASE_URL` points to your local Postgres (after you start it in Step 6):

```
DATABASE_URL=postgresql://standup:standup@localhost:5432/standup
API_HOST=127.0.0.1
API_PORT=8000
GROQ_API_KEY=gsk_...
```

Note: `.env.example` uses `db` as the hostname (for Docker networking). For local dev outside Docker, change it to `localhost`.

## Note on `standup.py`

The existing CLI already calls `load_dotenv()` at the top of `main()`. Once `config.py` exists, `load_dotenv()` will be called from there too. That's fine — calling it twice is harmless. You can clean it up from `standup.py` later if you want, but it's not required.

## What you're not doing yet

- Do not create `db.py` yet
- Do not import `config.py` anywhere yet — it will be imported by `db.py` in the next step

---

**Step 5 is done when:** `standup/config.py` exists, and `from standup.config import DATABASE_URL` works without errors (with `.env` populated).

**Next:** [Step 6](step-6-db.md) — create `db.py`, add SQLAlchemy + Alembic, extend the `Commit` dataclass, and write the first migration.
