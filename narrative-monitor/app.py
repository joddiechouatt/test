"""Streamlit dashboard for the Multi-Source Narrative Analysis Monitor.

Every topic - the three featured shortcuts or a free-text search - runs the
full pipeline live (keyword generation -> RSS collection -> per-article LLM
analysis), rate-limited per session and cached by topic string. There is no
pre-computed data shipped in the repo.

Visual design follows a dark-themed mockup provided by the project owner:
search bar + featured-topic chips, perspective/source filter pills, an
AI-synthesis summary card, and a sorted list of article cards with a
perspective-colored left border. Implemented with native Streamlit widgets
(st.pills, st.text_input, st.button) for anything interactive, and raw HTML
fragments (via st.markdown(unsafe_allow_html=True)) for the purely visual
pieces (header, synthesis card, article cards) so the layout can match the
mockup's markup/CSS closely.
"""

from __future__ import annotations

import html
import logging
import os
import re
from collections import Counter
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from loading_graph import CSS as LOADING_GRAPH_CSS
from loading_graph import build_loading_html

# INFO-level logging (feed_collector's per-source "N fetched, M kept" and
# analyzer's per-article progress) is silent by default - Python's root
# logger starts at WARNING, so only failures ever reached Streamlit Cloud's
# logs, with no way to tell a genuinely empty result from an undercounted
# one. Configured once, here, so production logs carry the same detail as
# a local `run_pipeline.py -v` run.
logging.basicConfig(level=logging.INFO, format="%(message)s")

# Featured topics are just pre-picked strings, not pre-computed data - every
# one of them runs through the exact same live pipeline as a free-text
# search (see trigger_live_analysis below), and counts against the same
# per-session request cap.
FEATURED_TOPICS = ["Iran–USA", "Turkey–Israel", "Strait of Hormuz"]
RELEVANCE_FLOOR = 3
LIVE_MODE_REQUEST_CAP = 3  # per browser session
COVERAGE_SIMILARITY_THRESHOLD = 0.25  # title-token Jaccard similarity

st.set_page_config(page_title="Narrative Monitoring", layout="wide", page_icon="🌐")

# ---------------------------------------------------------------------------
# Perspective display metadata (label, CSS color var, badge background)
# ---------------------------------------------------------------------------

PERSPECTIVE_STYLE = {
    "Western": {"label": "WESTERN", "var": "--west"},
    "Israeli": {"label": "ISRAELI", "var": "--isr"},
    "Iranian_axis": {"label": "IRANIAN / AXIS", "var": "--iran"},
    "Gulf": {"label": "GULF", "var": "--gulf"},
    "Qatari": {"label": "QATARI", "var": "--qatari"},
    "Turkish": {"label": "TURKISH", "var": "--turkish"},
    "Maghreb": {"label": "MAGHREB", "var": "--maghreb"},
    "Egyptian": {"label": "EGYPTIAN", "var": "--egyptian"},
    "French": {"label": "FRENCH", "var": "--fr"},
}
DEFAULT_PERSPECTIVE_STYLE = {"label": "OTHER", "var": "--ice"}

TONE_LABELS = {
    "neutral": "neutral", "alarmist": "alarmist", "triumphalist": "triumphalist",
    "defensive": "defensive", "sympathetic": "sympathetic", "accusatory": "accusatory",
    "dismissive": "dismissive",
}

SORT_OPTIONS = ["Relevance", "Date", "Disinformation score", "Coverage overlap"]

# ---------------------------------------------------------------------------
# CSS - adapted from the provided mockup. Scoped to avoid clashing with
# Streamlit's own <header>/chrome: the mockup's bare `header{...}` rule
# becomes `.app-header{...}` here, applied to a plain <div>.
# ---------------------------------------------------------------------------

