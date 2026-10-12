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

### GitHub Actions

A ready-to-use workflow ships in [`.github/workflows/codepulse.yml`](.github/workflows/codepulse.yml).
On every pull request it scores the change, posts a **sticky comment** (updated
in place, never spammed), and fails the check on `HIGH` risk:

> 🩺 **CodePulse — Risque : 🔴 HIGH (100/100)**
> 38 fichiers modifiés · 1 à risque élevé
> | Risque | Fichier | Pourquoi |
> |---:|---|---|
> | 100 | `crates/ui-egui/src/lib.rs` | hotspot majeur |

Drop the file into any repository to enable it — no extra configuration.

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

## License

MIT
