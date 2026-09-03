#!/bin/sh
set -e
.venv/bin/alembic upgrade head
exec .venv/bin/uvicorn surgite.api:app --host 0.0.0.0 --port 8000
