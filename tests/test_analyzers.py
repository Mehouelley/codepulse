from collections import Counter

from codepulse import analyzers
from codepulse.analyzers import FileStat
from codepulse.git_data import Commit, FileChange

DAY = 86400


def stat(path, commits, authors, complexity=10, exists=True, loc=100):
    return FileStat(
        path=path,
        commits=commits,
        authors=Counter(authors),
        complexity=complexity,
        loc=loc,
        exists=exists,
    )


# --- ignore patterns -------------------------------------------------------

def test_is_ignored_matches_basename_and_path():
    assert analyzers.is_ignored("a/b/Cargo.lock", analyzers.DEFAULT_IGNORE)
    assert analyzers.is_ignored("x/node_modules/y.js", analyzers.DEFAULT_IGNORE)
    assert not analyzers.is_ignored("src/app.py", analyzers.DEFAULT_IGNORE)


def test_is_ignored_custom_glob():
    assert analyzers.is_ignored("a/b.test.js", ["*.test.js"])


def test_filter_commits_drops_ignored_but_keeps_commit():
    c = Commit("h", 0, "A", files=[FileChange("app.py", 1, 0), FileChange("x.lock", 5, 0)])
    out = analyzers.filter_commits([c], ["*.lock"])
    assert len(out) == 1
    assert [f.path for f in out[0].files] == ["app.py"]


# --- hotspots --------------------------------------------------------------

def test_hotspots_ranked_by_commits_times_complexity():
    stats = {
        "big_simple": stat("big_simple", commits=10, authors={"A": 10}, complexity=5),
        "small_dense": stat("small_dense", commits=10, authors={"A": 10}, complexity=50),
    }
    top = analyzers.hotspots(stats)
    assert top[0].path == "small_dense"  # dense wins over big-but-simple


def test_hotspots_skip_deleted_files():
    stats = {"gone": stat("gone", 10, {"A": 10}, exists=False)}
    assert analyzers.hotspots(stats) == []


# --- bus factor ------------------------------------------------------------

def test_bus_factor_flags_single_author():
    stats = {
        "solo": stat("solo", commits=4, authors={"A": 4}),
        "shared": stat("shared", commits=5, authors={"A": 3, "B": 2}),
        "rare": stat("rare", commits=2, authors={"A": 2}),  # below min_commits
    }
    risks = analyzers.bus_factor_risks(stats)
    paths = [r.path for r in risks]
    assert paths == ["solo"]


# --- coupling --------------------------------------------------------------

def test_coupling_detects_co_changes():
    commits = [
        Commit(str(i), i, "A", files=[FileChange("a.py", 1, 0), FileChange("b.py", 1, 0)])
        for i in range(4)
    ]
    stats = {"a.py": stat("a.py", 4, {"A": 4}), "b.py": stat("b.py", 4, {"A": 4})}
    pairs = analyzers.coupling(commits, stats)
    assert len(pairs) == 1
    assert {pairs[0].a, pairs[0].b} == {"a.py", "b.py"}
    assert pairs[0].degree == 1.0


# --- release risk ----------------------------------------------------------

def test_release_risk_high_for_hotspot_single_owner():
    stats = {"hot.py": stat("hot.py", commits=10, authors={"A": 10}, complexity=100)}
    risk = analyzers.release_risk(["hot.py"], stats)
    assert risk.level == "HIGH"
    assert risk.score == 100
    assert any("auteur unique" in r for r in risk.files[0].reasons)


def test_suggested_reviewers_ranks_by_coverage_then_depth():
    stats = {
        "a.py": stat("a.py", 5, {"Alice": 4, "Bob": 1}),
        "b.py": stat("b.py", 3, {"Alice": 3}),
        "c.py": stat("c.py", 2, {"Bob": 2}),
    }
    known, reviewers = analyzers.suggested_reviewers(["a.py", "b.py", "c.py"], stats)
    assert known == 3
    # Alice knows 2 of 3 files -> ranks first; Bob knows 2 as well but fewer... check
    assert reviewers[0].name == "Alice"
    assert reviewers[0].files_known == 2


def test_suggested_reviewers_ignores_unknown_files():
    stats = {"a.py": stat("a.py", 5, {"Alice": 5})}
    known, reviewers = analyzers.suggested_reviewers(["a.py", "new.py"], stats)
    assert known == 1
    assert reviewers[0].name == "Alice"


def test_release_risk_low_for_new_file():
    stats = {"hot.py": stat("hot.py", 10, {"A": 10}, complexity=100)}
    risk = analyzers.release_risk(["brand_new.py"], stats)
    assert risk.level == "LOW"
    assert risk.score == 0


# --- trend -----------------------------------------------------------------

def test_trend_detects_rising_hotspot_pressure():
    commits = []
    for d in range(8):
        path = "cold.py" if d < 4 else "hot.py"  # pressure shifts onto the hotspot
        commits.append(Commit(str(d), d * DAY, "A", files=[FileChange(path, 1, 0)]))
    trend = analyzers.monthly_trend(commits, hotspot_paths={"hot.py"})
    assert trend.granularity == "jour"
    assert trend.direction == "up"
    assert len(trend.buckets) == 8
