# 🩺 CodePulse

**Reveal a codebase's health from its git history.**

Linters read your code. CodePulse reads your code's *history* — and that reveals
things no linter can see: where bugs are born, what knowledge lives in one
person's head, and which files are secretly glued together.

Because it works purely from git history, **CodePulse works on any language**,
with **zero dependencies** beyond git and Python.

---

## What it shows

| Signal | Question it answers |
|---|---|
| 🔥 **Hotspots** | *Where do I refactor first?* Files that are both large and changed constantly — the birthplace of most bugs. |
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

---

## How it works

1. Parses `git log --numstat` into commits and file changes (no merges).
2. Accumulates per-file history: commit count, authors, size on disk.
3. Derives the signals:
   - **Hotspot score** = `commits × current lines of code`.
   - **Bus factor risk** = files with ≥3 commits but exactly one author.
   - **Coupling degree** = `commits-together / min(individual commits)`,
     ignoring bulk commits that touch many files at once.

Inspired by the "code as a crime scene" approach to software analysis, made
simple enough to run in one command.

---

## Roadmap

- [ ] Real complexity metrics per language (beyond line count)
- [ ] Trend over time (is debt rising or falling?)
- [ ] `--json` output for CI pipelines and badges
- [ ] GitHub Action: comment health deltas on pull requests
- [ ] Ignore globs / path filters

## License

MIT
