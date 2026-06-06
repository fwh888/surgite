FROM python:3.14-slim

WORKDIR /app

RUN pip install uv uvicorn

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

RUN uv run alembic upgrade head || true

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8000"]