"""Extract commit history from a git repository.

This module shells out to ``git log`` and parses its output into plain
dataclasses. It has no third-party dependencies on purpose: anyone with git
and Python can run CodePulse without installing anything.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

# Delimiters chosen to be extremely unlikely to appear in commit metadata.
_UNIT = "\x1f"  # separates fields inside a commit header line
_REC = "--CP--"  # marks the start of a new commit record


@dataclass
class FileChange:
    """A single file touched by a commit."""

    path: str
    added: int
    deleted: int


@dataclass
class Commit:
    """One commit and the files it changed."""

    hash: str
    timestamp: int  # unix seconds (author date)
    author: str
    files: list[FileChange] = field(default_factory=list)


def _run_git(repo: str, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def is_git_repo(repo: str) -> bool:
    try:
        return _run_git(repo, ["rev-parse", "--is-inside-work-tree"]).strip() == "true"
    except Exception:
        return False


def normalize_path(path: str) -> str:
    """Resolve git rename notation to the current path.

    git numstat can emit renames as ``old => new`` or the compact
    ``dir/{old => new}/file`` form. We keep the *new* path so history
    accumulates onto the file as it exists today.
    """
    if "=>" in path:
        if "{" in path and "}" in path:
            prefix, rest = path.split("{", 1)
            inner, suffix = rest.split("}", 1)
            new = inner.split("=>", 1)[1].strip()
            path = f"{prefix}{new}{suffix}".replace("//", "/")
        else:
            path = path.split("=>", 1)[1].strip()
    return path.strip()


def get_changed_files(repo: str, ref_range: str) -> list[str]:
    """Return files changed for a diff spec.

    Accepts either a range ("main..HEAD", "main...HEAD") or a single ref
    ("origin/main", "HEAD~5"). A single ref is compared against the current
    working tree, so uncommitted changes count too — which is what a CI job or
    a pre-commit check usually wants.
    """
    out = _run_git(repo, ["diff", "--name-only", ref_range])
    return [normalize_path(line) for line in out.splitlines() if line.strip()]


def get_commits(repo: str, since: str | None = None, max_count: int | None = None) -> list[Commit]:
    """Return commits (newest first), excluding merges.

    ``since`` is passed straight to ``git --since`` (e.g. "6 months ago").
    """
    fmt = f"{_REC}%H{_UNIT}%at{_UNIT}%aN"
    args = ["log", "--no-merges", "--numstat", f"--pretty=format:{fmt}"]
    if since:
        args.append(f"--since={since}")
    if max_count:
        args.append(f"--max-count={max_count}")

    out = _run_git(repo, args)
    commits: list[Commit] = []
    current: Commit | None = None

    for line in out.splitlines():
        if line.startswith(_REC):
            parts = line[len(_REC):].split(_UNIT)
            if len(parts) == 3:
                current = Commit(hash=parts[0], timestamp=int(parts[1]), author=parts[2])
                commits.append(current)
            continue
        if not line.strip() or current is None:
            continue
        cols = line.split("\t")
        if len(cols) != 3:
            continue
        added_s, deleted_s, path = cols
        # Binary files report "-" instead of a count.
        added = int(added_s) if added_s.isdigit() else 0
        deleted = int(deleted_s) if deleted_s.isdigit() else 0
        current.files.append(FileChange(path=normalize_path(path), added=added, deleted=deleted))

    return commits
