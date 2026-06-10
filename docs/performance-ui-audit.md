# Performance & UI/UX Audit

Audit of standup-gen (FastAPI + SQLAlchemy/Postgres backend, Svelte 5 SPA frontend)
focused on performance and UI/UX. Each item lists severity, affected files/lines
(as of `main` @ 0154b06), the problem, and the minimal recommended fix.

Items are ordered by priority within each category.

---

## 1. Backend performance

### 1.1 `/summary` blocks synchronously for the whole pipeline — **High**

**Files:** `backend/api.py:272-281`, `backend/summarizer.py:216-242`, `backend/git.py:32-62`

A single `GET /summary` request runs, in sequence, inside one threadpool worker:

1. `git fetch`/`git clone` for **every** registered repo (`_ingest_all_repos`)
2. per-repo DB upsert
3. with `ai=true`: **one LLM HTTP call per repo plus one combined call**
   (`generate_summary_per_repo` loops sequentially, then `generate_summary`
   is called again for the combined log — `api.py:313-323`), each with a
   120 s timeout (`summarizer.py:14`)

A 5-repo workspace makes 6 sequential LLM round-trips; total latency is easily
15–60 s. Because the endpoint is a plain `def`, each in-flight request pins one
of FastAPI's default ~40 threadpool threads, so a handful of concurrent users
can stall the whole API (including `/health`).

**Fix (minimal, staged):**

- Parallelize the per-repo LLM calls with `concurrent.futures.ThreadPoolExecutor`
  inside `generate_summary_per_repo` — one-file change, cuts AI latency from
  `(N+1) × call` to roughly `2 × call`.
- Drop the combined `generate_summary` call when the client doesn't need it
  (see 1.2): the web UI only renders `ai_summaries`, never `ai_summary`.
- Longer term: make the endpoint `async def`, move ingest to a background task
  (`BackgroundTasks` or a periodic sync), and stream the AI summary
  (`StreamingResponse`) so the UI shows progress instead of a spinner for 30 s.

### 1.2 The combined AI summary is generated but never shown in the web UI — **High**

**Files:** `backend/api.py:316-330`, `frontend/src/lib/components/SummaryPanel.svelte:175-196`

When `ai=true`, the API always makes an extra LLM call over the full combined
log (`generate_summary(format_log(all_commit_objs), …)`) in addition to the
per-repo calls. `SummaryPanel.svelte` renders only `result.ai_summaries`;
`ai_summary` is dead weight for the web client. That's one full LLM call's
latency and token cost wasted on every web-UI generate.

**Fix:** add an opt-in query param (e.g. `combined=true`) and only run the
combined call when requested; the CLI can pass it, the web UI doesn't.

### 1.3 `/summary` re-ingests ALL repos on every request — **High**

**File:** `backend/api.py:281` (`_ingest_all_repos`, defined at 28-43)

Every `/summary` call triggers `git fetch` + upsert for every registered repo —
even when the user filtered to a single repo (the `repo` query param is not
passed to ingest, only to `_query_commits`). Ten repos = ten serial network
fetches per click of "generate".

**Fix (minimal):**

- Pass the `repo` filter into `_ingest_all_repos` and skip non-matching repos.
- Skip repos whose `last_ingested_at` (already stored on `RepoRow`,
  `db.py:42-44`) is fresher than a TTL, e.g.:

```python
STALE_AFTER = timedelta(minutes=10)

def _needs_ingest(row: RepoRow) -> bool:
    return row.last_ingested_at is None or \
        datetime.now(UTC) - row.last_ingested_at > STALE_AFTER
```

- Longer term: a periodic background sync job and never ingest in the request path.

### 1.4 N+1 query in `_ingest_repo` — **High**

**File:** `backend/api.py:66-87`

Each parsed commit does `session.get(CommitRow, c.hash)` individually — 500
commits = 500 round-trip SELECTs per repo per `/summary` call.

**Fix:** one bulk SELECT for existing hashes, then insert only the new rows:

