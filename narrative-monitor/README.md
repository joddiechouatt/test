# Multi-Source Narrative Analysis Monitor

A portfolio project for an intelligence-analyst-style workflow: it monitors how
different news outlets across the political spectrum frame a given geopolitical
topic, uses an LLM to extract each article's narrative, tone, blame attribution,
and disinformation signals, and displays the comparison in a Streamlit dashboard.

**⚠️ Portfolio demonstration.** This is a personal/portfolio project showcasing
an LLM-assisted media-analysis pipeline, not a production monitoring system or
a claim of ground truth about any outlet's editorial intent. Treat every
`tone` / `blame_attribution` / `disinfo_score` field as one LLM's read of a
short title+summary, not a verified fact.

Everything the dashboard shows is a live analysis — there is no
pre-computed/cached dataset shipped in the repo. Three "featured topics"
(Iran–USA, Turkey–Israel, Strait of Hormuz) sit above the search bar as
one-click shortcuts, but picking one runs the exact same live pipeline
(keyword generation → RSS collection → per-article LLM analysis) as typing
a topic into the free-text search box — same per-session request cap, same
result caching, same cost. There's nothing "instant" about a featured
topic beyond not having to type it; it isn't free.

![Narrative comparison view](docs/screenshot-narrative.png)
<!-- Screenshot placeholder: narrative comparison tab -->

![Tone map view](docs/screenshot-tonemap.png)
<!-- Screenshot placeholder: tone distribution chart -->

![Disinformation signals view](docs/screenshot-disinfo.png)
<!-- Screenshot placeholder: disinfo-score-ranked article list -->

## What it does

1. **`keyword_generator.py`** — one LLM call turns a topic string (e.g.
   `"US-Iran conflict"`) into a multilingual (English/French/Hebrew) keyword
   taxonomy of "strong" (single-match-is-enough) and "weak"
   (needs-a-second-match) terms.
2. **`feed_collector.py`** — fetches every RSS source in `sources.py`,
   normalizes each entry, and filters to articles matching the keyword
   taxonomy (≥1 strong term, or ≥2 weak terms, across all three languages).
   A source that's down is logged and skipped — it never crashes the run.
   Every fetch has an explicit timeout (`REQUEST_TIMEOUT`, 15s) so one dead
   source can't stall the whole (sequential) collection loop.
3. **`analyzer.py`** — one LLM call per article extracts a structured
   narrative/tone/blame/disinformation-signal analysis as strict JSON, merged
   back into the article record. Cache misses run concurrently (a small
   thread pool, `MAX_WORKERS`) since these are network-bound calls — cuts
   real wall-clock time substantially for a topic with many articles, versus
   paying for each one sequentially. Results are cached to disk
   (`data/.cache/`) so re-running the pipeline never re-pays for an
   article it already analyzed. Both this and `feed_collector.py` accept an
   optional `progress_callback` so a caller (e.g. `app.py`'s live mode) can
   show real per-source/per-article progress instead of an opaque wait.
4. **`run_pipeline.py`** — CLI orchestrator: keyword generation → collection
   → analysis → `data/<topic-slug>.json`. A standalone convenience for
   inspecting a full pipeline run's output on disk (or scripting/cron'ing
   one outside the app); the running dashboard does not read its output.
5. **`app.py`** — a Streamlit dashboard where every topic, featured or
   free-text, runs the pipeline live via `trigger_live_analysis()`, guarded
   by a per-session request cap (`LIVE_MODE_REQUEST_CAP`) and cached by
   topic string (`st.cache_data`) so repeating the same topic in one
   session doesn't re-call the LLM.

## Design rationale

**Everything live, capped and cached rather than pre-computed.** Earlier
versions of this project shipped pre-computed JSON for a default topic so
the public dashboard had zero exposed LLM cost. That's no longer how it
works: every topic, including the three "featured" ones, runs the live
pipeline on demand. The trade-off is deliberate — `LIVE_MODE_REQUEST_CAP`
(3 per browser session, in `app.py`) and `st.cache_data` keyed by topic
string are what keep that bounded rather than unbounded, but a visitor
loading the deployed app and clicking a featured topic **does** spend a
real Anthropic API call, unlike the earlier read-only design. Budget for
that before deploying somewhere with meaningful traffic.

