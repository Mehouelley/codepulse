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

from .git_data import Commit


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
