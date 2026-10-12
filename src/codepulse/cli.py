"""Command-line entry point for CodePulse.

Two modes:

* **Report** (default) — full HTML health dashboard for a repo.
* **Risk gate** (``--changed <ref>``) — score only the files changed since a
  ref, emit JSON or text, and set an exit code so CI can warn or block.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser

from . import analyzers
from .git_data import get_changed_files, get_commits, is_git_repo
from .report import render

_LEVELS = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


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
    parser.add_argument("--open", action="store_true", help="open the HTML report in a browser when done")
    parser.add_argument("--ignore", action="append", metavar="GLOB", default=[],
                        help="exclude paths matching this glob (repeatable), e.g. '*.sql'")
    parser.add_argument("--no-default-ignore", action="store_true",
                        help="don't exclude the built-in generated/data file patterns")

    gate = parser.add_argument_group("risk gate (CI)")
    gate.add_argument("--changed", metavar="REF",
                      help='score files changed since REF (e.g. "origin/main" or "HEAD~10..HEAD")')
    gate.add_argument("--format", choices=["text", "json", "markdown"], default="text",
                      help="risk-gate output format (default: text)")
    gate.add_argument("--fail-on", choices=["LOW", "MEDIUM", "HIGH"],
                      help="exit with code 1 if release risk reaches this level")
    return parser


def _ignore_patterns(args: argparse.Namespace) -> list[str]:
    base = [] if args.no_default_ignore else list(analyzers.DEFAULT_IGNORE)
    return base + list(args.ignore)


def _run_report(repo: str, args: argparse.Namespace) -> int:
    print(f"Reading git history from {repo} ...")
    commits = get_commits(repo, since=args.since, max_count=args.max_count)
    if not commits:
        print("error: no commits found for the given filters.", file=sys.stderr)
        return 1
    commits = analyzers.filter_commits(commits, _ignore_patterns(args))
    print(f"  {len(commits)} commits")

    stats = analyzers.build_file_stats(commits, repo)
    hot = analyzers.hotspots(stats, limit=args.top)
    hotspot_paths = {h.path for h in analyzers.hotspots(stats, limit=15)}
    html = render(
        repo_name=os.path.basename(repo.rstrip("/\\")) or repo,
        summary=analyzers.summarize(commits, stats),
        hotspots=hot,
        bus_risks=analyzers.bus_factor_risks(stats, limit=args.top),
        coupling=analyzers.coupling(commits, stats, limit=args.top),
        trend=analyzers.monthly_trend(commits, hotspot_paths),
    )

    out = os.path.abspath(args.output)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"\nReport written to {out}")
    if args.open:
        webbrowser.open(f"file://{out}")
    return 0


def _run_gate(repo: str, args: argparse.Namespace) -> int:
    commits = get_commits(repo, since=args.since, max_count=args.max_count)
    if not commits:
        print("error: no commits found to build a risk map.", file=sys.stderr)
        return 1
    patterns = _ignore_patterns(args)
    commits = analyzers.filter_commits(commits, patterns)
    stats = analyzers.build_file_stats(commits, repo)
    changed = [p for p in get_changed_files(repo, args.changed) if not analyzers.is_ignored(p, patterns)]
    risk = analyzers.release_risk(changed, stats)
    known_count, reviewers = analyzers.suggested_reviewers(changed, stats)

    def _reviewer_label(r):
        return f"{r.name} ({r.files_known}/{known_count} fichiers)"

    icons = {"HIGH": "🔴", "MEDIUM": "🟠", "LOW": "🟢"}

    if args.format == "json":
        payload = {
            "level": risk.level,
            "score": risk.score,
            "high_risk_count": risk.high_risk_count,
            "changed_files": len(risk.files),
            "files": [
                {"path": f.path, "risk": f.risk, "commits": f.commits, "loc": f.loc, "reasons": f.reasons}
                for f in risk.files
            ],
            "suggested_reviewers": [
                {"name": r.name, "files_known": r.files_known, "commits": r.commits} for r in reviewers
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.format == "markdown":
        # A sticky PR comment. The marker lets a CI step find and update it.
        lines = [
            "<!-- codepulse -->",
            f"## 🩺 CodePulse — Risque : {icons[risk.level]} **{risk.level}** ({risk.score}/100)",
            "",
            f"**{len(risk.files)} fichiers modifiés · {risk.high_risk_count} à risque élevé**",
            "",
        ]
        scored = [f for f in risk.files if f.risk > 0]
        if scored:
            lines += ["| Risque | Fichier | Pourquoi |", "|---:|---|---|"]
            for f in scored[:12]:
                lines.append(f"| {f.risk} | `{f.path}` | {', '.join(f.reasons)} |")
        else:
            lines.append("_Aucun fichier à risque touché._ ✅")
        if reviewers:
            lines += ["", "**👥 Relecteurs suggérés** (d'après l'historique) : "
                      + ", ".join(_reviewer_label(r) for r in reviewers)]
        lines += [
            "",
            "<sub>Score basé sur l'historique du dépôt. Risque élevé = touche un hotspot connu ou un fichier à auteur unique.</sub>",
        ]
        print("\n".join(lines))
    else:
        print(f"{icons[risk.level]} Release risk: {risk.level} ({risk.score}/100)")
        print(f"   {len(risk.files)} changed files · {risk.high_risk_count} high-risk")
        for f in risk.files:
            if f.risk > 0:
                print(f"   [{f.risk:3}] {f.path}  ({', '.join(f.reasons)})")
        if reviewers:
            print("   👥 Relecteurs suggérés: " + ", ".join(_reviewer_label(r) for r in reviewers))

    if args.fail_on and _LEVELS[risk.level] >= _LEVELS[args.fail_on]:
        print(f"\nRisk level {risk.level} >= threshold {args.fail_on} — failing.", file=sys.stderr)
        return 1
    return 0


def _force_utf8() -> None:
    # Windows consoles default to cp1252 and choke on emoji/box-drawing output.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    args = build_parser().parse_args(argv)
    repo = os.path.abspath(args.repo)

    if not is_git_repo(repo):
        print(f"error: '{repo}' is not a git repository.", file=sys.stderr)
        return 2

    return _run_gate(repo, args) if args.changed else _run_report(repo, args)


if __name__ == "__main__":
    raise SystemExit(main())
