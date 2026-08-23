"""Streamlit dashboard for the Multi-Source Narrative Analysis Monitor.

Reads pre-computed data/<topic>.json files (no LLM calls, no exposed cost).
An optional, clearly-separated "live mode" lets a visitor analyze a custom
topic on demand, rate-limited per session and cached.
"""

from __future__ import annotations

import glob
import json
import os
from datetime import datetime

import pandas as pd
import streamlit as st

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DEFAULT_TOPIC_SLUG = "us-iran-conflict"
RELEVANCE_FLOOR = 3
LIVE_MODE_REQUEST_CAP = 3  # per browser session

st.set_page_config(page_title="Narrative Analysis Monitor", layout="wide")


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
    return df


# ---------------------------------------------------------------------------
# Sidebar: topic selector + filters
# ---------------------------------------------------------------------------

st.title("🌐 Multi-Source Narrative Analysis Monitor")
st.caption(
    "Portfolio demonstration — compares how outlets across the political spectrum "
    "frame a topic, using an LLM to extract narrative, tone, blame attribution, "
    "and disinformation signals."
)

topics = list_topics()

if not topics:
    st.warning(
        "No pre-computed data found in `data/`. Run `python run_pipeline.py \"<topic>\"` "
        "locally to generate a topic file, then reload this app."
    )
    st.stop()

default_label = None
for label, path in topics.items():
    if DEFAULT_TOPIC_SLUG in path:
        default_label = label
        break
default_index = list(topics.keys()).index(default_label) if default_label else 0

st.sidebar.header("Topic")
selected_label = st.sidebar.selectbox("Pre-computed topic", list(topics.keys()), index=default_index)
payload = load_topic_data(topics[selected_label])

generated_at = payload.get("generated_at", "unknown")
try:
    generated_dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    generated_display = generated_dt.strftime("%Y-%m-%d %H:%M UTC")
except (ValueError, AttributeError):
    generated_display = generated_at
st.sidebar.caption(f"Last updated: {generated_display}")

df = articles_to_df(payload)
if df.empty:
    st.warning("This topic file has no articles.")
    st.stop()

df = df[df["relevance_score"] >= RELEVANCE_FLOOR].copy()
if df.empty:
    st.warning(f"No articles with relevance_score >= {RELEVANCE_FLOOR} for this topic.")
    st.stop()

st.sidebar.header("Filters")
perspectives = sorted(df["perspective"].dropna().unique().tolist())
selected_perspectives = st.sidebar.multiselect("Perspective", perspectives, default=perspectives)

sources = sorted(df["source"].dropna().unique().tolist())
selected_sources = st.sidebar.multiselect("Source", sources, default=sources)

if "published_parsed" in df.columns and df["published_parsed"].notna().any():
    min_date = df["published_parsed"].min().date()
    max_date = df["published_parsed"].max().date()
    if min_date < max_date:
        date_range = st.sidebar.date_input("Date range", value=(min_date, max_date))
    else:
        date_range = (min_date, max_date)
else:
    date_range = None

filtered = df[
    df["perspective"].isin(selected_perspectives) & df["source"].isin(selected_sources)
].copy()

if date_range and isinstance(date_range, tuple) and len(date_range) == 2 and "published_parsed" in filtered.columns:
    start, end = date_range
    mask = filtered["published_parsed"].dt.date.between(start, end) | filtered["published_parsed"].isna()
    filtered = filtered[mask]

st.sidebar.caption(f"{len(filtered)} of {len(df)} relevant articles shown after filters.")


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

tab1, tab2, tab3 = st.tabs(
    ["📰 Narrative Comparison", "🎭 Tone Map", "⚠️ Disinformation Signals"]
)

with tab1:
    st.subheader("How each perspective frames the story")
    if filtered.empty:
        st.info("No articles match the current filters.")
    for perspective in sorted(filtered["perspective"].unique()):
        with st.expander(f"**{perspective}**", expanded=True):
            group = filtered[filtered["perspective"] == perspective]
            for _, row in group.iterrows():
                st.markdown(f"**{row.get('source', '')}** — {row.get('title', '')}")
                st.markdown(
                    f"> {row.get('main_narrative', '_no narrative extracted_')}"
                )
                cols = st.columns(3)
                cols[0].caption(f"Tone: `{row.get('tone', 'unknown')}`")
                cols[1].caption(f"Blame: {row.get('blame_attribution', 'n/a')}")
                cols[2].caption(f"Relevance: {int(row.get('relevance_score', 0))}/5")
                if row.get("link"):
                    st.caption(f"[source link]({row['link']})")
                st.divider()

