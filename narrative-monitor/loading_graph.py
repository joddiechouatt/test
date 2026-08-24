"""Animated 'connection graph' loading indicator: nodes fade in and get
linked by lines, like a link-analysis map assembling itself, while the
live-mode pipeline (RSS fetch + LLM calls) is running.

Pure HTML/CSS - no JS, no external libs. Node/edge layout and animation
timing are computed once in Python (below) into plain inline styles, so the
browser just runs a handful of CSS keyframe animations with
`animation-iteration-count: infinite`; nothing needs to poll or restart it
from the Python side, and it disappears cleanly the instant the caller
empties the st.empty() placeholder it was rendered into.

Kept in its own module (no Streamlit import) so the exact markup used in
the app can also be generated standalone for a design preview.
"""

from __future__ import annotations

import html
import math

# (x, y, perspective label or None) - a deliberately organic scatter, not a
# grid, across a 600x160 viewBox. A handful of nodes carry a perspective
# label so the graph reads as "sources connecting," not abstract decoration.
NODES = [
    (40, 92, None),
    (86, 40, "Western"),
    (128, 118, None),
    (176, 58, None),
    (222, 100, "Israeli"),
    (266, 32, None),
    (312, 82, "Iranian"),
    (358, 128, None),
    (404, 52, None),
    (452, 98, "Arab"),
    (500, 40, None),
    (548, 88, "French"),
]

# Sparse, plausible link-analysis topology: mostly neighbors, plus a couple
# of longer triangulating links so it doesn't read as a straight chain.
EDGES = [
    (0, 1), (0, 2), (1, 3), (2, 3), (2, 4), (3, 5), (4, 5),
    (4, 6), (5, 8), (6, 7), (6, 8), (7, 9), (8, 9), (8, 10),
    (9, 11), (10, 11), (1, 5), (4, 9),
]

STATUS_PHRASES = [
    "Collecting articles…",
    "Filtering by relevance…",
    "Analyzing narratives…",
    "Comparing perspectives…",
]

# teal, amber, ice-blue - the app's existing accent trio, cycled across
# nodes/edges. Deliberately not the full 5-color perspective palette: this
# is chrome around the tool, not another data view, so it stays quieter.
ACCENTS = ["#4FB0A5", "#E0A458", "#9FB6D4"]

CYCLE_S = 6.0  # full build-up -> hold -> fade -> reset loop, in seconds
REVEAL_SPAN_S = 3.0  # all nodes have appeared by this point in the cycle
TEXT_CYCLE_S = 8.0  # independent loop for the 4 status phrases (2s each)


def _node_delay(index: int) -> float:
    n = len(NODES)
    return round(index / (n - 1) * REVEAL_SPAN_S, 2) if n > 1 else 0.0


def build_svg() -> str:
    """Render the SVG markup. Every node/edge shares the same CSS animation
    (same duration => they stay in a fixed relative stagger every loop,
    forever); only `animation-delay` differs, computed here."""
    parts: list[str] = []

    for a, b in EDGES:
        (x1, y1, _), (x2, y2, _) = NODES[a], NODES[b]
        length = round(math.hypot(x2 - x1, y2 - y1), 1)
        delay = max(_node_delay(a), _node_delay(b)) + 0.15
        color = ACCENTS[(a + b) % len(ACCENTS)]
        parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
            f'class="lg-edge" style="--len:{length};animation-delay:{delay}s"/>'
        )

    for i, (x, y, persp) in enumerate(NODES):
        color = ACCENTS[i % len(ACCENTS)]
        delay = _node_delay(i)
        parts.append(
            f'<circle cx="{x}" cy="{y}" r="4.5" fill="{color}" '
            f'class="lg-node" style="animation-delay:{delay}s"/>'
        )
        if persp:
            parts.append(
                f'<text x="{x}" y="{y - 11}" text-anchor="middle" class="lg-label" '
                f'style="animation-delay:{delay}s">{html.escape(persp)}</text>'
            )

    return (
        '<svg viewBox="0 0 600 160" preserveAspectRatio="xMidYMid meet" class="loadgraph-svg" '
        'role="img" aria-label="Connection graph animating while sources are collected and analyzed">'
        + "".join(parts)
        + "</svg>"
    )


def build_status_html() -> str:
    spans = "".join(
        f'<span class="lg-status-phrase" style="animation-delay:{i * (TEXT_CYCLE_S / len(STATUS_PHRASES))}s">'
        f"{html.escape(phrase)}</span>"
        for i, phrase in enumerate(STATUS_PHRASES)
    )
    return f'<div class="lg-status">{spans}</div>'


def build_loading_html(topic: str) -> str:
    """Full loading-indicator block: the animated graph + cycling status
    line, with a plain-text fallback for prefers-reduced-motion (CSS-only
    toggle, see CSS below - no JS feature detection needed)."""
    return f"""
    <div class="loadgraph-wrap">
      <div class="loadgraph-anim">
        {build_svg()}
        {build_status_html()}
      </div>
      <div class="loadgraph-static">Analyzing &ldquo;{html.escape(topic)}&rdquo;…</div>
    </div>
    """


CSS = f"""
.loadgraph-wrap{{margin-top:14px}}
.loadgraph-svg{{width:100%;height:auto;max-height:150px;display:block}}
.lg-node{{opacity:0;animation:lg-node-fade {CYCLE_S}s ease-in-out infinite}}
.lg-label{{opacity:0;fill:var(--mut);font-size:9px;letter-spacing:.3px;
  animation:lg-node-fade {CYCLE_S}s ease-in-out infinite}}
.lg-edge{{opacity:0;stroke-width:1;fill:none;
  stroke-dasharray:var(--len);stroke-dashoffset:var(--len);
  animation:lg-edge-draw {CYCLE_S}s ease-in-out infinite}}
@keyframes lg-node-fade{{
  0%{{opacity:0}}
  6%{{opacity:1}}
  82%{{opacity:1}}
  92%{{opacity:0}}
  100%{{opacity:0}}
}}
@keyframes lg-edge-draw{{
  0%{{opacity:0;stroke-dashoffset:var(--len)}}
  4%{{opacity:0;stroke-dashoffset:var(--len)}}
  11%{{opacity:.85;stroke-dashoffset:0}}
  82%{{opacity:.85;stroke-dashoffset:0}}
  92%{{opacity:0;stroke-dashoffset:0}}
  100%{{opacity:0;stroke-dashoffset:0}}
}}
.lg-status{{position:relative;height:18px;margin-top:8px;font-size:12px;color:var(--ice);text-align:center}}
.lg-status-phrase{{position:absolute;left:0;right:0;opacity:0;
  animation:lg-text-cycle {TEXT_CYCLE_S}s ease-in-out infinite}}
@keyframes lg-text-cycle{{
  0%{{opacity:0}}
  3%{{opacity:1}}
  22%{{opacity:1}}
  28%{{opacity:0}}
  100%{{opacity:0}}
}}
.loadgraph-static{{display:none;margin-top:14px;color:var(--ice);font-size:13px;text-align:center}}
@media (prefers-reduced-motion: reduce){{
  .loadgraph-anim{{display:none}}
  .loadgraph-static{{display:block}}
}}
"""
