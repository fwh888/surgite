# Step 9: Automate nightly ingestion

**The instruction:** Write a shell script that calls `POST /ingest` for each repo. Set up a systemd timer or cron job to run it nightly.

## 1. Create `ingest_all.sh`

Create this file in the project root:

```bash
#!/bin/bash
set -euo pipefail

REPOS=(
  "/Users/nicholas/dev/Arbiter"
  "/Users/nicholas/dev/standup-gen"
)

API_URL="http://localhost:8000"
SINCE=$(date -v-7d +%F)   # macOS date syntax; use $(date -d '7 days ago' +%F) on Linux

for repo in "${REPOS[@]}"; do
  echo "Ingesting $repo..."
  curl -s -X POST "$API_URL/ingest" \
    -H "Content-Type: application/json" \
    -d "{\"repo_path\": \"$repo\", \"since\": \"$SINCE\"}" \
    | python3 -m json.tool
done
```

Make it executable:

```bash
chmod +x ingest_all.sh
```

Test it manually with the API running:

```bash
./ingest_all.sh
```

## 2. Add repos as needed

To add a repo, add its path to the `REPOS` array. The repo name in the database is derived from the last path component (e.g. `/Users/nicholas/dev/Arbiter` → `Arbiter`), which is handled by `POST /ingest` in `api.py`.

## 3. Set up a nightly schedule

You're on macOS, so you have two options: **cron** (simpler) or **launchd** (the macOS-native way).

### Option A: cron (simpler)

```bash
crontab -e
```

Add this line to run at 11 PM every night:

```
0 23 * * * /Users/nicholas/dev/standup-gen/ingest_all.sh >> /Users/nicholas/dev/standup-gen/ingest.log 2>&1
```

The `>> ... 2>&1` part appends stdout and stderr to a log file so you can debug failures.

### Option B: launchd (macOS-native, runs even after sleep/wake)

Create `~/Library/LaunchAgents/com.nicholas.standup-ingest.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.nicholas.standup-ingest</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/nicholas/dev/standup-gen/ingest_all.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>23</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/nicholas/dev/standup-gen/ingest.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/nicholas/dev/standup-gen/ingest.log</string>
</dict>
</plist>
```

Load it:

```bash
launchctl load ~/Library/LaunchAgents/com.nicholas.standup-ingest.plist
```

Verify it's registered:

```bash
launchctl list | grep standup
```

To unload it later:

```bash
launchctl unload ~/Library/LaunchAgents/com.nicholas.standup-ingest.plist
```

## 4. Keep the API running

The script only works if the API is up when the cron/launchd fires. For a local dev machine, the simplest approach is to start the API manually when you need it. If you want it to always be available, add a second launchd plist that starts `uvicorn` on login — but that's out of scope for the initial build.

## What you're not doing yet (post-v1 ideas)

These are from the upgrade plan's extension ideas section — skip them for now:
- `PATCH /commits/{hash}/tags`
- `GET /summary?format=markdown`
- `--watch` mode on the CLI

---

**Step 9 is done when:** `ingest_all.sh` runs cleanly against the live API, and a cron or launchd entry fires it nightly.

**The upgrade is complete.** You now have:
- A CLI that prints, summarizes, and ingests
- A REST API with four routes
- A Postgres database with Alembic migrations
- Automated nightly ingestion