**RSS over scraping.** Every source in `sources.py` is a publicly published
RSS feed, not a scraped page. RSS is (a) explicitly offered by the
publisher for exactly this kind of syndication/aggregation use, (b)
structured, so parsing is robust to layout changes that would break an HTML
scraper, and (c) far lighter-weight than rendering/scraping full articles —
we only ever read title + summary, and never fetch full article bodies or
bypass any paywall or login.

**Generic keyword generation, not a hardcoded topic.** Rather than
hand-writing an "Iran" keyword list, `keyword_generator.py` asks the LLM to
build the taxonomy for whatever topic string it's given. That's what makes
"any topic" (the live-mode use case) possible at all, and it's also just
less brittle than a hand-maintained list for the default topic.

**Strict JSON everywhere, parsed defensively.** Every LLM prompt in this
project demands JSON-only output, and every call site
(`utils.safe_json_parse`) tries several repair strategies (strip markdown
fences, extract the outermost `{...}`/`[...]`, drop trailing commas) before
giving up. A single malformed response is logged and produces a safe
default record with `analysis_error` set — it never crashes the batch.

## Repository layout

```
narrative-monitor/
├── keyword_generator.py   # topic string -> multilingual keyword taxonomy (LLM)
├── feed_collector.py      # keywords + RSS sources -> filtered normalized articles
├── analyzer.py            # articles -> LLM analysis -> data/<topic>.json
├── run_pipeline.py        # orchestrates the 3 modules end-to-end for a topic
├── app.py                 # Streamlit dashboard - every topic runs live
├── loading_graph.py       # animated connection-graph loading indicator (pure HTML/CSS)
├── sources.py             # list of RSS sources with perspective labels
├── verify_sources.py      # standalone script: checks every RSS URL resolves
├── utils.py               # shared helpers: slugify, safe_json_parse, LLM client
├── data/                  # empty by default; analyzer.py's cache (.cache/, gitignored)
│                          # and run_pipeline.py's optional CLI output both land here
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Sources

`sources.py` lists RSS feeds with a `perspective` label
(`Western` / `Israeli` / `Iranian_state` / `Arab` / `French`) and an optional
`paywall: true` flag (shown as a 🔒 badge in the dashboard — only the RSS
title/summary is ever fetched, but the "Open article" link may hit a
paywall on the source's own site): BBC, Reuters, AP (Western); Times of
Israel, Jerusalem Post (Israeli); Press TV, Tehran Times (Iranian_state);
Al Jazeera, Middle East Eye (Arab); France 24, RFI (French).

**Reuters and AP have no current public RSS feed** — both wire services
discontinued theirs around 2020-2021, and no historical URL still works.
Rather than point at a dead link, both use a Google News RSS search scoped
to the outlet's domain (`site:reuters.com` / `site:apnews.com`) as a free,
public workaround. This is **not** the wire service's own feed — it's
Google's aggregation/excerpt of their articles, so summaries are shorter
and the framing is Google's snippet choice, not the outlet's own dek. Flagged
in `sources.py` so it's not mistaken for a first-party source.

**Verified status** (mixed — see `sources.py`'s file-level docstring for
the full per-source breakdown): BBC's general world feed, Jerusalem Post,
Press TV, Tehran Times, Al Jazeera, and France 24's general feed have all
been confirmed resolving with real entries in earlier passes. The
Middle-East-section variants used for BBC and France 24 here, plus Middle
East Eye and RFI, are **unverified** — best-known URLs, not independently
tested (each has a documented fallback in `sources.py` if it 404s). The
Times of Israel is known-flaky: it returns HTTP 403 via one HTTP client and
a malformed-XML parse error via another, both symptoms of the same bot/WAF
protection — included per request, but verify locally before relying on it.

Press TV and Al Jazeera also fail from **inside Israel specifically** —
Al Jazeera is blocked at the ISP/carrier level there by law (2024), and
Press TV, as Iranian state media, hits similar filtering — confirmed by two
different certificate errors on two different Israeli networks (home ISP
vs. mobile carrier), the signature of a network-level block, not a broken
feed. Both are expected to resolve normally from most other locations,
including Streamlit Community Cloud's hosting. **If you're verifying or
running the pipeline from a country that blocks one of these outlets**,
either use a VPN with an egress point elsewhere, or accept that
`feed_collector.py` will just log a warning and skip that source for the
run — it degrades gracefully per-source rather than crashing.

Re-run this after any change to `sources.py`, or before a fresh deploy:

```bash
python verify_sources.py
```

It reports HTTP status + parsed entry count per source (and a hint when a
failure looks like a local cert issue rather than a dead feed). Comment out
(or replace) anything that's confirmed actually broken.

## Running the pipeline locally

> **macOS tip:** if your clone lives inside `~/Desktop` or `~/Documents`
> with iCloud Drive's "Desktop & Documents Folders" sync on (or inside any
> Dropbox/OneDrive/Google Drive-synced folder), creating a venv there dumps
> tens of thousands of small files into a syncing directory and can make
> every shell command in that folder hang for a minute or more while the
> sync client churns through them. Put the venv itself outside the synced
> folder instead, e.g. `python -m venv ~/venvs/narrative-monitor`, and
> activate that — the repo can stay wherever it is.

```bash
# 1. Set up
python -m venv .venv && source .venv/bin/activate   # see the macOS tip above if this is slow
pip install -r requirements.txt
cp .env.example .env   # then fill in ANTHROPIC_API_KEY=sk-ant-...

