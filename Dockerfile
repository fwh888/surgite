FROM node:23-slim AS frontend
WORKDIR /build
COPY frontend/ ./frontend/
WORKDIR /build/frontend
RUN npm ci && npm run build

FROM python:3.14-slim
WORKDIR /app
RUN pip install uv --quiet
COPY . .
RUN uv sync --frozen --no-dev
COPY --from=frontend /build/frontend/build /app/frontend/build
EXPOSE 8000
CMD uv run alembic upgrade head && uv run uvicorn backend.api:app --host 0.0.0.0 --port 8000