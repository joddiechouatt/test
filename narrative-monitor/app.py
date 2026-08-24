"""Streamlit dashboard for the Multi-Source Narrative Analysis Monitor.

Reads pre-computed data/<topic>.json files (no LLM calls, no exposed cost).
An optional, clearly-separated "live mode" lets a visitor analyze a custom
topic on demand, rate-limited per session and cached.

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

import glob
import html
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DEFAULT_TOPIC_SLUG = "us-iran-conflict"
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
    "Iranian_state": {"label": "IRANIAN", "var": "--iran"},
    "Arab": {"label": "ARAB", "var": "--arab"},
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

CSS = """
<style>
:root{
  --bg:#0F1620; --panel:#18222F; --panel2:#1F2C3D; --line:#2A3849;
  --ink:#EAF0F7; --mut:#8A9BB2; --ice:#9FB6D4;
  --amber:#E0A458; --teal:#4FB0A5; --rose:#D08B7A;
  --west:#5B8DEF; --isr:#4FB0A5; --iran:#D06B6B; --arab:#E0A458; --fr:#B08BD0;
}
.stApp{background:var(--bg);color:var(--ink);}
.main .block-container{max-width:1080px;padding-top:1.5rem;padding-bottom:3rem;}
.stApp, .stApp p, .stApp span, .stApp label{color:var(--ink);}
[data-testid="stMarkdownContainer"] p{color:var(--ink);}

.app-header{padding:6px 0 18px;border-bottom:1px solid var(--line);margin-bottom:22px}
.brand{font-size:22px;font-weight:700;letter-spacing:.5px}
.brand span{color:var(--amber)}
.tag{color:var(--mut);font-size:13px;margin-top:2px}

.searchcard{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px;margin-bottom:4px}
.hint{color:var(--mut);font-size:12px;margin-top:10px;font-style:italic}

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

st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data
def list_topics() -> dict:
    """Return {display_name: file_path} for every data/*.json file."""
    topics = {}
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "*.json"))):
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            label = payload.get("topic", os.path.basename(path))
            topics[label] = path
        except (json.JSONDecodeError, OSError):
            continue
    return topics


@st.cache_data
def load_topic_data(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


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
          <div class="brand">Narrative <span>Monitoring</span></div>
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

    meta_time = f" · {time_ago}" if time_ago else ""

    st.markdown(
        f"""
        <div class="art" style="border-left-color:var({color_var})">
          <div class="top">
            <div class="src"><span class="persp" style="background:color-mix(in srgb, var({color_var}) 15%, transparent);color:var({color_var})">{badge_label}</span> {source}{meta_time}</div>
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

@st.cache_data(show_spinner=False)
def run_live_pipeline(topic: str) -> dict:
    """Run the full pipeline for a custom topic. Cached by topic string so
    repeated requests for the same topic don't re-call the LLM."""
    from analyzer import analyze_articles
    from feed_collector import collect_articles
    from keyword_generator import generate_keywords

    keywords = generate_keywords(topic)
    articles = collect_articles(keywords)
    analyzed = analyze_articles(articles)
    return {
        "topic": topic,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "keywords": keywords,
        "articles": analyzed,
    }


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

render_header()

topics = list_topics()
if not topics:
    st.markdown(
        '<div class="searchcard">No pre-computed data found in <code>data/</code>. '
        'Run <code>python run_pipeline.py "&lt;topic&gt;"</code> locally to generate one, then reload.</div>',
        unsafe_allow_html=True,
    )
    st.stop()

topic_labels = list(topics.keys())
default_topic_label = next((label for label in topic_labels if DEFAULT_TOPIC_SLUG in topics[label]), topic_labels[0])

if "active_label" not in st.session_state:
    st.session_state.active_label = default_topic_label
if "active_payload" not in st.session_state:
    st.session_state.active_payload = load_topic_data(topics[default_topic_label])
if "live_mode_request_count" not in st.session_state:
    st.session_state.live_mode_request_count = 0

# --- Search card: live-mode entry point + featured (pre-computed) topic chips ---
st.markdown('<div class="searchcard">', unsafe_allow_html=True)
search_col, button_col = st.columns([5, 1])
with search_col:
    live_topic_input = st.text_input(
        "Search",
        placeholder="Search any geopolitical topic… e.g. Taiwan Strait tensions",
        label_visibility="collapsed",
        key="live_topic_input",
    )
with button_col:
    remaining = LIVE_MODE_REQUEST_CAP - st.session_state.live_mode_request_count
    analyze_clicked = st.button("Analyze", disabled=(remaining <= 0), use_container_width=True)

featured = st.pills(
    "Featured topics",
    topic_labels,
    selection_mode="single",
    default=st.session_state.active_label if st.session_state.active_label in topic_labels else None,
    label_visibility="collapsed",
    key="featured_topic_pill",
)

if remaining <= 0:
    st.markdown(
        f'<div class="hint">Live-mode limit reached ({LIVE_MODE_REQUEST_CAP} requests this session) — '
        "reload the page to reset. Featured topics above still work.</div>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f'<div class="hint">Pick a featured topic for an instant, pre-computed view — or search any topic '
        f"to build a fresh live analysis ({remaining}/{LIVE_MODE_REQUEST_CAP} requests left this session).</div>",
        unsafe_allow_html=True,
    )
st.markdown("</div>", unsafe_allow_html=True)

# --- Resolve which dataset is active this run ---
if featured and featured != st.session_state.active_label:
    st.session_state.active_label = featured
    st.session_state.active_payload = load_topic_data(topics[featured])

if analyze_clicked and live_topic_input.strip():
    api_key = os.environ.get("ANTHROPIC_API_KEY") or st.secrets.get("ANTHROPIC_API_KEY", None)
    if not api_key:
        st.error(
            "Live mode is not configured: no ANTHROPIC_API_KEY found in environment or "
            "st.secrets. Pick a featured topic above instead - that works without it."
        )
    else:
        st.session_state.live_mode_request_count += 1
        with st.spinner(f"Collecting and analyzing articles about {live_topic_input!r}..."):
            try:
                live_payload = run_live_pipeline(live_topic_input.strip())
                st.session_state.active_label = live_payload["topic"]
                st.session_state.active_payload = live_payload
            except Exception as exc:  # noqa: BLE001 - surface a friendly error, don't crash the app
                st.error(f"Live analysis failed: {exc}")

payload = st.session_state.active_payload
generated_at = payload.get("generated_at", "unknown")
try:
    generated_dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    updated_ago = humanize_delta(pd.Timestamp(generated_dt))
except (ValueError, AttributeError):
    updated_ago = ""

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
    '<div class="note"><b>Portfolio demonstration.</b> "Coverage overlap" is computed locally '
    "from title-similarity across collected articles (no reliable view/share counts are exposed "
    "by RSS feeds) - an approximation, not a guaranteed story-clustering signal. All narrative/tone/"
    "disinformation fields are one LLM's read of a short title+summary, not verified fact.</div>",
    unsafe_allow_html=True,
)