CSS = (
    """
<style>
:root{
  --bg:#0F1620; --panel:#18222F; --panel2:#1F2C3D; --line:#2A3849;
  --ink:#EAF0F7; --mut:#8A9BB2; --ice:#9FB6D4;
  --amber:#E0A458; --teal:#4FB0A5; --rose:#D08B7A;
  --west:#5B8DEF; --isr:#4FB0A5; --iran:#D06B6B; --qatari:#E0A458; --fr:#B08BD0;
  --gulf:#C2A55C; --turkish:#DA7B54; --maghreb:#6FA97A; --egyptian:#8FA6C9;
}
.stApp{background:var(--bg);color:var(--ink);}
/* Back to exactly the one selector this rule had before any of this
   section's centering changes - confirmed (by the user, on the actual
   deployed app) that the title wasn't clipped before that work started.
   Adding [data-testid="stMainBlockContainer"] as a second match target
   earlier was the one remaining suspect neither of the last two fixes had
   actually removed - dropped now rather than guessed at again. This
   means the page-wide max-width/centering that selector was chasing is
   gone too, but nothing the user actually asked for depended on it: the
   "Pick a topic" label + chip row are centered via their own scoped CSS
   below (relative to the search card's own width), not via this rule. */
.main .block-container{
  max-width:1080px;padding-top:1.5rem;padding-bottom:3rem;
}
.stApp, .stApp p, .stApp span, .stApp label{color:var(--ink);}
[data-testid="stMarkdownContainer"] p{color:var(--ink);}

.app-header{padding:6px 0 18px;border-bottom:1px solid var(--line);margin-bottom:22px;overflow:visible}
/* Two prior mitigations (font-synthesis:none, an explicit font-family)
   didn't fix the clipped title on iOS Safari, and the user confirmed it
   wasn't clipped before this section's centering work started - meaning
   the actual cause was most likely the .block-container change above
   (now reverted), not this rule. Kept line-height/overflow/font-synthesis
   here anyway (harmless either way) and additionally dropped the italic
   <em> on "MENA" (now a plain .brand-mena span, see the markup) - that
   was the one remaining variable neither prior attempt had removed, and
   italic was the specific ingredient in every synthesis-based theory
   tried so far. -webkit-text-size-adjust guards against a separate, also
   iOS-specific text-scaling quirk some custom-styled headings hit. */
.brand{
  font-size:22px;font-weight:700;letter-spacing:.5px;line-height:1.4;
  overflow:visible;font-synthesis:none;-webkit-text-size-adjust:100%;
}
/* .brand-mena is a <span> (was <em>) so it now also matches ".brand span"
   below - which is meant for "Monitoring" only - and would otherwise
   inherit that rule's amber color since a single class has lower
   specificity than a class+type selector. Pinned back to the normal ink
   color explicitly, at equal specificity, to undo that. */
.brand span.brand-mena{font-style:normal;color:var(--ink)}
.brand span{color:var(--amber)}
.tag{color:var(--mut);font-size:13px;margin-top:2px}

/* st.container(key="searchcard") below, not a raw <div class="searchcard">
   opened in one st.markdown() call and closed in another - Streamlit
   renders each st.markdown() as its own isolated DOM node, so an
   opening tag with no matching close in the *same* call gets
   auto-closed by the browser as an empty element. That produced a
   visible empty gray bar above the actual (unstyled, floating)
   content instead of one bordered card wrapping everything. */
.st-key-searchcard{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px;margin-bottom:4px}
/* The search box had no explicit styling of its own - it only ever looked
   like a box because it used to sit directly on the page background
   (--bg), which was visibly darker than its own native input background
   (secondaryBackgroundColor). Now that it's properly nested inside
   .st-key-searchcard (--panel, the *same* secondaryBackgroundColor). Both
   surfaces are the same color and Streamlit's own default input border
   isn't strong enough on its own to read as a box - needs an explicit
   border/background here the same way st.pills' buttons are restyled
   above, rather than relying on an accidental color mismatch. */
/* The box's actual paint target differs by Streamlit version - older
   ones build text_input on BaseWeb ([data-baseweb="input"] wrapper),
   current ones on react-aria (stTextInputRootElement testid); the bare
   <input>/stTextInputField is transparent/borderless by design in both,
   letting the wrapper show through. Both selector forms are listed since
   local testing (this pip install) and the deployed app turned out to be
   on different Streamlit versions with different DOM here. */
[data-testid="stTextInputRootElement"],
[data-testid="stTextInput"] [data-baseweb="input"]{
  background:var(--bg) !important;
  border:1px solid var(--line) !important;
  border-radius:8px !important;
  box-shadow:none !important;
}
[data-testid="stTextInputRootElement"]:focus-within,
[data-testid="stTextInput"] [data-baseweb="input"]:focus-within{
  border-color:var(--amber) !important;
}
[data-testid="stTextInputField"],
[data-testid="stTextInput"] input{
  background:transparent !important;
  color:var(--ink) !important;
  box-shadow:none !important;
}
.hint{color:var(--mut);font-size:12px;margin-top:10px;font-style:italic}
/* Only the "Pick a topic" label + the chip row are centered - the search
   bar/button row below stays left-aligned as before, per request. */
.picklabel{font-size:11px;letter-spacing:1px;text-transform:uppercase;color:var(--mut);margin-bottom:9px;text-align:center}
.st-key-featured_topic_pill{display:flex;justify-content:center;width:100%}
.st-key-featured_topic_pill [data-testid="stPills"]{justify-content:center;width:100%}
.orsep{display:flex;align-items:center;gap:12px;margin:16px 0;color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:1px}
.orsep::before,.orsep::after{content:"";flex:1;height:1px;background:var(--line)}
"""
    + LOADING_GRAPH_CSS
    + """
.topictitle{display:flex;align-items:baseline;gap:10px;margin:26px 0 4px;flex-wrap:wrap}
.topictitle h2{font-size:22px;margin:0;color:var(--ink)}
.tt-tag{font-size:10.5px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:var(--amber);background:rgba(224,164,88,.12);border:1px solid var(--amber);border-radius:999px;padding:3px 10px}

.fgroup h4{font-size:11px;letter-spacing:1px;text-transform:uppercase;color:var(--mut);margin:18px 0 6px}

.synth{margin-top:10px;background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:14px;padding:20px}
.synth h3{font-size:14px;margin-bottom:14px;display:flex;align-items:center;gap:8px}
.synth h3 .badge{background:var(--teal);color:#06201d;font-size:10px;font-weight:700;padding:2px 8px;border-radius:999px;letter-spacing:.5px}
.synthgrid{display:grid;grid-template-columns:repeat(auto-fit, minmax(220px, 1fr));gap:12px}
.scol{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:13px}
.scol .pv{font-size:11px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;margin-bottom:6px}
.scol p{font-size:12.5px;color:var(--ice);margin:0}

.sechead{display:flex;justify-content:space-between;align-items:baseline;margin:28px 0 4px}
.sechead h2{font-size:16px;margin:0}
.sechead .count{color:var(--mut);font-size:12.5px}

.art{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--west);border-radius:12px;padding:16px 18px;margin-top:12px}
.art .top{display:flex;justify-content:space-between;gap:14px;align-items:flex-start}
.art .src{font-size:12px;color:var(--mut);display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.persp{font-size:10.5px;font-weight:700;padding:2px 8px;border-radius:999px;letter-spacing:.4px}
.paywall{font-size:11px;opacity:.85;cursor:help}
.art h3{font-size:15.5px;margin:8px 0;line-height:1.35}
.art h3 a{color:var(--ink);text-decoration:none}
.art h3 a:hover{color:var(--amber)}
.meta{display:flex;gap:16px;flex-wrap:wrap;margin-top:10px;font-size:12px;color:var(--mut);align-items:center}
.metaitem{display:flex;align-items:center;gap:5px}
.rel{display:flex;align-items:center;gap:6px}
.bar{width:60px;height:6px;background:var(--line);border-radius:3px;overflow:hidden;display:inline-block}
.bar i{display:block;height:100%;background:var(--teal)}
.tone{font-size:11px;padding:2px 8px;border-radius:6px;background:var(--panel2);color:var(--ice)}
.disinfo{font-size:11px;padding:2px 8px;border-radius:6px;font-weight:600}
.d-low{background:rgba(79,176,165,.15);color:var(--teal)}
.d-hi{background:rgba(208,107,107,.15);color:#e08a8a}
.open{color:var(--amber);font-size:12px;text-decoration:none;font-weight:600;white-space:nowrap}
.open:hover{text-decoration:underline}

.note{background:rgba(224,164,88,.08);border:1px dashed var(--amber);border-radius:10px;padding:12px 15px;margin-top:22px;font-size:12.5px;color:var(--ice)}
.note b{color:var(--amber)}

/* Restyle st.pills (rendered as <button data-variant="pills">) to look like
   the mockup's filter pills / topic chips. data-selected="true" marks the
   active state; .st-key-<key> scopes the featured-topic chip row so it can
   get the mockup's amber "chip.active" look instead of the muted filter-pill
   look. */
[data-testid="stPills"] button[data-variant="pills"]{
  background:var(--panel2) !important;
  border:1px solid var(--line) !important;
  border-radius:8px !important;
  color:var(--ice) !important;
  font-size:12.5px !important;
  font-weight:400 !important;
  box-shadow:none !important;
}
[data-testid="stPills"] button[data-variant="pills"][data-selected="true"]{
  border-color:var(--ice) !important;
  color:var(--ink) !important;
}
[data-testid="stPills"] button[data-variant="pills"]:hover{
  border-color:var(--amber) !important;
  color:#fff !important;
}
.st-key-featured_topic_pill button[data-variant="pills"]{
  border-radius:999px !important;
  padding-left:14px !important;
  padding-right:14px !important;
}
.st-key-featured_topic_pill button[data-variant="pills"][data-selected="true"]{
  background:var(--amber) !important;
  color:#20160a !important;
  border-color:var(--amber) !important;
  font-weight:600 !important;
}
</style>
"""
)

