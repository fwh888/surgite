# v2 implementation plan: SvelteKit frontend

Concrete, researched build plan for the v2 web UI. The backend half of v2 (the `repos`
table + `/repos` routes) is already done; this covers the frontend.

All tooling details below were verified against official docs on **6 June 2026** — not
from memory. Sources are listed at the bottom.

---

## Decision: SvelteKit (static adapter, SPA mode)

We're using **SvelteKit**, not plain Vite + Svelte, because the Svelte team now officially
recommends it for new projects and the learning/portfolio value is part of this project's goal.

Because FastAPI is already the backend, we don't want SvelteKit's server half. We run it as a
**single-page app**: SSR off, prerender the shell, output static files that FastAPI serves.
This keeps the production deployment a **single server** (FastAPI) — no Node process in prod.

What we deliberately turn off (FastAPI already does these jobs): server-side rendering, server
endpoints, form actions, load functions hitting a server. We keep: file-based routing, Svelte 5
components, and the build pipeline.

---

## Verified tooling (June 2026)

| Tool | Version / command | Notes |
|---|---|---|
| Scaffolder | `npx sv create` | The new `sv` CLI. **`create-svelte` is deprecated.** Offers Tailwind as an add-on during scaffolding, in one pass. |
| Svelte | 5 (runes) | `$state`, `$derived`, `$props`, `$effect` — not the old `let`-is-reactive model. |
| Tailwind | v4 via `@tailwindcss/vite` | `@import "tailwindcss"` in CSS. **No `tailwind.config.js`, no PostCSS.** |
| Static adapter | `@sveltejs/adapter-static` | `fallback: '200.html'` for SPA routing; default output dir is `build/`. |

---

## Directory layout

Frontend lives in its own `frontend/` subdirectory so SvelteKit's `build/` output doesn't
collide with Python's existing (gitignored) `build/` packaging artifacts.

```
standup-gen/
├── backend/            # Python package (API + CLI), formerly standup/
├── frontend/           # NEW — SvelteKit app (TypeScript)
│   ├── src/
│   │   ├── routes/
│   │   │   ├── +layout.ts       # ssr = false, prerender = true
│   │   │   ├── +layout.svelte   # imports layout.css, renders children
│   │   │   ├── layout.css       # @import "tailwindcss";
│   │   │   └── +page.svelte     # the one page
│   │   ├── lib/
│   │   │   ├── api.ts           # thin fetch wrapper + typed Repo/Commit/Summary shapes
│   │   │   └── components/
│   │   │       ├── RepoList.svelte
│   │   │       ├── AddRepoForm.svelte
│   │   │       └── SummaryPanel.svelte
│   ├── svelte.config.js         # adapter-static, fallback: '200.html'
│   ├── vite.config.ts           # @tailwindcss/vite + sveltekit plugins
│   └── build/                   # static output FastAPI serves (gitignored)
└── ...
```

---

## Steps

### 1. Scaffold ✅ done

```bash
npx sv create frontend   # run interactively from repo root
```

Choices made: **SvelteKit minimal** template, **TypeScript** (TS syntax), **tailwindcss**
add-on (with **no** Tailwind sub-plugins — the typography/forms sub-prompt is what hangs a
fully-flagged non-interactive run), **npm** as the package manager. This wires Tailwind v4 via
`@tailwindcss/vite` automatically — no separate install.

### 2. Configure SPA mode (no SSR) ✅ done

`frontend/src/routes/+layout.ts`:
```javascript
export const ssr = false;       // FastAPI is the backend; no server rendering
export const prerender = true;  // prerender the static shell at build time
```

`frontend/svelte.config.js` — use the static adapter with an SPA fallback:
```javascript
import adapter from '@sveltejs/adapter-static';

export default {
  kit: {
    adapter: adapter({ fallback: '200.html' })
  }
};
```

`fallback: '200.html'` makes any unmatched URL boot the client app — standard SPA behavior.
Build output lands in `frontend/build/`.

### 3. Dev wiring (frontend ↔ API across origins)

In dev the Vite dev server runs on `:5173` and FastAPI on `:8000` — different origins, so we
need to bridge them. Plan:

- Frontend fetches use a base URL from an env var: `const BASE = import.meta.env.VITE_API_BASE ?? ''`.
  - **Dev:** `frontend/.env` sets `VITE_API_BASE=http://localhost:8000`.
  - **Prod:** unset → empty string → same-origin relative requests (FastAPI serves both).
- Add CORS middleware to FastAPI allowing the dev origin only:
  ```python
  from fastapi.middleware.cors import CORSMiddleware
  app.add_middleware(
      CORSMiddleware,
      allow_origins=["http://localhost:5173"],
      allow_methods=["*"],
      allow_headers=["*"],
  )
  ```

This keeps the frontend fetch code identical in dev and prod (only the base differs), and CORS
is a useful thing to understand. (Alternative considered: Vite's `server.proxy`. Rejected
because our API paths have no common prefix — `/repos`, `/commits`, `/summary`, `/providers`,
`/ingest` — so proxying is fiddlier than one CORS block.)

### 4. API client (`src/lib/api.ts`)

One function per endpoint, fetch kept out of components, with typed `Repo`/`Commit`/`Summary`
shapes documenting the API contract:
- `listRepos()` → `GET /repos`
- `addRepo(path)` → `POST /repos`
- `deleteRepo(id)` → `DELETE /repos/{id}`
- `ingestRepo(id)` → `POST /repos/{id}/ingest`
- `generateSummary({repo, since, until, ai})` → `GET /summary`

### 5. Components (Svelte 5 runes)

- **`+page.svelte`** — layout + loads repos on mount, holds top-level state.
- **`RepoList.svelte`** — table: name, relative "last ingested" time, per-row "Ingest now".
- **`AddRepoForm.svelte`** — toggle-able inline form (path input + submit).
- **`SummaryPanel.svelte`** — repo selector (All / specific), period selector (7d / custom),
  Generate button, output box with a Copy button.

Each gets loading + error states so failures aren't silent.

### 6. FastAPI serves the build

Mount the static output so prod is one server. In `api.py`:
```python
from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory="frontend/build", html=True), name="frontend")
```
Mount **last**, after all API routes, so it doesn't shadow them. `html=True` serves
`index.html` at `/`. (If we later add client-side routes, wire the `200.html` fallback for
unknown paths; with a single page it isn't needed yet.)

### 7. Build + CI

- `cd frontend && npm run build` produces `frontend/build/`.
- Add `frontend/build/` and `frontend/node_modules/` to `.gitignore`.
- CI (`.forgejo/workflows/ci.yml`): a `frontend` job that runs `npm ci && npm run build` to
  catch build breaks. (Deferring lint/test on the frontend until there's enough to test.)

---

## Deferred (not now)

- Frontend unit tests (Vitest/Playwright) — wait until the UI has logic worth testing.
- Polishing for open source — README screenshot/GIF, picking a LICENSE, and making the CLI
  config degrade gracefully (no `KeyError` on missing `DATABASE_URL`). Do after the UI works.

---

## Sources

- Svelte — Getting started: <https://svelte.dev/docs/svelte/getting-started>
- SvelteKit — Single-page apps: <https://svelte.dev/docs/kit/single-page-apps>
- SvelteKit — adapter-static: <https://svelte.dev/docs/kit/adapter-static>
- Tailwind CSS — Install with Vite: <https://tailwindcss.com/docs/installation/using-vite>