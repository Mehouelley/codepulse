"""Render analysis results as a single self-contained HTML dashboard.

No build step, no CDN: the CSS is inlined so the report opens anywhere and
survives being emailed around. Colours adapt to light/dark via tokens.
"""

from __future__ import annotations

import datetime as _dt
import html

from . import charts
from .analyzers import CouplingPair, FileStat, StaleFile, Summary, Trend


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _date(ts: int) -> str:
    if not ts:
        return "—"
    return _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def _bar(value: float, maximum: float) -> str:
    pct = 0 if maximum <= 0 else max(2, round(value / maximum * 100))
    return f'<span class="bar" style="width:{pct}%"></span>'


def _risk_badge(share: float) -> str:
    if share >= 0.9:
        cls, label = "high", "élevé"
    elif share >= 0.7:
        cls, label = "mid", "moyen"
    else:
        cls, label = "low", "faible"
    return f'<span class="badge {cls}">{label}</span>'


def _trend_section(trend: Trend) -> str:
    if not trend or not trend.buckets:
        return ""
    commits = [(b.label, b.commits) for b in trend.buckets]
    size = [(b.label, b.cum_net) for b in trend.buckets]
    pressure = [(b.label, b.hotspot_pct) for b in trend.buckets]
    grid = (
        charts.bars(f"Commits par {trend.granularity}", commits, "accent", charts.fmt_int)
        + charts.line("Taille du code (lignes cumulées)", size, "accent", charts.fmt_int)
        + charts.line("Pression hotspots (% commits)", pressure, "hot", charts.fmt_pct)
    )
    return f"""<section>
    <h2>📈 Tendance</h2>
    <p class="hint">L'évolution dans le temps — l'activité, la croissance du code, et surtout si les changements se concentrent sur les fichiers à risque.</p>
    <p class="verdict">{_esc(trend.verdict)}</p>
    <div class="trend-grid">{grid}</div>
  </section>"""


def _stale_section(stale: list[StaleFile]) -> str:
    if not stale:
        return ""
    rows = "\n".join(
        f"""<tr>
          <td class="path">{_esc(s.path)}</td>
          <td class="num">{s.complexity:,}</td>
          <td class="num">{s.days_stale} j</td>
          <td class="owner">{_esc(s.main_owner[0] or '—')}</td>
        </tr>"""
        for s in stale
    )
    return f"""<section>
    <h2>🕸️ Code orphelin</h2>
    <p class="hint">Fichiers complexes que plus personne n'a touchés depuis longtemps — de la logique qui vieillit et que plus grand monde ne comprend.</p>
    <table>
      <thead><tr><th>Fichier</th><th class="num">Complexité</th><th class="num">Sans changement</th><th>Dernier auteur</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </section>"""


def render(
    repo_name: str,
    summary: Summary,
    hotspots: list[FileStat],
    bus_risks: list[FileStat],
    coupling: list[CouplingPair],
    trend: Trend | None = None,
    stale: list[StaleFile] | None = None,
) -> str:
    generated = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    span = f"{_date(summary.first_timestamp)} → {_date(summary.last_timestamp)}"

    max_hot = max((h.hotspot_score for h in hotspots), default=1)
    hot_rows = "\n".join(
        f"""<tr>
          <td class="rank">{i}</td>
          <td class="path">{_esc(h.path)}</td>
          <td class="num">{h.commits}</td>
          <td class="num">{h.complexity:,}</td>
          <td class="score">{_bar(h.hotspot_score, max_hot)}<span class="score-val">{h.hotspot_score:,}</span></td>
        </tr>"""
        for i, h in enumerate(hotspots, 1)
    ) or '<tr><td colspan="5" class="empty">Aucun hotspot détecté.</td></tr>'

    bus_rows = "\n".join(
        f"""<tr>
          <td class="path">{_esc(s.path)}</td>
          <td class="owner">{_esc(s.main_owner[0] or '—')}</td>
          <td class="num">{s.commits}</td>
          <td>{_risk_badge(s.main_owner[1])}</td>
        </tr>"""
        for s in bus_risks
    ) or '<tr><td colspan="4" class="empty">Aucun risque de bus factor. 🎉</td></tr>'

    coupling_rows = "\n".join(
        f"""<tr>
          <td class="path">{_esc(p.a)}</td>
          <td class="path">{_esc(p.b)}</td>
          <td class="num">{p.shared}</td>
          <td class="num">{round(p.degree * 100)}%</td>
        </tr>"""
        for p in coupling
    ) or '<tr><td colspan="4" class="empty">Aucun couplage significatif.</td></tr>'

    max_contrib = max((n for _, n in summary.top_contributors), default=1)
    contrib_rows = "\n".join(
        f"""<li><span class="c-name">{_esc(name)}</span>
          <span class="c-bar">{_bar(n, max_contrib)}</span>
          <span class="c-num">{n}</span></li>"""
        for name, n in summary.top_contributors
    ) or '<li class="empty">—</li>'

    return _TEMPLATE.format(
        repo_name=_esc(repo_name),
        generated=generated,
        span=span,
        chart_css=charts.CHART_CSS,
        trend_section=_trend_section(trend),
        stale_section=_stale_section(stale or []),
        total_commits=f"{summary.total_commits:,}",
        active_files=f"{summary.active_files:,}",
        tracked_files=f"{summary.tracked_files:,}",
        contributors=summary.contributors,
        hot_rows=hot_rows,
        bus_rows=bus_rows,
        coupling_rows=coupling_rows,
        contrib_rows=contrib_rows,
    )