```python
with get_session() as session:
    hashes = [c.hash for c in commits]
    existing = {
        row.hash: row
        for row in session.scalars(
            select(CommitRow).where(CommitRow.hash.in_(hashes))
        )
    }
    now = datetime.now(UTC)
    for c in commits:
        row = existing.get(c.hash)
        if row is None:
            session.add(CommitRow(hash=c.hash, short_hash=c.hash[:7],
                                  date=c.date, author=c.author,
                                  message=c.message, repo=repo_name,
                                  ingested_at=now))
            inserted += 1
        elif row.repo != repo_name:
            row.repo, row.ingested_at = repo_name, now
            updated += 1
        else:
            unchanged += 1
```

(For larger batches, `postgresql.insert(...).on_conflict_do_nothing()` avoids
the SELECT entirely, but the dict approach is the minimal change and keeps the
inserted/updated/unchanged counters.)

### 1.5 No indexes on `commits` — **Medium** (grows to High with data)

**Files:** `backend/db.py:15-29`, `alembic/versions/e5e311c2e5f0_create_commits_table.py`

The only index is the PK on `hash`. Every filter `_query_commits` supports —
`date >=/<=`, `author ILIKE`, `repo ILIKE` (`api.py:149-156`) — plus the
`ORDER BY date DESC` and the manual cascade `DELETE … WHERE repo = …`
(`api.py:397`) is a sequential scan.

**Fix:** add a migration with indexes matching the query shapes:

```python
op.create_index("ix_commits_date", "commits", ["date"])
op.create_index("ix_commits_repo_date", "commits", ["repo", "date"])
op.create_index("ix_commits_author", "commits", ["author"])
```

Note: the `ILIKE '%…%'` filters can't use btree indexes regardless (see 1.8) —
exact-match or prefix filters would let `ix_commits_repo_date` do its job. The
`repo` filter in particular comes from a `<select>` of exact repo names in the
UI, so equality (`==`) is the right operator there anyway.

### 1.6 `CommitRow.date` stored as String — **Medium**

**File:** `backend/db.py:20` (also `e5e311c2e5f0` migration line 29)

Dates are TEXT and compared lexicographically (`api.py:150-152` compares
against `date.isoformat()`). That works only because the format is ISO-8601,
but it blocks native date functions (`date_trunc`, range types), makes
indexing/statistics worse, and silently accepts garbage.

**Fix:** migration to `sa.Date` with `USING date::date`, change the model to
`Mapped[date] = mapped_column(Date)`, and drop the `.isoformat()` calls in
`_query_commits`. `parse_log` already emits `--date=short` (`git.py:84`), so
input is clean ISO dates.

### 1.7 Up to 4 + N DB sessions per `/summary` request — **Medium**

**Files:** `backend/api.py:31` (repo list), `:66` (per-repo ingest, ×N),
`:147` (commit query), `:183` (prompt settings)

Each `get_session()` checks a connection out of the pool. One `/summary` with 10
repos and `ai=true` uses 13 sessions serially. Combined with the threadpool
issue (1.1), concurrent requests can exhaust the default SQLAlchemy pool
(5 + 10 overflow) and start throwing `TimeoutError`.

**Fix:** accept an optional `session` parameter in the helpers (or use FastAPI's
`Depends`-injected session) and run the whole request on one session. As a
safety net, configure the engine explicitly:

```python
engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20, pool_pre_ping=True)
```

### 1.8 SQL wildcard injection in ILIKE filters — **Medium**

**File:** `backend/api.py:154-156`

