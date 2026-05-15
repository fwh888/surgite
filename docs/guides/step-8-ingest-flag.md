# Step 8: Add `--ingest` to the CLI

**The instruction:** Add the `--ingest <url>` flag. When passed, POST to the API instead of printing. Requires Step 7 to exist first.

## What to add

This is a targeted change to `standup/standup.py`. Add one new argument and a branch in `main()`.

### New argument

```python
parser.add_argument(
    "--ingest",
    metavar="URL",
    help="POST commits to the API at this URL instead of printing (e.g. http://localhost:8000)"
)
```

### New branch in `main()`

After `commits = parse_log(raw_log)`, add:

```python
if args.ingest:
    import requests
    payload = {
        "repo_path": args.repo_path,
        "since": args.since,
        "until": args.until,
    }
    url = args.ingest.rstrip("/") + "/ingest"
    response = requests.post(url, json=payload)
    response.raise_for_status()
    result = response.json()
    print(f"Ingested into {result['repo']}: {result['inserted']} inserted, {result['updated']} updated, {result['unchanged']} unchanged")
    return
```

Place this block before the `if args.summarize:` block so that `--ingest` exits early and the rest of the print/summarize logic is skipped.

## Add `requests` to dependencies

`requests` isn't in `pyproject.toml` yet:

```toml
dependencies = [
    ...
    "requests>=2.32",
]
```

```bash
uv sync
```

## Updated `main()` — full picture

After the change, the flow in `main()` looks like:

```
parse args
→ get_raw_log()
→ parse_log()
→ if --ingest: POST to API, print result, return
→ format_log()
→ if --summarize: summarize_commits()
→ if --output: write to file, else print
```

## Test it

Make sure the API is running (`uv run uvicorn standup.api:app --reload`), then:

```bash
uv run standup /path/to/repo --since 2026-05-01 --ingest http://localhost:8000
```

Expected output:
```
Ingested into repo-name: 12 inserted, 0 updated, 3 unchanged
```

Confirm the data landed:
```bash
curl -s "http://localhost:8000/commits?since=2026-05-01" | python3 -m json.tool
```

Also confirm the existing flags still work without `--ingest` (no regression):
```bash
uv run standup /path/to/repo --since 2026-05-01
uv run standup /path/to/repo --since 2026-05-01 --output /tmp/out.txt
```

---

**Step 8 is done when:** `--ingest` POSTs to the API and prints the result, and all existing flags still work.

**Next:** [Step 9](step-9-automation.md) — write the ingest script and set up a nightly cron job or systemd timer.