_TEMPLATE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CodePulse — {repo_name}</title>
<style>
:root {{
  --bg: #f6f7f9; --panel: #ffffff; --ink: #1a1d21; --muted: #6b7280;
  --line: #e5e7eb; --accent: #2563eb; --hot: #ef4444; --hot-soft: #fee2e2;
  --high: #dc2626; --mid: #d97706; --low: #16a34a;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg: #0d1117; --panel: #161b22; --ink: #e6edf3; --muted: #8b949e;
    --line: #30363d; --accent: #58a6ff; --hot: #f85149; --hot-soft: #3d1a1a;
    --high: #f85149; --mid: #e3b341; --low: #3fb950;
  }}
}}
:root[data-theme="dark"] {{
  --bg: #0d1117; --panel: #161b22; --ink: #e6edf3; --muted: #8b949e;
  --line: #30363d; --accent: #58a6ff; --hot: #f85149; --hot-soft: #3d1a1a;
  --high: #f85149; --mid: #e3b341; --low: #3fb950;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}}
.wrap {{ max-width: 960px; margin: 0 auto; padding: 32px 16px 64px; }}
header {{ margin-bottom: 28px; }}
.logo {{ font-size: 13px; letter-spacing: .14em; text-transform: uppercase; color: var(--accent); font-weight: 700; }}
h1 {{ margin: 6px 0 4px; font-size: 26px; }}
.sub {{ color: var(--muted); font-size: 13px; }}
.cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 24px 0 36px; }}
@media (max-width: 640px) {{ .cards {{ grid-template-columns: repeat(2, 1fr); }} }}
.card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 16px; }}
.card .k {{ font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; }}
.card .v {{ font-size: 26px; font-weight: 700; margin-top: 4px; }}
section {{ background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 20px; margin-bottom: 24px; }}
section h2 {{ margin: 0 0 4px; font-size: 18px; }}
section .hint {{ color: var(--muted); font-size: 13px; margin: 0 0 16px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
th {{ text-align: left; color: var(--muted); font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; padding: 6px 8px; border-bottom: 1px solid var(--line); }}
td {{ padding: 8px; border-bottom: 1px solid var(--line); vertical-align: middle; }}
tr:last-child td {{ border-bottom: none; }}
.rank {{ color: var(--muted); width: 28px; }}
.path {{ font-family: ui-monospace, "Cascadia Code", Consolas, monospace; font-size: 13px; word-break: break-all; }}
.num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
.score {{ position: relative; min-width: 160px; }}
.bar {{ display: inline-block; height: 8px; border-radius: 4px; background: var(--hot); vertical-align: middle; }}
.score-val {{ font-variant-numeric: tabular-nums; color: var(--muted); font-size: 12px; margin-left: 8px; }}
.owner {{ color: var(--ink); }}
.badge {{ display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; color: #fff; }}
.badge.high {{ background: var(--high); }}
.badge.mid {{ background: var(--mid); }}
.badge.low {{ background: var(--low); }}
.empty {{ color: var(--muted); text-align: center; padding: 20px; }}
ul.contrib {{ list-style: none; margin: 0; padding: 0; }}
ul.contrib li {{ display: grid; grid-template-columns: 180px 1fr 40px; gap: 10px; align-items: center; padding: 5px 0; }}
ul.contrib .c-name {{ font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
ul.contrib .c-bar .bar {{ background: var(--accent); }}
ul.contrib .c-num {{ text-align: right; color: var(--muted); font-variant-numeric: tabular-nums; }}
footer {{ text-align: center; color: var(--muted); font-size: 12px; margin-top: 32px; }}
footer a {{ color: var(--accent); text-decoration: none; }}
{chart_css}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="logo">🩺 CodePulse</div>
    <h1>{repo_name}</h1>
    <div class="sub">Analyse générée le {generated} · historique {span}</div>
  </header>

  <div class="cards">
    <div class="card"><div class="k">Commits</div><div class="v">{total_commits}</div></div>
    <div class="card"><div class="k">Fichiers actifs</div><div class="v">{active_files}</div></div>
    <div class="card"><div class="k">Fichiers suivis</div><div class="v">{tracked_files}</div></div>
    <div class="card"><div class="k">Contributeurs</div><div class="v">{contributors}</div></div>
  </div>

  {trend_section}

  <section>
    <h2>🔥 Hotspots</h2>
    <p class="hint">Fichiers à la fois complexes (beaucoup de chemins de décision) et souvent modifiés — là où les bugs naissent et où refactorer rapporte le plus.</p>
    <table>
      <thead><tr><th></th><th>Fichier</th><th class="num">Commits</th><th class="num">Complexité</th><th>Score (commits × complexité)</th></tr></thead>
      <tbody>{hot_rows}</tbody>
    </table>
  </section>

  <section>
    <h2>👥 Risque de bus factor</h2>
    <p class="hint">Fichiers activement maintenus par une seule personne. Si elle part, ce savoir part avec elle.</p>
    <table>
      <thead><tr><th>Fichier</th><th>Unique auteur</th><th class="num">Commits</th><th>Risque</th></tr></thead>
      <tbody>{bus_rows}</tbody>
    </table>
  </section>

  <section>
    <h2>🔗 Couplage caché</h2>
    <p class="hint">Fichiers qui changent presque toujours ensemble — une dépendance que le code ne montre pas.</p>
    <table>
      <thead><tr><th>Fichier A</th><th>Fichier B</th><th class="num">Ensemble</th><th class="num">Degré</th></tr></thead>
      <tbody>{coupling_rows}</tbody>
    </table>
  </section>

  {stale_section}

  <section>
    <h2>🏆 Top contributeurs</h2>
    <p class="hint">Par nombre de commits sur la période analysée.</p>
    <ul class="contrib">{contrib_rows}</ul>
  </section>

  <footer>Généré par <a href="https://github.com/">CodePulse</a> — la santé de votre code, révélée par son historique.</footer>
</div>
</body>
</html>"""
