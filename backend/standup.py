import argparse
import os
import sys
from datetime import date, timedelta

import httpx
from dotenv import load_dotenv

from backend import cli_auth
from backend.formatter import format_log
from backend.git import get_raw_log, parse_log
from backend.summarizer import summarize_commits


def _api_base() -> str:
    return os.environ.get("STANDUP_API_URL", "http://localhost:8000").rstrip("/")


def _run_local(args) -> str:
    """Summarize a local repo path — the standalone, no-server path."""
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
    return summary


def _run_registered(args) -> str:
    """Pull a registered repo's data from a running standup-gen API instead of
    a local clone. URL from STANDUP_API_URL. Auth (multi_user deployments) via
    a saved session cookie (`standup --login` / `--redeem-invite`) or
    STANDUP_API_KEY; off/single_user deployments need none. Mirrors what the
    web UI shows for the same repo."""
    base = _api_base()
    headers = cli_auth.auth_headers(base)

    # The API filters by date, not git's relative syntax. Default to the last
    # 7 days to match the local path's default window.
    since = args.since or (date.today() - timedelta(days=7)).isoformat()
    params: dict[str, str] = {"repo": args.registered, "since": since}
    if args.until:
        params["until"] = args.until
    if args.author:
        params["author"] = args.author
    if args.summarize:
        params["ai"] = "true"

    resp = httpx.get(f"{base}/summary", params=params, headers=headers, timeout=180)
    resp.raise_for_status()
    data = resp.json()

    if args.summarize:
        sections = data.get("ai_summaries") or {}
        parts = [f"## {repo}\n{s['summary']}" for repo, s in sections.items()]
    else:
        parts = list((data.get("log_by_repo") or {}).values())
    return "\n\n".join(p for p in parts if p.strip()) or "No commits in this period."


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Generate a standup summary from git log.")
    parser.add_argument("repo_path", nargs="?", help="Path to a local git repository")
    parser.add_argument(
        "--registered",
        metavar="NAME",
        help="Pull a repo registered in a running standup-gen API "
        "(set STANDUP_API_URL; auth via `standup --login` or STANDUP_API_KEY) "
        "instead of a local path",
    )

    auth_group = parser.add_argument_group("auth (multi_user deployments)")
    auth_group.add_argument(
        "--login", action="store_true", help="Log in to the API and save a session"
    )
    auth_group.add_argument(
        "--logout", action="store_true", help="Revoke and forget the saved session"
    )
    auth_group.add_argument(
        "--redeem-invite",
        metavar="TOKEN",
        help="Redeem an invite token: create an account and log in",
    )
    auth_group.add_argument("--email", help="Email for --login / --redeem-invite (or prompt)")

    since_group = parser.add_mutually_exclusive_group()
    since_group.add_argument("--since", help="Start date for git log (default: 7.days.ago)")
    since_group.add_argument("--since-commit", help="Starting commit hash (overrides --since)")
    parser.add_argument("--until", help="End date or commit ref for git log (default: now)")
    parser.add_argument("--author", help="Filter commits by author (optional)")
    parser.add_argument("--output", help="Output file for the summary (optional)")
    parser.add_argument(
        "--summarize", action="store_true", help="Summarize the commit messages with AI. (optional)"
    )

    args = parser.parse_args()

    # Auth subcommands short-circuit before the repo/summary path.
    if args.login or args.logout or args.redeem_invite:
        if sum(bool(x) for x in (args.login, args.logout, args.redeem_invite)) > 1:
            parser.error("use only one of --login, --logout, --redeem-invite")
        base = _api_base()
        if args.login:
            sys.exit(cli_auth.cmd_login(base, email=args.email))
        if args.logout:
            sys.exit(cli_auth.cmd_logout(base))
        sys.exit(cli_auth.cmd_redeem_invite(base, args.redeem_invite, email=args.email))

    if bool(args.repo_path) == bool(args.registered):
        parser.error("provide either a repo_path or --registered <name>, not both")
    if args.registered and args.since_commit:
        parser.error("--since-commit is only supported for a local repo_path")

    summary = _run_registered(args) if args.registered else _run_local(args)

    if args.output:
        with open(args.output, "w") as f:
            f.write(summary)
    else:
        print(summary)


if __name__ == "__main__":
    main()
