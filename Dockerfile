FROM node:22-slim AS frontend
WORKDIR /build/frontend
# npm ci keyed on the manifests alone, so a .svelte edit reuses node_modules.
# The `prepare` script's svelte-kit sync has no config to read yet; its
# `|| echo ''` guard makes that harmless, and `vite build` syncs anyway.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim
WORKDIR /app
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
RUN pip install uv --quiet
# Deps install from the manifests alone, so a source edit below reuses this
# layer. --no-install-project is load-bearing: surgite is not here yet, and a
# plain `uv sync` fails on that -- which is what reverted this split in 6b525b0.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
# Installs surgite itself; deps are already in .venv, which survives the COPY
# because .dockerignore excludes it.
RUN uv sync --frozen --no-dev
COPY --from=frontend /build/frontend/build /app/frontend/build
RUN mkdir -p /var/surgite/repos /var/surgite/data
EXPOSE 8000
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
CMD ["/entrypoint.sh"]