import argparse
from standup.git import get_raw_log, parse_log
from standup.formatter import format_log
from standup.summarizer import summarize_commits
from dotenv import load_dotenv
import requests

def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Generate a standup summary from git log.")
    parser.add_argument("repo_path", help="Path to the git repository")
    since_group = parser.add_mutually_exclusive_group()
    since_group.add_argument("--since", help="Start date for git log (default: 7.days.ago)")
    since_group.add_argument("--since-commit", help="Starting commit hash (overrides --since)")
    parser.add_argument("--until", help="End date or commit ref for git log (default: now)")
    parser.add_argument("--author", help="Filter commits by author (optional)")
    parser.add_argument("--output", help="Output file for the summary (optional)")
    # action="store_true" means args.summarize is True if the flag is passed, False otherwise.
    parser.add_argument("--summarize", action="store_true", help="Summarize the commit messages with AI. (optional)")
    parser.add_argument(
        "--ingest",
        metavar="URL",
        help="POST commits to the API at this URL instead of printing (e.g. http://localhost:8000) (optional)"
    )


    args = parser.parse_args()

    if args.ingest:
        payload = {"repo_path": args.repo_path}
        if args.since:
            payload["since"] = args.since
        if args.until:
            payload["until"] = args.until
        url = args.ingest.rstrip("/") + "/ingest"
        response = requests.post(url, json=payload)
        response.raise_for_status()
        result = response.json()
        print(f"Ingested into {result['repo']}: {result['inserted']} inserted, {result['updated']} updated, {result['unchanged']} unchanged")
        return

    raw_log = get_raw_log(
        args.repo_path,
        args.since or "7.days.ago",
        args.until or "now",
        args.author,
        args.since_commit,
    )
    commits = parse_log(raw_log)

    summary = format_log(commits)
    if args.summarize:
        summary = summarize_commits(summary)
    if args.output:
        with open(args.output, "w") as f:
            f.write(summary)
    else:
        print(summary)

if __name__ == "__main__":
    main()