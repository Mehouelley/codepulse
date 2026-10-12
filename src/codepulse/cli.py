"""Command-line entry point for CodePulse."""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser

from . import analyzers
from .git_data import get_commits, is_git_repo
from .report import render


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codepulse",
        description="Reveal a codebase's health from its git history.",
    )
    parser.add_argument("repo", nargs="?", default=".", help="path to a git repository (default: current dir)")
    parser.add_argument("-o", "--output", default="codepulse-report.html", help="HTML report output path")
    parser.add_argument("--since", help='only commits after this date, e.g. "6 months ago"')
    parser.add_argument("--max-count", type=int, help="limit to the N most recent commits")
    parser.add_argument("--top", type=int, default=20, help="rows per table (default: 20)")
    parser.add_argument("--open", action="store_true", help="open the report in a browser when done")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = os.path.abspath(args.repo)

    if not is_git_repo(repo):
        print(f"error: '{repo}' is not a git repository.", file=sys.stderr)
        return 2

    print(f"Reading git history from {repo} ...")
    commits = get_commits(repo, since=args.since, max_count=args.max_count)
    if not commits:
        print("error: no commits found for the given filters.", file=sys.stderr)
        return 1
    print(f"  {len(commits)} commits")

    stats = analyzers.build_file_stats(commits, repo)
    summary = analyzers.summarize(commits, stats)
    hot = analyzers.hotspots(stats, limit=args.top)
    bus = analyzers.bus_factor_risks(stats, limit=args.top)
    coupled = analyzers.coupling(commits, stats, limit=args.top)

    html = render(
        repo_name=os.path.basename(repo.rstrip("/\\")) or repo,
        summary=summary,
        hotspots=hot,
        bus_risks=bus,
        coupling=coupled,
    )

    out = os.path.abspath(args.output)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)

    print(f"\nReport written to {out}")
    print(f"  {len(hot)} hotspots · {len(bus)} bus-factor risks · {len(coupled)} coupled pairs")

    if args.open:
        webbrowser.open(f"file://{out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
