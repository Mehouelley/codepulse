"""Tiny dependency-free SVG charts for the trend section.

One series per chart (small multiples), never a dual axis. Marks are thin, axes
recessive, bar ends rounded, x-labels selective (first/last), and every mark
carries a native <title> tooltip. Colours come from the report's CSS tokens so
light/dark both work.
"""

from __future__ import annotations

from collections.abc import Callable

# viewBox geometry (unitless; the SVG scales to its container via width:100%).
_W, _H = 360, 180
_L, _R, _T, _B = 8, 10, 14, 24
_PLOT_W = _W - _L - _R
_PLOT_H = _H - _T - _B
_BASE = _T + _PLOT_H  # baseline y


def _frame(title: str, body: str, ymax_label: str) -> str:
    return f"""<figure class="chart">
  <figcaption>{title}</figcaption>
  <svg viewBox="0 0 {_W} {_H}" role="img" preserveAspectRatio="xMidYMid meet">
    <line class="axis" x1="{_L}" y1="{_BASE}" x2="{_W - _R}" y2="{_BASE}"/>
    <text class="ymax" x="{_L}" y="{_T - 3}">{ymax_label}</text>
    {body}
  </svg>
</figure>"""


def _xlabels(labels: list[str], xs: list[float]) -> str:
    if not labels:
        return ""
    parts = [f'<text class="xlab" x="{xs[0]:.1f}" y="{_BASE + 15}" text-anchor="start">{labels[0]}</text>']
    if len(labels) > 1:
        parts.append(f'<text class="xlab" x="{xs[-1]:.1f}" y="{_BASE + 15}" text-anchor="end">{labels[-1]}</text>')
    return "\n    ".join(parts)


def bars(title: str, data: list[tuple[str, float]], cls: str, fmt: Callable[[float], str]) -> str:
    if not data:
        return _frame(title, '<text class="empty-svg" x="180" y="90" text-anchor="middle">pas de données</text>', "")
    labels = [d[0] for d in data]
    values = [d[1] for d in data]
    vmax = max(values) or 1
    n = len(data)
    slot = _PLOT_W / n
    bw = min(slot * 0.68, 26)
    rects, xs = [], []
    for i, (label, v) in enumerate(data):
        x = _L + i * slot + (slot - bw) / 2
        xs.append(x + bw / 2)
        h = (v / vmax) * _PLOT_H
        y = _BASE - h
        r = min(3, bw / 2)
        if h <= r:
            path = f'M{x:.1f},{_BASE} h{bw:.1f} V{y:.1f} h{-bw:.1f} Z'
        else:
            path = (f'M{x:.1f},{_BASE} V{y + r:.1f} q0,{-r} {r},{-r} '
                    f'h{bw - 2 * r:.1f} q{r},0 {r},{r} V{_BASE} Z')
        rects.append(f'<path class="mark {cls}" d="{path}"><title>{label}: {fmt(v)}</title></path>')
    body = "\n    ".join(rects) + "\n    " + _xlabels(labels, xs)
    return _frame(title, body, fmt(vmax))


def line(title: str, data: list[tuple[str, float]], cls: str, fmt: Callable[[float], str], area: bool = True) -> str:
    if not data:
        return _frame(title, '<text class="empty-svg" x="180" y="90" text-anchor="middle">pas de données</text>', "")
    labels = [d[0] for d in data]
    values = [d[1] for d in data]
    vmax = max(values) or 1
    vmin = min(values)
    span = (vmax - vmin) or 1
    n = len(data)
    xs = [_L + (i / (n - 1) * _PLOT_W if n > 1 else _PLOT_W / 2) for i in range(n)]
    ys = [_BASE - ((v - vmin) / span) * _PLOT_H for v in values]
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))

    body = []
    if area:
        body.append(f'<polygon class="area {cls}" points="{xs[0]:.1f},{_BASE} {pts} {xs[-1]:.1f},{_BASE}"/>')
    body.append(f'<polyline class="line {cls}" points="{pts}"/>')
    # Transparent hit targets so every point has a hover tooltip.
    for (x, y), label, v in zip(zip(xs, ys), labels, values):
        body.append(f'<circle class="hit" cx="{x:.1f}" cy="{y:.1f}" r="7"><title>{label}: {fmt(v)}</title></circle>')
    body.append(f'<circle class="dot {cls}" cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="3"/>')
    body.append(_xlabels(labels, xs))
    return _frame(title, "\n    ".join(body), fmt(vmax))


# Formatters ---------------------------------------------------------------

def fmt_int(v: float) -> str:
    return f"{int(round(v)):,}"


def fmt_pct(v: float) -> str:
    return f"{round(v * 100)}%"


CHART_CSS = """
.trend-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
@media (max-width: 680px) { .trend-grid { grid-template-columns: 1fr; } }
.chart { margin: 0; }
.chart figcaption { font-size: 12px; color: var(--muted); margin-bottom: 4px; font-weight: 600; }
.chart svg { width: 100%; height: auto; display: block; }
.chart .axis { stroke: var(--line); stroke-width: 1; }
.chart .ymax { fill: var(--muted); font-size: 10px; font-variant-numeric: tabular-nums; }
.chart .xlab { fill: var(--muted); font-size: 10px; }
.chart .empty-svg { fill: var(--muted); font-size: 12px; }
.chart .mark.accent { fill: var(--accent); }
.chart .mark.hot { fill: var(--hot); }
.chart .mark { transition: opacity .1s; }
.chart .mark:hover { opacity: .75; }
.chart .line { fill: none; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
.chart .line.accent { stroke: var(--accent); }
.chart .line.hot { stroke: var(--hot); }
.chart .area.accent { fill: var(--accent); opacity: .12; }
.chart .area.hot { fill: var(--hot); opacity: .12; }
.chart .dot.accent { fill: var(--accent); }
.chart .dot.hot { fill: var(--hot); }
.chart .hit { fill: transparent; }
.verdict { font-size: 14px; margin: 0 0 16px; padding: 10px 14px; border-radius: 10px;
  background: var(--bg); border: 1px solid var(--line); }
"""
