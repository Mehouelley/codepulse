"""Command-line entry point for CodePulse.

Two modes:

* **Report** (default) — full HTML health dashboard for a repo.
* **Risk gate** (``--changed <ref>``) — score only the files changed since a
  ref, emit JSON or text, and set an exit code so CI can warn or block.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import webbrowser
from urllib.parse import quote

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
    parser.add_argument("--who", metavar="PATH",
                        help="show who knows a file best (from git history) and exit")
    parser.add_argument("--badge", action="store_true",
                        help="print a shields.io health-badge snippet and exit")

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
    summary = analyzers.summarize(commits, stats)
    hot = analyzers.hotspots(stats, limit=args.top)
    bus = analyzers.bus_factor_risks(stats, limit=args.top)
    hotspot_paths = {h.path for h in analyzers.hotspots(stats, limit=15)}
    trend = analyzers.monthly_trend(commits, hotspot_paths)
    coupled = analyzers.coupling(commits, stats, limit=args.top)
    stale = analyzers.stale_risks(stats, summary.last_timestamp, limit=args.top)
    recs = analyzers.recommendations(commits, hot, bus, coupled, trend, stale)

    html = render(
        repo_name=os.path.basename(repo.rstrip("/\\")) or repo,
        summary=summary,
        hotspots=hot,
        bus_risks=bus,
        coupling=coupled,
        trend=trend,
        stale=stale,
        recommendations=recs,
    )

    out = os.path.abspath(args.output)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"\nReport written to {out}")
    if recs:
        print("\nRecommandations :")
        for i, r in enumerate(recs, 1):
            print(f"  {i}. {r.icon} {r.title.replace('`', '')}")
            print(f"     {r.action.replace('`', '')}")
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


def _load_stats(repo: str, args: argparse.Namespace):
    commits = get_commits(repo, since=args.since, max_count=args.max_count)
    if not commits:
        return None, None
    commits = analyzers.filter_commits(commits, _ignore_patterns(args))
    return commits, analyzers.build_file_stats(commits, repo)


def _run_who(repo: str, args: argparse.Namespace) -> int:
    commits, stats = _load_stats(repo, args)
    if not commits:
        print("error: no commits found.", file=sys.stderr)
        return 1
    matches = analyzers.find_files(stats, args.who)
    if not matches:
        print(f"Aucun fichier suivi ne correspond à '{args.who}'.", file=sys.stderr)
        return 1
    if len(matches) > 1:
        print(f"Plusieurs fichiers correspondent à '{args.who}' — précise le chemin :")
        for m in matches[:20]:
            print(f"  {m}")
        return 1

    s = stats[matches[0]]
    total = sum(s.authors.values())
    last = datetime.datetime.fromtimestamp(s.last_timestamp).strftime("%Y-%m-%d")
    print(f"{s.path} — {s.commits} commits, {s.num_authors} auteur(s), dernier changement {last}")
    for author, n in s.authors.most_common(8):
        print(f"  {round(n / total * 100):>3}%  {n:>3} commits  {author}")
    if s.num_authors == 1:
        print("  ⚠️ Un seul auteur — risque de bus factor.")
    return 0


def _run_badge(repo: str, args: argparse.Namespace) -> int:
    commits, stats = _load_stats(repo, args)
    if not commits:
        print("error: no commits found.", file=sys.stderr)
        return 1
    summary = analyzers.summarize(commits, stats)
    hotspot_paths = {h.path for h in analyzers.hotspots(stats, limit=15)}
    trend = analyzers.monthly_trend(commits, hotspot_paths)
    health = analyzers.health_grade(stats, summary, trend)

    message = f"{health.grade} ({health.score})"
    static = f"https://img.shields.io/badge/{quote('code health')}-{quote(message)}-{health.color}"
    print(f"Grade: {health.grade} ({health.score}/100)")
    for r in health.reasons:
        print(f"  {r}")
    print("\nMarkdown (copie dans ton README) :")
    print(f"![code health]({static})")
    print("\nJSON (endpoint shields.io, si tu héberges ce fichier) :")
    print(json.dumps({"schemaVersion": 1, "label": "code health", "message": message, "color": health.color},
                     ensure_ascii=False))
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

    if args.who:
        return _run_who(repo, args)
    if args.badge:
        return _run_badge(repo, args)
    if args.changed:
        return _run_gate(repo, args)
    return _run_report(repo, args)


if __name__ == "__main__":
    raise SystemExit(main())