`CommitRow.author.ilike(f"%{author}%")` interpolates user input directly into
the pattern. `%` or `_` in the input changes filter semantics (e.g.
`author=%` matches everything), and a pattern like `%a%b%c%…` can be
pathologically slow. Not SQL injection (it's still a bound parameter), but it
is pattern injection.

**Fix:** escape wildcards and pass the escape char:

```python
def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")

q = q.where(CommitRow.author.ilike(f"%{_escape_like(author)}%", escape="\\"))
```

For `repo`, switch to exact equality — the UI sends exact names from a dropdown
(see 1.5).

### 1.9 No FK between `commits.repo` and `repos` — **Low**

**Files:** `backend/db.py:23,36`, `backend/api.py:397`

Deleting a repo manually deletes commits by name (`delete(CommitRow).where(
CommitRow.repo == repo.name)`). `repos.name` isn't unique (`db.py:36`), so two
clone URLs that resolve to the same name (e.g. forks `alice/app` and `bob/app`)
silently share/steal commits — `_ingest_repo` even reassigns ownership at
`api.py:82-84` — and deleting one wipes the other's commits too.

**Fix:** add `UNIQUE` on `repos.name` (reject duplicate names at `POST /repos`
with a clear 409), then add `commits.repo_id` FK with `ON DELETE CASCADE` and
drop the manual delete. The unique constraint is the important half; the FK can
follow when convenient.

### 1.10 `POST /repos` blocks on initial clone — **Low**

**File:** `backend/api.py:381-384`

Adding a repo runs `git clone --depth 100` synchronously before responding; a
large repo or slow remote means the "add" button hangs for many seconds.
Failures are already swallowed (`log.warning`), so nothing depends on the
result.

**Fix:** run the initial ingest via `BackgroundTasks`:

```python
@app.post("/repos", status_code=201)
def create_repo(req: RepoCreate, background: BackgroundTasks):
    ...
    background.add_task(_ingest_repo, repo_id, name, req.url)
    return _repo_to_dict(repo)
```

The UI already shows `last_ingested_at` ("never" → relative time), so the user
can see when the first sync lands.

---

## 2. Frontend / UI-UX

### 2.1 Race condition on rapid "Generate" clicks — **High**

**Files:** `frontend/src/lib/components/SummaryPanel.svelte:74-95`,
`frontend/src/lib/api.ts:39-56`

`generate()` has no cancellation: the button is disabled while `generating`,
but a click during the brief window before state flushes — or a generate fired,
parameters changed, generate again after an error — produces overlapping
requests, and whichever resolves *last* wins `result`, which may correspond to
stale parameters. Each orphaned request also still costs a full backend
ingest + LLM run (see 1.1).

**Fix:** thread an `AbortSignal` through the API client and abort the previous
request:

```ts
// api.ts
async function request<T>(path: string, init?: RequestInit): Promise<T> { ... } // already takes init
export const generateSummary = (params: SummaryParams = {}, signal?: AbortSignal) =>
    request<Summary>(`/summary${qs}`, { signal });

// SummaryPanel.svelte
let controller: AbortController | undefined;
async function generate() {
    controller?.abort();
    controller = new AbortController();
    ...
    result = await generateSummary(opts, controller.signal);
}
```

Ignore `AbortError` in the catch so a superseded request doesn't flash an error.

### 2.2 `renderMarkdown` can't render common LLM output — **High**

**File:** `frontend/src/lib/markdown.ts:18-54`

Only `#`–`###` headings, `-`/`*` bullets, bold/italic/inline-code are handled.
Numbered lists (`1.`), links (`[x](y)`), nested lists, and fenced code blocks
(```` ``` ````) all fall through to `<p>` lines — and models emit all of these
routinely even when prompted for simple markdown. A fenced block becomes a
paragraph per line with the backtick fence rendered literally.

**Fix (minimal):** extend the line loop with three cases, reusing the existing
escape-first approach so XSS safety is unchanged:

- ordered lists: `^\s*\d+[.)]\s+(.*)$` → `<ol>`/`<li>` (track list type to
  close/reopen correctly)
- fenced code: on a `` ``` `` line toggle a `inCode` flag; inside it, emit raw
  escaped lines into one `<pre><code>` block, skipping `inline()`
- links: in `inline()`, `\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)` →
  `<a href="$2" rel="noopener noreferrer" target="_blank">$1</a>` (restricting
  to `https?:` keeps `javascript:` URLs out)

Alternative: swap to `marked` + `DOMPurify` (~10 kB gz) and delete this file —
reasonable, but the extension above is the minimal change.

### 2.3 No date-range validation for custom ranges — **Medium**

**File:** `frontend/src/lib/components/SummaryPanel.svelte:120-123` (inputs), `:79-81` (use)

`customSince`/`customUntil` are sent as-is; since > until just returns
"No commits in this period." with no hint why.

**Fix:** derive validity and gate the button:

```svelte
const rangeInvalid = $derived(
    range === 'custom' && !!customSince && !!customUntil && customSince > customUntil
);
```

Disable generate when `rangeInvalid` and show
`<p class="text-err">"From" must be on or before "to".</p>`. Also set
`max={customUntil}` / `min={customSince}` on the two date inputs so the native
picker prevents it in the first place.

### 2.4 Theme list duplicated in two files — **Medium** (maintenance)

**Files:** `frontend/src/app.html:10`, `frontend/src/lib/theme.svelte.ts:15-22`

The pre-paint inline script hardcodes
`['github-dark', 'light', 'nord', 'catppuccin', 'solarized', 'terminal']`;
`THEMES` in `theme.svelte.ts` is the second copy. Adding a theme to one but not
the other either flashes the default or offers a theme the script rejects.

**Fix:** the inline script can't import modules (it must run pre-paint), so
make it validation-free instead of syncing lists: apply whatever
`localStorage.theme` holds, and let `theme.svelte.ts` (the single source of
truth) correct an unknown value right after hydration:

```js
// app.html — no list to maintain
var t = null;
try { t = localStorage.getItem('theme'); } catch (e) {}
document.documentElement.setAttribute('data-theme', t || 'github-dark');
```

An unknown stored value falls back to default CSS variables for one frame and
is then normalized by `ThemeState.initial()` — add a `theme.set(theme.current)`
call on startup to write the corrected attribute back.

### 2.5 No loading skeletons — **Medium**

**Files:** `frontend/src/lib/components/RepoList.svelte:37`,
`frontend/src/lib/components/PromptSettings.svelte:104`

Both render bare "Loading…" text; the layout jumps when content arrives.
(SummaryPanel already has a spinner treatment, which is fine for an action the
user just triggered — the list loads are the ones that benefit from skeletons.)

**Fix:** a small shared `Skeleton.svelte` using Tailwind's `animate-pulse`,
sized like a repo row:

```svelte
{#if loading}
    {#each Array(3) as _}
        <div class="flex items-center justify-between px-4 py-3">
            <div class="h-4 w-40 animate-pulse bg-surface-2"></div>
            <div class="h-3 w-16 animate-pulse bg-surface-2"></div>
        </div>
    {/each}
{:else if ...}
```

### 2.6 Hardcoded version in StatusBar — **Low**

**Files:** `frontend/src/lib/components/StatusBar.svelte:4`,
`frontend/vite.config.ts`, `frontend/package.json`

`const VERSION = '0.2.0'` will silently drift from `package.json` on the next
release.

**Fix:** inject at build time:

```ts
// vite.config.ts
import pkg from './package.json' with { type: 'json' };
export default defineConfig({
    define: { __APP_VERSION__: JSON.stringify(pkg.version) },
    ...
});
```

Declare `declare const __APP_VERSION__: string;` in `src/app.d.ts` and use it
in StatusBar.

### 2.7 PromptSettings double-fetches — **Low**

**File:** `frontend/src/lib/components/PromptSettings.svelte:35-42, 53-66`

`onMount` fetches settings even though the panel starts collapsed, then
`toggle()` fetches again on every expand. The mount fetch is wasted work on
every page load for a panel most visits never open.

**Fix:** delete the `onMount` block and fetch lazily on first expand only:

```ts
let loaded = false;
async function toggle() {
    expanded = !expanded;
    if (expanded && !loaded) {
        loading = true;
        try {
            applySettings(await fetchPromptSettings());
            loaded = true;
        } catch { toasts.error('Failed to load prompt settings'); }
        finally { loading = false; }
    }
}
```

(Refetching on every expand also clobbers unsaved edits if the user collapses
and reopens — the `loaded` flag fixes that too.)

---

## 3. Reported items found NOT to be issues

### Debounce on provider selector / date inputs (suggested item 16)

**Checked:** `SummaryPanel.svelte:106-147`, `lib/api.ts`

The provider `<select>`, date inputs, and author field only update local
`$state`; no API call fires until the Generate button is clicked. The single
mount-time `fetchProviders()` call (`SummaryPanel.svelte:40-48`) runs once.
There is nothing to debounce today — no change recommended. (If live
search-as-you-type over `/commits` is added later, debounce it then.)

---

## 4. Work tracker

| # | Item | Severity | Effort | Status |
| --- | --- | --- | --- | --- |
| 1 | 1.3 Skip fresh/filtered repos on ingest | High | S | ✅ Done — `perf/summary-ingest`, merged 2026-06-10 |
| 2 | 1.4 Bulk upsert in `_ingest_repo` | High | S | ✅ Done — `perf/summary-ingest`, merged 2026-06-10 |
| 3 | 1.2 Make combined AI summary opt-in | High | S | 🔄 In review — `perf/ai-summary` |
| 4 | 2.1 AbortController on generate | High | S | 🔄 In review — `perf/abort-controller` |
| 5 | 1.1 Parallelize per-repo LLM calls | High | M | 🔄 In review — `perf/ai-summary` |
| 6 | 2.2 Markdown: ordered lists, links, fences | High | M | 🔄 In review — `ui/markdown-render` |
| 7 | 1.5 + 1.6 Date column type + indexes (one migration) | Medium | M | ⬜ Not started |
| 8 | 1.8 Escape ILIKE wildcards / exact repo match | Medium | S | ⬜ Not started |
| 9 | 2.3 Date-range validation | Medium | S | ⬜ Not started |
| 10 | 1.7 Single session per request | Medium | M | ⬜ Not started |
| 11 | 2.4 Theme single source of truth | Medium | S | ⬜ Not started |
| 12 | 2.5 Loading skeletons | Medium | S | ⬜ Not started |
| 13 | 2.6 Build-time version | Low | S | ⬜ Not started |
| 14 | 2.7 Lazy-load prompt settings | Low | S | ⬜ Not started |
| 15 | 1.9 Unique repo name + FK cascade | Low | M | ⬜ Not started |
| 16 | 1.10 Background initial ingest | Low | S | ⬜ Not started |

Items 1–4 are each small, independent changes that remove the worst latency
and cost multipliers; doing just those four makes `/summary` roughly
`N×(fetch+LLM)` → `1×fetch + parallel LLM` for the common single-repo case.

### Implementation notes (deviations from the recommendations above)

- **PR `perf/summary-ingest`** (items 1.3 + 1.4, merged 2026-06-10): the
  freshness check is an in-process cache keyed by **(repo, since, until)**
  rather than the per-repo `last_ingested_at` TTL sketched in 1.3 — an ingest
  only covers its requested window, so a repo fetched for a 7-day summary is
  not fresh for a 30-day one and a pure per-repo TTL would silently return
  incomplete results. `last_ingested_at` is still updated for the UI. Failed
  ingests are not cached. Regression tests in `tests/test_ingest.py`, including
  a SELECT-count guard for the N+1.
- **PR `perf/ai-summary`** (items 1.1 partial + 1.2, in review): per-repo LLM
  calls run through a 4-worker `ThreadPoolExecutor`; the whole-log summary is
  gated behind `combined=false` with the response shape unchanged. Because the
  always-on combined call was what mapped provider misconfiguration to HTTP
  400, `ai=true` now validates the provider **up front** (unknown provider or
  missing key → 400 before any LLM work). The longer-term parts of 1.1
  (async endpoint, background ingest, streaming) remain open.
- **PR `perf/abort-controller`** (item 2.1, merged 2026-06-10): `generateSummary` in
  `api.ts` accepts an optional `signal?: AbortSignal` and passes it through to
  `fetch`. `SummaryPanel.svelte` tracks an `AbortController`, aborts the
  previous request before starting a new one, and silently ignores
  `AbortError` so superseded requests don't flash an error or overwrite the
  result with stale data.
- **PR `ui/markdown-render`** (item 2.2, in review): extended `markdown.ts`
  line loop with three cases — ordered lists (`^\s*\d+[.)]\s+`) emit `<ol>`
  with list-type tracking so switching between bullet/ordered closes and
  reopens correctly; fenced code blocks toggle an `inCode` flag and collect
  raw escaped lines into a single `<pre><code>` without running `inline()`;
  links in `inline()` match `\[text\]\(https?://url\)` and emit `<a>` with
  `rel="noopener noreferrer" target="_blank"`, rejecting non-http schemes.
  Tests cover all three features plus XSS safety inside code blocks.
