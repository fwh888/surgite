# v2 sketch: repo management + web UI

This picks up after the v1 upgrade plan is complete. The API is running, commits are persisted, and `GET /summary?ai=true` works. This document sketches what comes next.

---

## What needs to be added to the backend

### New: `repos` table

Right now repos are listed in a flat file read by `scripts/ingest_all.sh`. The UI needs to manage them dynamically.

```
repos
─────────────────────────────────────
id          integer, primary key
name        text (e.g. "Arbiter")
path        text (local filesystem path)
added_at    timestamptz
last_ingested_at  timestamptz (nullable)
```

### New API routes

```
GET    /repos              → list all registered repos
POST   /repos              → register a new repo { "path": "/Users/nick/dev/Arbiter" }
DELETE /repos/{id}         → remove a repo
POST   /repos/{id}/ingest  → manually trigger ingest for one repo
```

`POST /ingest` stays as-is for the CLI and automation script. The new `/repos/{id}/ingest` is the UI-facing version — it looks up the path from the DB so the frontend doesn't need to pass it.

### Change to automation

`scripts/ingest_all.sh` can be simplified — instead of reading a flat file, it just hits `POST /repos/{id}/ingest` for each registered repo. Or the API can expose a `POST /ingest/all` endpoint that does it in one call.

---

## Frontend

### What it does

- A repo list with an "Add repo" button (paste a local path)
- Per-repo: last ingested time, commit count, "Ingest now" button
- A summary view: pick a repo (or "all"), pick a time range (last 7 days / last 5 days / custom), click "Generate summary"
- The summary renders the AI text in a copyable text box — one click to copy for Slack/email

### Tech stack options

**Option A: Lightweight (recommended for v1 UI)**
- Plain HTML + vanilla JS or Alpine.js
- Served as static files by FastAPI (`app.mount("/", StaticFiles(...))`)
- No build step, no framework overhead
- Good fit if the tool stays personal/local

**Option B: React or Vue SPA**
- More structure for a growing UI
- Requires a build step (Vite)
- Right choice if you want a polished, shareable product
- FastAPI serves the built `dist/` folder

Either way, the frontend only talks to the existing API — there's no new backend logic required beyond the repo management routes above.

### Rough page layout

```
┌─────────────────────────────────────────────────┐
│  standup                                        │
├─────────────────────────────────────────────────┤
│  Repos                              [+ Add repo]│
│  ┌──────────────────────────────────────────┐   │
│  │ Arbiter          last ingested: 2h ago   │   │
│  │ standup-gen      last ingested: 2h ago   │   │
│  └──────────────────────────────────────────┘   │
├─────────────────────────────────────────────────┤
│  Generate summary                               │
│                                                 │
│  Repo:  [All ▾]   Period: [Last 7 days ▾]       │
│                                                 │
│  [Generate]                                     │
│                                                 │
│  ┌──────────────────────────────────────────┐   │
│  │ This week I worked on...                 │   │
│  │                                          │   │
│  │                              [Copy text] │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

---

## Open source considerations

A few things worth doing before making the repo public that aren't worth doing right now:

- **`GROQ_API_KEY` must never be committed** — `.env` should already be in `.gitignore`, but double-check
- **`README.md`** — needs a proper project description, setup instructions, and a screenshot or demo GIF once the UI exists
- **`LICENSE`** — pick one before publishing (MIT is the obvious choice for a personal tool)
- **`CONTRIBUTING.md`** — optional but useful if you want external contributors
- Make `DATABASE_URL` default gracefully in the CLI (right now it'll raise `KeyError` at import if not set, which is bad UX for someone who just wants to run `standup` without Postgres)
- Consider making Postgres optional for the CLI path — the CLI worked fine before the DB existed, and a new user shouldn't need Docker just to run `standup /path/to/repo`

---

## Suggested order

1. Finish the v1 upgrade plan (Steps 1–9)
2. Add repo management routes to `api.py` + migrate the DB
3. Build the UI (start with Option A — upgrade to React later if needed)
4. Polish for open source (README, LICENSE, graceful config errors)
