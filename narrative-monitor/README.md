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

`sources.py` covers the full MENA region (Middle East **and** North
Africa) across nine perspectives, not just the conflict actors —
`Western` / `Israeli` / `Iranian_axis` / `Gulf` / `Qatari` / `Turkish` /
`Maghreb` / `Egyptian` / `French`. Each entry also carries a `language`
("en" or "fr" — the edition actually being fetched), an optional
`paywall: true` flag (shown as a 🔒 badge in the dashboard — only the RSS
title/summary is ever fetched, but the "Open article" link may hit a
paywall on the source's own site), and a `verified` field (`True` =
confirmed resolving via a real `verify_sources.py` run, `False` = confirmed
broken and excluded from the active list — kept in the file commented out,
not deleted, `None` = not yet tested).

**Live-tested for real** via `.github/workflows/verify-sources.yml`
(GitHub Actions runners have normal internet access — this exists so
verification doesn't depend on anyone having a local machine at all; run
it from the repo's Actions tab, "Verify RSS Sources" → *Run workflow*, from
a phone or anywhere else). Two runs (2026-08-24):

- **Run #1** (direct outlet feeds): 12/22 resolved, 10 failed — leaving
  Iranian_axis, Gulf, and Turkish with zero working sources.
- **Run #2** (Google News `site:` proxy — see below — tried for exactly
  those 10 failed outlets): all 7 candidates resolved. **Every
  perspective now has at least one confirmed-working source.**

