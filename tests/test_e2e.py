"""End-to-end: build a real git repo, run the full pipeline against it."""

import os
import subprocess

import pytest

from codepulse import analyzers
from codepulse.git_data import get_commits, is_git_repo

# Fixed dates keep the history deterministic; inherit the real env so git still
# finds PATH/SYSTEMROOT etc. on every OS.
_ENV = {**os.environ, "GIT_AUTHOR_DATE": "2026-01-01T00:00:00", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00"}


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=_ENV)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "dev@test.local")
    _git(r, "config", "user.name", "Dev")

    (r / "hot.py").write_text("def f():\n    pass\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "init")
    # Churn hot.py repeatedly so it becomes the top hotspot.
    for i in range(4):
        (r / "hot.py").write_text(f"def f():\n    if x{i}:\n        pass\n")
        _git(r, "add", "-A")
        _git(r, "commit", "-q", "-m", f"change {i}")
    return r


def test_is_git_repo(repo, tmp_path):
    assert is_git_repo(str(repo))
    assert not is_git_repo(str(tmp_path))


def test_pipeline_finds_hotspot(repo):
    commits = get_commits(str(repo))
    assert len(commits) == 5
    stats = analyzers.build_file_stats(commits, str(repo))
    top = analyzers.hotspots(stats)
    assert top[0].path == "hot.py"
    assert top[0].commits == 5
    assert top[0].complexity >= 2  # the "if" was counted


def test_pipeline_summary(repo):
    commits = get_commits(str(repo))
    stats = analyzers.build_file_stats(commits, str(repo))
    summary = analyzers.summarize(commits, stats)
    assert summary.total_commits == 5
    assert summary.contributors == 1