with tab2:
    st.subheader("Tone distribution by perspective")
    if filtered.empty:
        st.info("No articles match the current filters.")
    else:
        tone_counts = (
            filtered.groupby(["perspective", "tone"]).size().reset_index(name="count")
        )
        pivot = tone_counts.pivot(index="tone", columns="perspective", values="count").fillna(0)
        st.bar_chart(pivot)
        with st.expander("Raw counts"):
            st.dataframe(pivot)

with tab3:
    st.subheader("Articles ranked by disinformation risk score")
    if filtered.empty:
        st.info("No articles match the current filters.")
    else:
        ranked = filtered.sort_values("disinfo_score", ascending=False)
        for _, row in ranked.iterrows():
            score = int(row.get("disinfo_score", 0))
            if score <= 0:
                continue
            signals = row.get("disinfo_signals", [])
            if isinstance(signals, str):
                signals = [signals]
            st.markdown(f"**[{score}/5]** {row.get('source', '')} — {row.get('title', '')}")
            if signals:
                st.markdown("- " + "\n- ".join(str(s) for s in signals))
            else:
                st.caption("No specific signals listed.")
            st.divider()
        if ranked["disinfo_score"].max() <= 0:
            st.info("No disinformation signals flagged among the filtered articles.")


# ---------------------------------------------------------------------------
# Optional live mode (secondary, rate-limited, cached)
# ---------------------------------------------------------------------------

st.divider()
st.header("🧪 Try your own topic (live mode)")
st.caption(
    "Runs the full pipeline live against a real LLM call, protected by a per-session "
    "request cap and result caching. This is a secondary demo feature, separate from "
    "the pre-computed dashboard above."
)

if "live_mode_request_count" not in st.session_state:
    st.session_state.live_mode_request_count = 0

remaining = LIVE_MODE_REQUEST_CAP - st.session_state.live_mode_request_count
st.caption(f"Live requests remaining this session: {max(remaining, 0)}/{LIVE_MODE_REQUEST_CAP}")


@st.cache_data(show_spinner=False)
def run_live_pipeline(topic: str) -> dict:
    """Run the full pipeline for a custom topic. Cached by topic string so
    repeated requests for the same topic don't re-call the LLM."""
    from datetime import timezone

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


live_topic = st.text_input("Custom topic", placeholder="e.g. Taiwan Strait tensions")
live_submit = st.button("Analyze", disabled=(remaining <= 0))

if remaining <= 0:
    st.warning(
        f"You've reached the live-mode limit of {LIVE_MODE_REQUEST_CAP} requests for this "
        "session. Reload the page to reset (this protects the demo's LLM budget)."
    )

if live_submit and live_topic.strip():
    api_key = os.environ.get("ANTHROPIC_API_KEY") or st.secrets.get("ANTHROPIC_API_KEY", None)
    if not api_key:
        st.error(
            "Live mode is not configured: no ANTHROPIC_API_KEY found in environment or "
            "st.secrets. The pre-computed dashboard above still works without it."
        )
    else:
        st.session_state.live_mode_request_count += 1
        with st.spinner(f"Collecting and analyzing articles about {live_topic!r}..."):
            try:
                live_payload = run_live_pipeline(live_topic.strip())
            except Exception as exc:  # noqa: BLE001 - surface a friendly error, don't crash the app
                st.error(f"Live analysis failed: {exc}")
                live_payload = None

        if live_payload:
            live_df = articles_to_df(live_payload)
            live_relevant = live_df[live_df["relevance_score"] >= RELEVANCE_FLOOR] if not live_df.empty else live_df
            st.success(
                f"Collected {len(live_df)} articles, {len(live_relevant)} relevant "
                f"(score >= {RELEVANCE_FLOOR})."
            )
            if not live_relevant.empty:
                for _, row in live_relevant.iterrows():
                    st.markdown(f"**{row.get('source', '')}** ({row.get('perspective', '')}) — {row.get('title', '')}")
                    st.markdown(f"> {row.get('main_narrative', '')}")
                    st.caption(f"Tone: `{row.get('tone', 'unknown')}` · Blame: {row.get('blame_attribution', '')}")
                    st.divider()