st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Data shaping
# ---------------------------------------------------------------------------

def articles_to_df(payload: dict) -> pd.DataFrame:
    articles = payload.get("articles", [])
    if not articles:
        return pd.DataFrame()
    df = pd.DataFrame(articles)
    for col in ["relevance_score", "disinfo_score"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    if "published" in df.columns:
        df["published_parsed"] = pd.to_datetime(df["published"], errors="coerce", utc=True)
    else:
        df["published_parsed"] = pd.NaT
    return df


# ---------------------------------------------------------------------------
# Small presentation helpers
# ---------------------------------------------------------------------------

def humanize_delta(ts) -> str:
    """'2h ago' / '3d ago' style relative time. Falls back to '' if unknown."""
    if ts is None or pd.isna(ts):
        return ""
    now = datetime.now(timezone.utc)
    delta = now - ts.to_pydatetime()
    seconds = delta.total_seconds()
    if seconds < 0:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


_STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "for", "to", "and", "or", "is", "are",
    "with", "after", "before", "amid", "as", "at", "by", "from", "its", "over",
    "into", "than", "that", "this", "who", "what", "will", "says", "said",
}


def _title_tokens(title: str) -> set:
    words = re.findall(r"[a-zA-ZÀ-ſ]+", (title or "").lower())
    return {w for w in words if len(w) > 3 and w not in _STOPWORDS}


