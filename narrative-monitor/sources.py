"""RSS source list for the narrative monitor.

Each entry: {"name": str, "rss_url": str, "perspective": str, "paywall": bool}

perspective is one of: "Western", "Israeli", "Iranian_state", "Arab", "French".
"paywall" (optional, defaults to False if absent) marks a source known to
gate some/all article content behind a subscription — app.py shows a 🔒
badge next to these. Full article bodies are never fetched by this project
regardless (only RSS title/summary), but the "Open article" link a reader
clicks through to may hit a paywall, which is worth flagging honestly.

Verification status: this file was rebuilt to the sources requested by the
project owner (BBC/Reuters/AP, Times of Israel/Jerusalem Post, Press TV/
Tehran Times, Al Jazeera/Middle East Eye, France 24/RFI), grouped by
perspective. It could NOT be live-verified from the build environment —
outbound HTTPS to every one of these domains is blocked by that sandbox's
egress policy (confirmed again on feeds.bbci.co.uk and middleeasteye.net
while building this revision). URLs below are graded by confidence:

- CONFIRMED (by the developer, via `verify_sources.py`, in an earlier pass
  on the previous source list): BBC World News, The Jerusalem Post, Press TV
  (works outside Israel), Tehran Times, Al Jazeera (works outside Israel),
  France 24.
- KNOWN BROKEN, not guessable around: Reuters and AP both discontinued
  their public RSS feeds around 2020-2021 — there is no current official
  feed to point at. See the Reuters/AP entries below for the workaround
  used instead (Google News RSS, clearly not the same thing as the wire
  service's own feed).
- KNOWN FLAKY: The Times of Israel returned HTTP 403 (bot/WAF block) via
  `requests`, and a "mismatched tag" XML parse error via `feedparser`'s own
  fetch (i.e. it likely serves a JS-challenge HTML page instead of the feed
  to non-browser clients, depending on exactly how the request looks to
  their WAF) — same underlying block, two different symptoms depending on
  which HTTP client hits it. Re-included here because it was explicitly
  requested; verify locally before relying on it.
- UNVERIFIED, best-known URL from documentation/training knowledge, not
  independently tested this pass: Middle East Eye, RFI. Section-specific
  (Middle East / world) variants for BBC and France 24 are also unverified
  even though their general feeds are confirmed - a wrong section-path
  guess would 404 even though the outlet's RSS in general works.

Run this locally (not in a network-restricted sandbox) before trusting any
of the unconfirmed/flaky entries below:

    python verify_sources.py
"""

SOURCES = [
    # --- Western ---
    {
        "name": "BBC News - Middle East",
        "rss_url": "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
        "perspective": "Western",
        # UNVERIFIED this pass: follows BBC's standard per-section feed
        # pattern (feeds.bbci.co.uk/news/<section>/rss.xml), and the
        # sibling "world" feed at this same host is CONFIRMED working
        # (HTTP 200, 38 entries). If this 404s, fall back to:
        # https://feeds.bbci.co.uk/news/world/rss.xml (confirmed, broader).
    },
    # Reuters discontinued its public RSS feeds around 2020. There is no
    # current official feed - every historical URL (feeds.reuters.com/...,
    # reutersagency.com/feed/...) is dead or redirected, confirmed multiple
    # times in earlier passes on this file. Workaround: Google News RSS,
    # scoped to reuters.com via a site: search. This is NOT Reuters' own
    # feed - it's Google's aggregation/snippet of Reuters articles, so
    # summaries will be shorter and framing may be Google's excerpt choice
    # rather than Reuters' own dek. Free and genuinely public, but flagged
    # here so it's not mistaken for a first-party feed. Also has a
    # subscriber paywall on reuters.com itself for some articles.
    {
        "name": "Reuters (via Google News)",
        "rss_url": "https://news.google.com/rss/search?q=when:1d+site:reuters.com&hl=en-US&gl=US&ceid=US:en",
        "perspective": "Western",
        "paywall": True,
    },
    # Associated Press also wound down its direct public RSS feeds in the
    # same era - apnews.com does not currently publish a straightforward
    # first-party feed. Same Google News workaround, same caveat as Reuters
    # above (not AP's own feed).
    {
        "name": "AP News (via Google News)",
        "rss_url": "https://news.google.com/rss/search?q=when:1d+site:apnews.com&hl=en-US&gl=US&ceid=US:en",
        "perspective": "Western",
    },

    # --- Israeli ---
    {
        "name": "The Times of Israel",
        "rss_url": "https://www.timesofisrael.com/feed/",
        "perspective": "Israeli",
        # KNOWN FLAKY: see file-level note above (bot/WAF protection, two
        # different symptoms depending on HTTP client). Re-included per
        # request; run verify_sources.py before relying on it, and don't be
        # surprised if feed_collector.py logs a fetch failure for this one.
    },
    {
        "name": "The Jerusalem Post",
        "rss_url": "https://www.jpost.com/rss/rssfeedsfrontpage.aspx",
        "perspective": "Israeli",
        # CONFIRMED (HTTP 200, 26 entries). JPost gates some articles/
        # columns behind "JPost Premium" while most daily news stays free -
        # a partial/metered paywall, flagged accordingly.
        "paywall": True,
    },

    # --- Iranian state media ---
    # Included deliberately: this tool's purpose is comparative narrative
    # analysis across the political spectrum, and Iranian state outlets are
    # a required data point for that comparison. Both are publicly
    # accessible RSS feeds, no auth bypass involved, both free (no paywall).
    {
        "name": "Press TV",
        "rss_url": "https://www.presstv.ir/rss.xml",
        "perspective": "Iranian_state",
        # CONFIRMED working outside Israel. Blocked at the network level
        # from inside Israel (see file-level note in the project's git
        # history / README) - not a dead feed, a geo-block.
    },
    {
        "name": "Tehran Times",
        "rss_url": "https://www.tehrantimes.com/rss",
        "perspective": "Iranian_state",
        # CONFIRMED (HTTP 200, 30 entries).
    },

    # --- Arab ---
    {
        "name": "Al Jazeera English",
        "rss_url": "https://www.aljazeera.com/xml/rss/all.xml",
        "perspective": "Arab",
        # CONFIRMED working outside Israel; legally blocked at the ISP/
        # carrier level inside Israel (2024 law) - not a dead feed.
    },
    {
        "name": "Middle East Eye",
        "rss_url": "https://www.middleeasteye.net/rss",
        "perspective": "Arab",
        # UNVERIFIED this pass - best-known URL for this outlet's feed, not
        # independently tested (egress blocked from the build sandbox to
        # middleeasteye.net). Free, independent, non-profit-funded outlet -
        # no paywall. Check verify_sources.py output before relying on it;
        # if it 404s, look for the feed link in their site footer.
    },

    # --- French ---
    {
        "name": "France 24 - Middle East",
        "rss_url": "https://www.france24.com/en/middle-east/rss",
        "perspective": "French",
        # UNVERIFIED this pass: follows France 24's regional-section URL
        # pattern (france24.com/en/<region>/...). The general feed at this
        # same host is CONFIRMED working (HTTP 200, 23 entries). If this
        # 404s, fall back to: https://www.france24.com/en/rss
    },
    {
        "name": "RFI",
        "rss_url": "https://www.rfi.fr/en/rss",
        "perspective": "French",
        # UNVERIFIED this pass - best-known URL for RFI's English feed, not
        # independently tested. Public broadcaster, free, no paywall.
    },
]
