import argparse
from standup.git import get_raw_log, parse_log
from standup.formatter import format_log
from standup.summarizer import summarize_commits
from dotenv import load_dotenv

def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Generate a standup summary from git log.")
    parser.add_argument("repo_path", help="Path to the git repository")
    since_group = parser.add_mutually_exclusive_group()
    since_group.add_argument("--since", default="7.days.ago", help="Start date for git log (default: 7.days.ago)")
    since_group.add_argument("--since-commit", help="Starting commit hash (overrides --since)")
    parser.add_argument("--until", default="now", help="End date or commit ref for git log (default: now)")
    parser.add_argument("--author", help="Filter commits by author (optional)")
    parser.add_argument("--output", help="Output file for the summary (optional)")
    parser.add_argument("--summarize", action="store_true", help="Summarize the commit messages with AI. (optional)") # action="store_true" means args.summarize is True if the flag is passed, False otherwise.

    args = parser.parse_args()
    raw_log = get_raw_log(args.repo_path, args.since, args.until, args.author, args.since_commit)
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