# 2. Verify your RSS sources actually resolve from your network
python verify_sources.py

# 3. Run the dashboard - every topic (featured or typed) analyzes live
streamlit run app.py
```

`run_pipeline.py` still exists as an optional standalone CLI (keyword
generation → collection → analysis → `data/<topic-slug>.json`) if you want
a full run's output sitting on disk to inspect, script, or cron outside the
app - the running dashboard never reads its output:

```bash
python run_pipeline.py "Iran–USA"
```

Each module is also independently runnable for smoke-testing:

```bash
python keyword_generator.py "Taiwan Strait tensions"
python feed_collector.py "Taiwan Strait tensions"   # generates keywords first, then collects
python analyzer.py                                   # analyzes 3 built-in sample articles
```

`analyzer.py` caches every successful LLM analysis to `data/.cache/` keyed by
article link+title, so re-running the same article (via `run_pipeline.py`,
or the same topic surfacing it again in the app) never re-pays for it.

## Deploying to Streamlit Community Cloud

1. Push this repo to GitHub (`.env` and `data/.cache/` are gitignored on
   purpose and should **not** be committed - there's no `data/*.json` to
   worry about anymore, everything runs live).
2. On [share.streamlit.io](https://share.streamlit.io), create a new app
   pointing at this repo, branch, and `app.py` as the entry point.
3. In the app's **Settings → Secrets**, add:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```
   This is now **required**, not optional - every topic, including the
   three featured ones, calls the LLM. Without it, `app.py` shows a clean
   "not configured" message instead of crashing, but nothing will actually
   analyze.
4. Deploy. `LIVE_MODE_REQUEST_CAP` (`app.py`) caps requests per browser
   session and `st.cache_data` avoids re-calling the LLM for a topic already
   analyzed this session, but there is real per-visitor LLM cost now — see
   *Design rationale* above.

To change the three featured topics: edit `FEATURED_TOPICS` in `app.py` -
it's just a list of strings, nothing to generate or commit.

## Notes on the LLM provider

Uses the Anthropic API (`anthropic` Python SDK). The API key is read from
the `ANTHROPIC_API_KEY` environment variable — via `python-dotenv` locally
(see `.env.example`), or `st.secrets` in Streamlit Cloud. It is never
hardcoded anywhere in this repo.

## Constraints / scope

- Only public sources: RSS feeds and other publicly accessible pages. No
  paywalled content, no auth bypass, no scraping behind a login.
- Single-developer-runnable: a local pipeline run plus a free Streamlit
  Community Cloud deploy is the whole footprint — no infra beyond that.
