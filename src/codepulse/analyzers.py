"""Turn raw commit history into code-health signals.

The headline idea: history reveals things static linters can't. A file that
is both *complex* and *changed constantly* is where bugs are born. A file only
one person ever touches is a staffing risk. Files that always change together
are secretly coupled.
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from fnmatch import fnmatch

from .git_data import Commit

# Files that are generated, vendored, or pure data — real churn, but not code
# whose health tells you anything. Excluded by default so they don't crowd out
# the files that actually matter.
DEFAULT_IGNORE: tuple[str, ...] = (
    "*.lock", "Cargo.lock", "package-lock.json", "yarn.lock",
    "pnpm-lock.yaml", "poetry.lock", "composer.lock", "Gemfile.lock",
    "*.tsv", "*.csv",
    "*.min.js", "*.min.css", "*.map", "*.snap",
    "node_modules/*", "*/node_modules/*",
    "dist/*", "*/dist/*", "build/*", "*/build/*",
    "vendor/*", "*/vendor/*", "*/.next/*",
)


def is_ignored(path: str, patterns) -> bool:
    """True if the path matches any glob pattern (whole path or basename)."""
    base = path.rsplit("/", 1)[-1]
    return any(fnmatch(path, p) or fnmatch(base, p) for p in patterns)


def filter_commits(commits: list[Commit], patterns) -> list[Commit]:
    """Drop ignored files from each commit, keeping the commit itself.

    The commit still counts toward totals and author activity; only its ignored
    file changes are removed, so hotspots/coupling/bus-factor ignore them too.
    """
    if not patterns:
        return commits
    out: list[Commit] = []
    for c in commits:
        kept = [fc for fc in c.files if not is_ignored(fc.path, patterns)]
        out.append(Commit(hash=c.hash, timestamp=c.timestamp, author=c.author, files=kept))
    return out


@dataclass
class FileStat:
    """Accumulated history for a single file path."""

    path: str
    commits: int = 0
    authors: Counter = field(default_factory=Counter)  # author -> commits
    added: int = 0
    deleted: int = 0
    last_timestamp: int = 0
    loc: int = 0  # current line count in the working tree
    exists: bool = True  # still present on disk?

    @property
    def num_authors(self) -> int:
        return len(self.authors)

    @property
    def main_owner(self) -> tuple[str | None, float]:
        """Top contributor and their share of this file's commits."""
        if not self.authors:
            return None, 0.0
        owner, count = self.authors.most_common(1)[0]
        total = sum(self.authors.values())
        return owner, count / total

    @property
    def hotspot_score(self) -> int:
        """Change frequency x size. High = complex AND churned."""
        return self.commits * self.loc


def _count_lines(path: str) -> int:
    try:
        with open(path, "rb") as fh:
            return sum(1 for _ in fh)
    except Exception:
        return 0


def build_file_stats(commits: list[Commit], repo: str) -> dict[str, FileStat]:
    stats: dict[str, FileStat] = {}
    for commit in commits:
        for change in commit.files:
            stat = stats.get(change.path)
            if stat is None:
                stat = FileStat(path=change.path)
                stats[change.path] = stat
            stat.commits += 1
            stat.authors[commit.author] += 1
            stat.added += change.added
            stat.deleted += change.deleted
            stat.last_timestamp = max(stat.last_timestamp, commit.timestamp)

    for stat in stats.values():
        full = os.path.join(repo, stat.path.replace("/", os.sep))
        if os.path.isfile(full):
            stat.loc = _count_lines(full)
            stat.exists = True
        else:
            stat.exists = False

    return stats


def hotspots(stats: dict[str, FileStat], limit: int = 20) -> list[FileStat]:
    present = [s for s in stats.values() if s.exists and s.loc > 0]
    present.sort(key=lambda s: s.hotspot_score, reverse=True)
    return present[:limit]


def bus_factor_risks(stats: dict[str, FileStat], limit: int = 20, min_commits: int = 3) -> list[FileStat]:
    """Files actively maintained by exactly one person."""
    risky = [
        s for s in stats.values()
        if s.exists and s.commits >= min_commits and s.num_authors == 1
    ]
    risky.sort(key=lambda s: s.commits, reverse=True)
    return risky[:limit]


@dataclass
class CouplingPair:
    a: str
    b: str
    shared: int  # commits where both changed
    degree: float  # shared / min(individual commit counts)