def compute_coverage_overlap(df: pd.DataFrame) -> list:
    """Heuristic 'how many distinct sources ran a similar story' per article.

    No LLM call: pure title-token Jaccard similarity against every other
    article in the same (already-filtered) set. Approximate by design - RSS
    feeds don't give us a real story-clustering signal, and view/share
    counts aren't exposed at all, so this is the closest honest proxy for
    the mockup's "coverage overlap" metric.
    """
    titles = df["title"].tolist() if "title" in df.columns else []
    sources = df["source"].tolist() if "source" in df.columns else []
    token_sets = [_title_tokens(t) for t in titles]
    overlaps = []
    for i, s1 in enumerate(token_sets):
        distinct_sources = {sources[i]}
        if s1:
            for j, s2 in enumerate(token_sets):
                if i == j or not s2:
                    continue
                union = s1 | s2
                if not union:
                    continue
                jaccard = len(s1 & s2) / len(union)
                if jaccard >= COVERAGE_SIMILARITY_THRESHOLD:
                    distinct_sources.add(sources[j])
        overlaps.append(len(distinct_sources))
    return overlaps


def perspective_style(perspective: str) -> dict:
    return PERSPECTIVE_STYLE.get(perspective, DEFAULT_PERSPECTIVE_STYLE)


def synthesize_perspective(group: pd.DataFrame) -> str:
    """Deterministic, no-LLM-call synthesis: the highest-relevance article's
    main_narrative for this perspective, plus a note on how many articles
    that summarizes. This is a light aggregation of already-computed
    per-article fields, not a fresh model call - keeps the "no LLM calls on
    page load" rule intact. A dedicated LLM synthesis pass (computed once at
    pipeline time, like per-article analysis) would be a natural upgrade if
    a punchier multi-article summary is wanted later."""
    if group.empty:
        return "No relevant coverage from this perspective yet."
    top = group.sort_values("relevance_score", ascending=False).iloc[0]
    narrative = str(top.get("main_narrative", "")).strip()
    n = len(group)
    suffix = f" (based on {n} article{'s' if n != 1 else ''})"
    return (narrative or "No narrative extracted.") + suffix


# ---------------------------------------------------------------------------
# HTML fragment builders
# ---------------------------------------------------------------------------

