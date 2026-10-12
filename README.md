# 🩺 CodePulse

[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-CodePulse-2088FF?logo=github&logoColor=white)](https://github.com/marketplace/actions/codepulse-risk-gate)
[![tests](https://github.com/Mehouelley/codepulse/actions/workflows/tests.yml/badge.svg)](https://github.com/Mehouelley/codepulse/actions/workflows/tests.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Zero dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](pyproject.toml)

**Reveal a codebase's health from its git history.**

Linters read your code. CodePulse reads your code's *history* — and that reveals
things no linter can see: where bugs are born, what knowledge lives in one
person's head, and which files are secretly glued together.

Because it works purely from git history, **CodePulse works on any language**,
with **zero dependencies** beyond git and Python.

---

## Demo

<!-- Render docs/demo.gif from demo.tape with `vhs demo.tape`, then:
     ![demo](docs/demo.gif) -->

```console
$ codepulse . --badge
Grade: B (83/100)
  -2 bus factor (9 fichiers à auteur unique)
  -15 pression hotspots en hausse
![code health](https://img.shields.io/badge/code%20health-B%20(83)-green)

$ codepulse . --changed origin/main
🔴 Release risk: HIGH (100/100)
   56 changed files · 2 high-risk
   [100] crates/ui-egui/src/lib.rs  (hotspot majeur)
   [ 70] crates/layout/src/para.rs  (zone active, auteur unique)
   👥 Relecteurs suggérés: Valentin Klein (29/37 fichiers), Dmitrii Khlapov (22/37)

$ codepulse . --who crates/ui-egui/src/canvas.rs
crates/ui-egui/src/canvas.rs — 64 commits, 22 auteur(s), dernier changement 2026-10-12
   45%   29 commits  Valentin Klein
   11%    7 commits  Dmitrii Khlapov
```

> A recordable [`demo.tape`](demo.tape) (for [VHS](https://github.com/charmbracelet/vhs))
> generates an animated `docs/demo.gif` of the above.

---

## What it shows

| Signal | Question it answers |
|---|---|
| 🔥 **Hotspots** | *Where do I refactor first?* Files that are both complex and changed constantly — the birthplace of most bugs. |
| 👥 **Bus factor** | *What breaks if someone leaves?* Files actively maintained by a single person. |
| 🔗 **Hidden coupling** | *What really depends on what?* Files that almost always change together, even when the code doesn't show a link. |
| 🏆 **Contributors** | Who is active across the analyzed window. |

The result is a single self-contained **HTML dashboard** you can open anywhere
or email to your team.

---

## Quick start

```bash
# From a git repository:
python -m codepulse /path/to/repo --open

# Common options:
python -m codepulse . --since "6 months ago" --top 30 -o health.html
```

> Running from the source checkout? Prefix with `PYTHONPATH=src`, or install it:
> `pip install -e .` then just run `codepulse`.

### Options

| Flag | Meaning |
|---|---|
| `repo` | Path to a git repository (default: current directory) |
| `-o, --output` | Output HTML path (default: `codepulse-report.html`) |
| `--since` | Only commits after a date, e.g. `"6 months ago"` |
| `--max-count N` | Limit to the N most recent commits |
| `--top N` | Rows per table (default: 20) |
| `--open` | Open the report in a browser when done |
| `--who PATH` | Show who knows a file best (from history) and exit |
| `--badge` | Print a shields.io health-badge snippet and exit |
| `--ignore GLOB` | Exclude paths matching a glob (repeatable) |

---

## Use in CI (the risk gate)

CodePulse can score *only the files a change touches* against the repo's risk
map, then set an exit code so your pipeline can warn or block.

```bash
# Score what this branch changed vs main; fail the job on HIGH risk.
python -m codepulse . --changed origin/main --fail-on HIGH

# Machine-readable output for dashboards / PR comments:
python -m codepulse . --changed origin/main --format json
```

Output (JSON):

```json
{
  "level": "HIGH",
  "score": 100,
  "high_risk_count": 1,
  "files": [
    { "path": "auth.py", "risk": 100, "commits": 6, "loc": 7,
      "reasons": ["hotspot majeur", "auteur unique (Alice)"] }
  ]
}
```

### GitHub Action (two lines)

Add CodePulse to any repository as a reusable Action — it scores each PR, posts
a **sticky comment** (updated in place, never spammed), and fails the check on
`HIGH` risk:

```yaml
name: CodePulse
on: pull_request
permissions:
  contents: read
  pull-requests: write
jobs:
  risk:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 } # full history is required
      - uses: Mehouelley/codepulse@v0.1.0
        with:
          fail-on: HIGH # or MEDIUM / LOW / '' to never fail
```

The PR comment looks like:

> 🩺 **CodePulse — Risque : 🔴 HIGH (100/100)**
> 38 fichiers modifiés · 1 à risque élevé
>
> 👥 **Relecteurs suggérés** : Valentin Klein (29/37 fichiers), Dmitrii Khlapov (22/37)

Prefer a plain workflow with no external action? One ships in
[`.github/workflows/codepulse.yml`](.github/workflows/codepulse.yml) — copy it in as-is.

**Why DevOps cares:** a release is roughly as risky as its riskiest file.
Touching a well-known hotspot — or a file only one person understands — is
exactly where change-failure-rate (a DORA metric) comes from. The gate makes
that risk visible *before* merge, not after an incident.

---

## How it works

1. Parses `git log --numstat` into commits and file changes (no merges).
2. Accumulates per-file history: commit count, authors, size on disk.
3. Derives the signals:
   - **Hotspot score** = `commits × complexity`, where complexity estimates
     decision points (branch keywords + boolean operators) — far better than
     raw line count at telling "big but simple" from "dense and risky".
   - **Bus factor risk** = files with ≥3 commits but exactly one author.
   - **Coupling degree** = `commits-together / min(individual commits)`,
     ignoring bulk commits that touch many files at once.

Inspired by the "code as a crime scene" approach to software analysis, made
simple enough to run in one command.

---

## Roadmap

- [x] Risk gate: score a change set, JSON output, CI exit code
- [x] Ignore globs / path filters for generated & data files
- [x] Post the gate result as a sticky PR comment (GitHub Action)
- [x] Trend over time (adaptive day/week/month buckets + hotspot-pressure verdict)
- [x] Complexity-based hotspots (decision-point estimate instead of line count)
- [x] Suggested PR reviewers from code ownership (in gate text/json/comment)
- [x] `--who <file>` — who knows this code best
- [x] `--badge` — shareable A–F health badge for your README
- [x] Orphaned-code section — complex files nobody touches anymore

## Development

```bash
pip install -e ".[dev]"
pytest
```

The suite covers the complexity estimator, git parsing, every analyzer, and an
end-to-end run against a throwaway git repo. CI runs it on Python 3.10 and 3.12.

## License

MIT