def coupling(
    commits: list[Commit],
    stats: dict[str, FileStat],
    limit: int = 20,
    min_shared: int = 3,
    max_files_per_commit: int = 30,
) -> list[CouplingPair]:
    """Pairs of files that tend to change together.

    Commits touching a huge number of files (bulk reformat, vendoring) are
    skipped so they don't drown real coupling in noise.
    """
    pair_counts: Counter = Counter()
    file_commits: Counter = Counter()

    for commit in commits:
        paths = sorted({fc.path for fc in commit.files})
        if len(paths) > max_files_per_commit:
            continue
        for path in paths:
            file_commits[path] += 1
        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                pair_counts[(paths[i], paths[j])] += 1

    results: list[CouplingPair] = []
    for (a, b), shared in pair_counts.items():
        if shared < min_shared:
            continue
        sa, sb = stats.get(a), stats.get(b)
        if not sa or not sb or not sa.exists or not sb.exists:
            continue
        degree = shared / min(file_commits[a], file_commits[b])
        results.append(CouplingPair(a=a, b=b, shared=shared, degree=degree))

    results.sort(key=lambda p: (p.degree, p.shared), reverse=True)
    return results[:limit]


@dataclass
class ChangedFileRisk:
    path: str
    risk: int  # 0-100
    commits: int
    loc: int
    reasons: list[str]


@dataclass
class ReleaseRisk:
    """Risk of shipping a specific set of changed files.

    A release is treated as roughly as risky as its riskiest file, with the
    count of high-risk files raising the overall level — this maps directly to
    DORA's change-failure-rate concern.
    """

    files: list[ChangedFileRisk]
    score: int  # 0-100, overall
    level: str  # LOW | MEDIUM | HIGH
    high_risk_count: int


_HIGH, _MEDIUM = 70, 40


def _level(score: int) -> str:
    if score >= _HIGH:
        return "HIGH"
    if score >= _MEDIUM:
        return "MEDIUM"
    return "LOW"


def release_risk(changed: list[str], stats: dict[str, FileStat]) -> ReleaseRisk:
    """Score a set of changed paths against the repo's accumulated risk map."""
    max_score = max((s.hotspot_score for s in stats.values() if s.exists), default=0)

    files: list[ChangedFileRisk] = []
    for path in changed:
        stat = stats.get(path)
        if stat is None or not stat.exists:
            # New or untracked file: no history to judge it by.
            files.append(ChangedFileRisk(path=path, risk=0, commits=0, loc=0, reasons=["nouveau / sans historique"]))
            continue

        risk = round(stat.hotspot_score / max_score * 100) if max_score else 0
        reasons: list[str] = []
        if risk >= _HIGH:
            reasons.append("hotspot majeur")
        elif risk >= _MEDIUM:
            reasons.append("zone active")
        if stat.commits >= 3 and stat.num_authors == 1:
            owner = stat.main_owner[0]
            reasons.append(f"auteur unique ({owner})")
            risk = min(100, risk + 10)  # single-owner changes are riskier to review
        files.append(ChangedFileRisk(path=path, risk=risk, commits=stat.commits, loc=stat.loc, reasons=reasons or ["—"]))

    files.sort(key=lambda f: f.risk, reverse=True)
    score = files[0].risk if files else 0
    high = sum(1 for f in files if f.risk >= _HIGH)
    # Several risky files in one release pushes the ceiling up a tier.
    if high >= 2:
        score = max(score, _HIGH)
    return ReleaseRisk(files=files, score=score, level=_level(score), high_risk_count=high)


@dataclass
class Summary:
    total_commits: int
    tracked_files: int
    active_files: int  # still present on disk
    contributors: int
    first_timestamp: int
    last_timestamp: int
    top_contributors: list[tuple[str, int]]


def summarize(commits: list[Commit], stats: dict[str, FileStat]) -> Summary:
    author_commits: Counter = Counter(c.author for c in commits)
    timestamps = [c.timestamp for c in commits] or [0]
    return Summary(
        total_commits=len(commits),
        tracked_files=len(stats),
        active_files=sum(1 for s in stats.values() if s.exists),
        contributors=len(author_commits),
        first_timestamp=min(timestamps),
        last_timestamp=max(timestamps),
        top_contributors=author_commits.most_common(8),
    )