def render_header():
    st.markdown(
        """
        <div class="app-header">
          <div class="brand"><span class="brand-mena">MENA</span> Narrative <span>Monitoring</span></div>
          <div class="tag">How different media frame the same geopolitical events — with disinformation signals</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_synthesis_card(df: pd.DataFrame):
    perspectives = [p for p in PERSPECTIVE_STYLE if p in df["perspective"].unique()] if not df.empty else []
    if not perspectives:
        return
    cols_html = []
    for p in perspectives:
        style = perspective_style(p)
        group = df[df["perspective"] == p]
        summary = html.escape(synthesize_perspective(group))
        cols_html.append(
            f'<div class="scol"><div class="pv" style="color:var({style["var"]})">{style["label"].title()}</div>'
            f'<p>{summary}</p></div>'
        )
    st.markdown(
        f"""
        <div class="synth">
          <h3><span class="badge">AI SYNTHESIS</span> How the perspectives diverge, right now</h3>
          <div class="synthgrid">{''.join(cols_html)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_article_card(row: pd.Series, coverage: int):
    style = perspective_style(row.get("perspective", ""))
    color_var = style["var"]
    badge_label = style["label"]
    source = html.escape(str(row.get("source", "")))
    time_ago = humanize_delta(row.get("published_parsed"))
    title = html.escape(str(row.get("title", "")))
    link = html.escape(str(row.get("link", "")) or "#")
    relevance = float(row.get("relevance_score", 0) or 0)
    tone = html.escape(str(row.get("tone", "unknown")))
    disinfo = int(row.get("disinfo_score", 0) or 0)
    disinfo_class = "d-hi" if disinfo >= 3 else "d-low"
    bar_pct = max(0, min(100, int(relevance / 5 * 100)))
    is_paywalled = bool(row.get("paywall", False))

    meta_time = f" · {time_ago}" if time_ago else ""
    paywall_badge = ' <span class="paywall" title="Source may paywall full articles">🔒</span>' if is_paywalled else ""

    st.markdown(
        f"""
        <div class="art" style="border-left-color:var({color_var})">
          <div class="top">
            <div class="src"><span class="persp" style="background:color-mix(in srgb, var({color_var}) 15%, transparent);color:var({color_var})">{badge_label}</span> {source}{paywall_badge}{meta_time}</div>
            <a class="open" href="{link}" target="_blank" rel="noopener noreferrer">Open article ↗</a>
          </div>
          <h3><a href="{link}" target="_blank" rel="noopener noreferrer">{title}</a></h3>
          <div class="meta">
            <span class="rel">Relevance <span class="bar"><i style="width:{bar_pct}%"></i></span> {relevance:.1f}</span>
            <span class="tone">Tone: {tone}</span>
            <span class="disinfo {disinfo_class}">Disinfo {disinfo}/5</span>
            <span class="metaitem">↺ covered by {coverage} source{'s' if coverage != 1 else ''}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Live mode pipeline (cached, rate-limited)
# ---------------------------------------------------------------------------

def resolve_api_key() -> str | None:
    """Find ANTHROPIC_API_KEY from the environment or Streamlit secrets.

    Two gotchas this works around:
    - st.secrets.get(...) raises StreamlitSecretNotFoundError (not a normal
      dict miss) when no secrets.toml/secret exists at all - very much the
      common case for local dev via .env, so this must be guarded or the
      whole app crashes the moment someone clicks Analyze.
    - Every pipeline module (keyword_generator.py, analyzer.py, via
      utils.get_anthropic_client()) only ever reads os.environ, not
      st.secrets. So a key found only in st.secrets is copied into
      os.environ here, or live mode would keep failing even with the key
      correctly set in Streamlit Cloud's Secrets UI.
    """
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY", None)
    except Exception:  # noqa: BLE001 - no secrets configured at all
        key = None
    if key:
        os.environ["ANTHROPIC_API_KEY"] = key
    return key


def run_live_pipeline(topic: str, _progress_callback=None) -> dict:
    """Run the full pipeline for a topic - featured or free-text, no
    difference in mechanism, though featured topics pull a curated subset of
    sources (see sources.get_sources_for_topic) rather than every source.
    Not cached - every call re-runs the pipeline (collection, relevance
    prefilter, per-article fetch, analysis) against a fresh set of sources.

    _progress_callback, if given, is called as (phase: str, done: int,
    total: int) during collection, relevance prefiltering, full-article
    fetching, and analysis (phase is "collecting" / "prefiltering" /
    "fetching_content" / "analyzing"), so the caller can show real progress
    instead of an opaque wait - see trigger_live_analysis.
    """
    from analyzer import analyze_articles, filter_by_relevance
    from article_fetcher import fetch_full_text_for_articles
    from feed_collector import collect_articles
    from keyword_generator import generate_keywords
    from sources import get_sources_for_topic

    keywords = generate_keywords(topic)
    articles = collect_articles(
        keywords,
        sources=get_sources_for_topic(topic),
        progress_callback=(
            lambda done, total, name: _progress_callback("collecting", done, total)
        ) if _progress_callback else None,
    )
    # Two-phase filtering: this cheap relevance-only pass judges title+
    # summary alone and drops anything unlikely to matter *before* the
    # expensive steps below (a real network fetch per article, then a full
    # narrative-analysis LLM call with a much larger prompt) ever run on it.
    # The keyword filter inside collect_articles already narrowed things
    # down by simple term matching; this adds actual judgment on top of
    # that, without paying full price for every article that judgment ends
    # up rejecting.
    articles = filter_by_relevance(
        articles,
        relevance_floor=RELEVANCE_FLOOR,
        progress_callback=(
            lambda done, total: _progress_callback("prefiltering", done, total)
        ) if _progress_callback else None,
    )
    # Try to fetch each kept article's actual body text before analysis -
    # a real read of the piece rather than just its RSS teaser. Silently
    # falls back to the RSS summary per-article wherever this fails
    # (network error, paywall, JS-rendered page, blocked scraper) - see
    # article_fetcher.py's docstring.
    articles = fetch_full_text_for_articles(
        articles,
        progress_callback=(
            lambda done, total: _progress_callback("fetching_content", done, total)
        ) if _progress_callback else None,
    )
    analyzed = analyze_articles(
        articles,
        progress_callback=(
            lambda done, total: _progress_callback("analyzing", done, total)
        ) if _progress_callback else None,
    )
    return {
        "topic": topic,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "keywords": keywords,
        "articles": analyzed,
    }


def trigger_live_analysis(topic: str) -> None:
    """Single entry point for launching a live analysis - used identically
    by a featured-chip click and a free-text search, so both behave exactly
    the same way: same per-session cap, same API-key guard, same loading
    animation, same caching. Everything is live now; there is no
    pre-computed fallback."""
    remaining = LIVE_MODE_REQUEST_CAP - st.session_state.live_mode_request_count
    if remaining <= 0:
        st.warning(
            f"Live-mode limit reached ({LIVE_MODE_REQUEST_CAP} requests this session) — "
            "reload the page to reset."
        )
        return

    api_key = resolve_api_key()
    if not api_key:
        st.error(
            "Live mode is not configured: no ANTHROPIC_API_KEY found in environment or st.secrets."
        )
        return

    st.session_state.live_mode_request_count += 1
    # Custom loading indicator (an animated connection graph - nodes fade in
    # and get linked by lines, like a link-analysis map assembling itself)
    # instead of st.spinner's default icon, plus a real progress line below
    # it fed by run_live_pipeline's progress callback - actual completion
    # counts, not just a decorative loop, since a topic with many collected
    # articles can otherwise sit on an opaque wait for tens of seconds.
    # Both st.empty() placeholders so they're cleanly removed once the
    # pipeline finishes, one way or the other.
    spinner_placeholder = st.empty()
    spinner_placeholder.markdown(build_loading_html(topic), unsafe_allow_html=True)
    progress_placeholder = st.empty()

    def _update_progress(phase: str, done: int, total: int) -> None:
        if total <= 0:
            return
        label = {
            "collecting": "Collecting from source",
            "prefiltering": "Checking relevance",
            "fetching_content": "Fetching full article",
            "analyzing": "Analyzing article",
        }.get(phase, "Processing")
        progress_placeholder.markdown(
            f'<div class="hint" style="text-align:center">{label} {done}/{total}…</div>',
            unsafe_allow_html=True,
        )

    try:
        live_payload = run_live_pipeline(topic, _progress_callback=_update_progress)
        st.session_state.active_label = live_payload["topic"]
        st.session_state.active_payload = live_payload
    except Exception as exc:  # noqa: BLE001 - surface a friendly error, don't crash the app
        st.error(f"Live analysis failed: {exc}")
    finally:
        spinner_placeholder.empty()
        progress_placeholder.empty()


def sync_featured_chip() -> None:
    """Keep the featured-topic pill widget's own state in sync with
    active_label after any live analysis. st.pills already deselects/
    reselects itself correctly when a chip is the thing that was clicked -
    this only matters for the other direction: a free-text search must not
    leave a stale chip looking selected once its results have been replaced.

    Streamlit forbids writing st.session_state[key] for a widget that has
    already been instantiated *in this run* (the pills widget renders
    earlier in the script than this is called) - raises
    StreamlitAPIException. So this defers the write: stash the desired
    value under a plain (non-widget) key and rerun; apply_pending_chip_sync()
    consumes it at the very top of the next run, before the pills widget is
    created, which Streamlit does allow. Only reruns when something
    actually needs to change."""
    desired = st.session_state.active_label if st.session_state.active_label in FEATURED_TOPICS else None
    if st.session_state.get("featured_topic_pill") != desired:
        st.session_state["_pending_featured_chip"] = desired
        st.rerun()


def apply_pending_chip_sync() -> None:
    """Consume a pending chip-selection change queued by sync_featured_chip,
    if any. Must run before the featured-topic st.pills() is instantiated."""
    if "_pending_featured_chip" in st.session_state:
        value = st.session_state.pop("_pending_featured_chip")
        st.session_state["featured_topic_pill"] = value
        # Keep click-detection (see "_last_seen_chip" below) in sync too, or
        # this forced value would itself look like a brand-new click next run.
        st.session_state["_last_seen_chip"] = value


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

render_header()

# Nothing is pre-selected on landing: only the search card (chips + search
# bar) shows until the visitor picks a featured topic or launches a live
# search. active_label/active_payload stay None until then.
if "active_label" not in st.session_state:
    st.session_state.active_label = None
if "active_payload" not in st.session_state:
    st.session_state.active_payload = None
if "live_mode_request_count" not in st.session_state:
    st.session_state.live_mode_request_count = 0

# --- Search card: featured-topic chips (live analysis, same as search) + free-text entry ---
apply_pending_chip_sync()  # must run before the pills widget below is instantiated
# st.container(key=...) rather than a raw <div class="searchcard"> opened in
# one st.markdown() and closed in another - Streamlit renders every element
# call as its own isolated DOM node, so a tag opened in one call and closed
# in a later one never actually wraps anything; the browser just auto-closes
# the orphaned opening tag as an empty element (the stray gray bar this
# replaces). A keyed container puts everything below inside one real div the
# .st-key-searchcard CSS rule can style - same technique already used for
# the featured-topic pills' scoped styling further down this stylesheet.
with st.container(key="searchcard"):
    st.markdown('<div class="picklabel">Pick a topic</div>', unsafe_allow_html=True)
    featured = st.pills(
        "Featured topics",
        FEATURED_TOPICS,
        selection_mode="single",
        default=st.session_state.active_label if st.session_state.active_label in FEATURED_TOPICS else None,
        label_visibility="collapsed",
        key="featured_topic_pill",
    )

    st.markdown('<div class="orsep"><span>or</span></div>', unsafe_allow_html=True)

    search_col, button_col = st.columns([5, 1])
    with search_col:
        live_topic_input = st.text_input(
            "Search",
            placeholder="Search any MENA topic",
            label_visibility="collapsed",
            key="live_topic_input",
        )
    with button_col:
        remaining = LIVE_MODE_REQUEST_CAP - st.session_state.live_mode_request_count
        analyze_clicked = st.button("Analyze", disabled=(remaining <= 0), use_container_width=True)

    if remaining <= 0:
        st.markdown(
            f'<div class="hint">Live-mode limit reached ({LIVE_MODE_REQUEST_CAP} requests this session) — '
            "reload the page to reset.</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="hint">Pick a featured topic or search any MENA '
            f"topic - both run a fresh live analysis ({remaining}/{LIVE_MODE_REQUEST_CAP} requests left "
            "this session).</div>",
            unsafe_allow_html=True,
        )

# --- React to whichever interaction fired this run ---
# st.pills persists its selected value across every rerun, not just the one
# where it was clicked - typing in the search box, for instance, reruns the
# whole script too. Comparing directly against active_label would re-fire
# trigger_live_analysis on every such unrelated rerun for as long as a
# previous attempt failed (no key, rate limit) and never updated
# active_label. "_last_seen_chip" tracks the raw widget value regardless of
# whether the analysis it triggered succeeded, so a click is only ever
# acted on once.
if "_last_seen_chip" not in st.session_state:
    st.session_state["_last_seen_chip"] = None
if featured != st.session_state["_last_seen_chip"]:
    st.session_state["_last_seen_chip"] = featured
    if featured:
        trigger_live_analysis(featured)

if analyze_clicked and live_topic_input.strip():
    label_before = st.session_state.active_label
    trigger_live_analysis(live_topic_input.strip())
    # Only the free-text path can leave a *stale* chip selected (a featured
    # topic's results replaced by a typed search) - sync only here, and
    # only when the search actually succeeded (active_label really
    # changed), so a failed attempt (no key, rate-limited) never touches
    # the chip or clears its own error message via the sync's rerun.
    if st.session_state.active_label != label_before:
        sync_featured_chip()

# Nothing selected yet (no featured topic picked, no live search run) - show
# only the search card above and stop here, per the "blank landing" request.
if st.session_state.active_payload is None:
    st.stop()

payload = st.session_state.active_payload
generated_at = payload.get("generated_at", "unknown")
try:
    generated_dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    updated_ago = humanize_delta(pd.Timestamp(generated_dt))
except (ValueError, AttributeError):
    updated_ago = ""

# --- Active-topic title: confirms what's being shown, before any results ---
is_featured_topic = st.session_state.active_label in FEATURED_TOPICS
topic_tag = "Featured topic" if is_featured_topic else "Live analysis"
st.markdown(
    f'<div class="topictitle"><span class="tt-tag">{topic_tag}</span>'
    f'<h2>{html.escape(st.session_state.active_label)}</h2></div>',
    unsafe_allow_html=True,
)

df = articles_to_df(payload)
df = df[df["relevance_score"] >= RELEVANCE_FLOOR].copy() if not df.empty else df

if df.empty:
    st.markdown(
        f'<div class="searchcard">No articles with relevance_score &ge; {RELEVANCE_FLOOR} for '
        f'"{html.escape(st.session_state.active_label)}".</div>',
        unsafe_allow_html=True,
    )
    st.stop()

# --- Filter pills: perspective + source ---
st.markdown('<div class="fgroup"><h4>Filter by perspective</h4></div>', unsafe_allow_html=True)
available_perspectives = sorted(df["perspective"].dropna().unique().tolist())
selected_perspectives = st.pills(
    "Perspective",
    available_perspectives,
    selection_mode="multi",
    default=available_perspectives,
    format_func=lambda p: perspective_style(p)["label"].title(),
    label_visibility="collapsed",
    key=f"perspective_pills_{st.session_state.active_label}",
)

st.markdown('<div class="fgroup"><h4>Filter by source</h4></div>', unsafe_allow_html=True)
available_sources = sorted(df["source"].dropna().unique().tolist())
selected_sources = st.pills(
    "Source",
    available_sources,
    selection_mode="multi",
    default=available_sources,
    label_visibility="collapsed",
    key=f"source_pills_{st.session_state.active_label}",
)

filtered = df[
    df["perspective"].isin(selected_perspectives or []) & df["source"].isin(selected_sources or [])
].copy()

# --- AI synthesis card ---
render_synthesis_card(filtered)

# --- Optional: tone distribution (spec requirement, tucked into an expander
# to keep the primary layout matching the mockup) ---
if not filtered.empty:
    with st.expander("📊 Tone distribution by perspective"):
        tone_counts = filtered.groupby(["perspective", "tone"]).size().reset_index(name="count")
        pivot = tone_counts.pivot(index="tone", columns="perspective", values="count").fillna(0)
        st.bar_chart(pivot)

# --- Results: sortable article list ---
count_label = f"{len(filtered)} relevant"
if updated_ago:
    count_label += f" · updated {updated_ago}"
st.markdown(
    f'<div class="sechead"><h2>Latest articles</h2><span class="count">{count_label}</span></div>',
    unsafe_allow_html=True,
)

sort_choice = st.radio("Sort by", SORT_OPTIONS, horizontal=True, label_visibility="collapsed", key=f"sort_{st.session_state.active_label}")

if filtered.empty:
    st.markdown('<div class="hint">No articles match the current filters.</div>', unsafe_allow_html=True)
else:
    filtered["coverage_overlap"] = compute_coverage_overlap(filtered)
    sort_map = {
        "Relevance": ("relevance_score", False),
        "Date": ("published_parsed", False),
        "Disinformation score": ("disinfo_score", False),
        "Coverage overlap": ("coverage_overlap", False),
    }
    sort_col, ascending = sort_map[sort_choice]
    ranked = filtered.sort_values(sort_col, ascending=ascending, na_position="last")
    for _, row in ranked.iterrows():
        render_article_card(row, int(row["coverage_overlap"]))

st.markdown(
    '<div class="note"><b>Portfolio demonstration.</b> 🔒 marks a source known to paywall some or '
    'all full articles - only the RSS title/summary is ever fetched here regardless, but clicking '
    '"Open article" may hit a paywall on the source\'s own site. "Coverage overlap" is computed '
    "locally from title-similarity across collected articles (no reliable view/share counts are "
    "exposed by RSS feeds) - an approximation, not a guaranteed story-clustering signal. All "
    "narrative/tone/disinformation fields are one LLM's read of a short title+summary, not "
    "verified fact.</div>",
    unsafe_allow_html=True,
)
