# surgite frontend

SvelteKit SPA (Svelte 5 + Tailwind v4) for the surgite web app: register repos,
trigger ingests, and generate standup summaries from the browser. Built to static
assets via `@sveltejs/adapter-static` and served same-origin by the FastAPI backend
in production.

For the full project (backend, CLI, Docker quickstart), see the
[root README](../README.md).

## Development

```bash
npm install
npm run dev      # Vite dev server on :5173, calls the API on :8000 cross-origin
```

Run the backend (`uv run uvicorn surgite.api:app --reload`) alongside it. To point at
a non-default backend, set `VITE_API_BASE` — see [.env.example](.env.example).

## Build & check

```bash
npm run build    # production build → ./build (served by the backend)
npm run preview  # preview the production build locally
npm run check    # svelte-check (type + a11y diagnostics)
```