| Perspective | Working sources | Result |
|---|---|---|
| Western | BBC, Reuters (via Google News), AP (via Google News) | **3/3 OK** |
| Israeli | Arutz Sheva, Jerusalem Post | **2/2 OK** |
| Iranian_axis | Al Mayadeen (via Google News), Al-Manar (via Google News) | **2/2 OK** |
| Gulf | Al Arabiya, Arab News, The National (all via Google News) | **3/3 OK** |
| Qatari | Al Jazeera English | **1/1 OK** |
| Turkish | TRT World, Daily Sabah (both via Google News) | **2/2 OK** |
| Maghreb | Jeune Afrique, TSA, Hespress (FR edition) | **3/4 OK** (Morocco World News: HTTP 403, dropped) |
| Egyptian | Egypt Independent | **1/2 OK** (Ahram Online: HTTP 403, dropped) |
| French | France 24, RFI | **2/3 OK** (L'Orient-Le Jour: HTTP 404, dropped) |

**19 of 22 tested sources are active; all 19 are `verified: True`.** The 3
dropped (Morocco World News, Ahram Online, L'Orient-Le Jour) failed on
their direct feed and have no Google News proxy candidate tried yet — a
natural next step if either perspective needs a second source later.

Run #1's failure detail, exactly as reported: Al Mayadeen (403), Al-Manar
(404), Al Arabiya (403), Arab News (403), The National (404), TRT World
(404), Daily Sabah (HTTP 200 but 0 entries — feed reached, empty/malformed),
Morocco World News (403), Ahram Online (403), L'Orient-Le Jour (404). A 403
reads as bot/WAF blocking — out of scope to defeat, per this project's
public-sources-only stance, same treatment as the earlier Times of Israel
drop. A 404 means the guessed RSS path is wrong, not necessarily that the
outlet has no feed at all.

**Every "(via Google News)" source is Google's aggregation/snippet of the
outlet's articles, not the outlet's own RSS** — shorter summaries, and the
framing is Google's excerpt choice rather than the outlet's own dek (see
the Reuters/AP note below for where this pattern started). This is now 9
of the 19 active sources — worth keeping in mind when reading tone/framing
signals derived from these particular summaries.

**Not every topic pulls from every source.** `sources.py`'s
`TOPIC_PERSPECTIVES` maps each featured topic to the perspectives actually
relevant to it, and `get_sources_for_topic(topic)` — used by
`app.py`'s `run_live_pipeline` — filters `SOURCES` down to that subset:

```python
TOPIC_PERSPECTIVES = {
    "Iran–USA":         ["Western", "Israeli", "Iranian_axis", "Gulf", "Qatari", "French"],
    "Strait of Hormuz": ["Western", "Israeli", "Iranian_axis", "Gulf", "Qatari", "French"],
    "Turkey–Israel":    ["Western", "Israeli", "Iranian_axis", "Gulf", "Qatari", "Turkish", "French"],
}
```

A topic with no entry there — i.e. any free-text live search — falls back
to every source: there's no reliable way to infer which perspectives are
relevant to arbitrary typed text without another LLM call, which this
project doesn't spend on the collection step. Add a new featured topic's
row here (e.g. a Maghreb-focused topic → `["Western", "Maghreb", "French",
"Qatari"]`) to give it its own curated set instead of everything.

**Reuters and AP have no current public RSS feed** — both wire services
discontinued theirs around 2020-2021, and no historical URL still works.
Rather than point at a dead link, both use a Google News RSS search scoped
to the outlet's domain (`site:reuters.com` / `site:apnews.com`) as a free,
public workaround. This is **not** the wire service's own feed — it's
Google's aggregation/excerpt of their articles, so summaries are shorter
and the framing is Google's snippet choice, not the outlet's own dek.

**⚠️ Iranian-state domestic outlets are unreachable from every network this
project has been tested on.** Press TV (`SSL: CERTIFICATE_VERIFY_FAILED` —
a genuinely broken/self-issued certificate, confirmed from multiple
networks including outside Israel and Streamlit Cloud itself; a `certifi`
upgrade didn't fix it), Tasnim News Agency and Mehr News Agency (blocking
access outright, developer-confirmed), and IRNA (reported failing before
being added here at all) were all tried and dropped. The perspective was
renamed `Iranian_state` → `Iranian_axis` to match: the pro-Iran narrative
is represented instead via accessible Beirut-based "resistance axis"
media — **Al Mayadeen English** (primary) and **Al-Manar** (secondary) —
rather than Iranian state broadcasting itself. Both outlets' *direct*
feeds failed run #1 (Al Mayadeen: HTTP 403 bot-block; Al-Manar: HTTP 404
wrong/dead path); run #2 confirmed both resolve via the Google News proxy
instead, so this perspective is covered again, just via the aggregator
route rather than either outlet's own feed. Tehran Times had been this
perspective's one confirmed-working *domestic* source; it's kept in
`sources.py`, commented out, in case excluding it turns out to be the
wrong call.

**Verified status overall** (see `sources.py`'s file-level docstring and
each entry's `verified` field for the full breakdown): **19 of the 22
tested sources are confirmed working** on a real network (GitHub Actions,
2026-08-24 — 12 direct feeds in run #1, 7 more via Google News proxy in
run #2) — see the table above for the per-perspective split. The other 3
are commented out in `sources.py` with the exact failure recorded inline,
not deleted, in case a fixed URL or a Google-News-proxy candidate brings
one of them back later too.

Al Jazeera fails from **inside Israel specifically** — blocked at the
ISP/carrier level there by law (2024), confirmed by two different
certificate errors on two different Israeli networks (home ISP vs. mobile
carrier), the signature of a network-level block, not a broken feed. It's
expected to resolve normally from most other locations, including
Streamlit Community Cloud's hosting. **If you're verifying or running the
pipeline from a country that blocks an outlet**, either use a VPN with an
egress point elsewhere, or accept that `feed_collector.py` will just log a
warning and skip that source for the run — it degrades gracefully
per-source rather than crashing.

Re-run verification before trusting any `verified: None` entry or after any
change to `sources.py`. Two ways, same script either way:

- **No computer needed:** repo → Actions tab → "Verify RSS Sources" →
  *Run workflow* (also runs automatically on any push touching
  `sources.py`). Full plain-text output lands in the run's summary page —
  readable from the GitHub mobile app.
- **Locally**, if you have a machine with real network access:
  ```bash
  python verify_sources.py
  ```

Either way it reports HTTP status + parsed entry count per source (and a
hint when a failure looks like a local cert issue rather than a dead
feed). After running it, update each entry's `verified` field to match,
and comment out (the style already used for dropped sources above)
anything confirmed actually broken.

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
