"""RSS source list for the narrative monitor.

Each entry: {"name": str, "rss_url": str, "perspective": str, "paywall": bool}

perspective is one of: "Western", "Israeli", "Iranian_state", "Arab", "French".
"paywall" (optional, defaults to False if absent) marks a source known to
gate some/all article content behind a subscription — app.py shows a 🔒
badge next to these. Full article bodies are never fetched by this project
regardless (only RSS title/summary), but the "Open article" link a reader
clicks through to may hit a paywall, which is worth flagging honestly.

Verification status. It could NOT be live-verified from the build
environment — outbound HTTPS to every candidate domain below is blocked by
that sandbox's egress policy (confirmed again on i24news.tv, blocked, and
tasnimnews.com, DNS failure - consistent with the same policy). URLs are
graded by confidence:

- CONFIRMED (by the developer, via `verify_sources.py`, in earlier passes):
  BBC World News, The Jerusalem Post, Tehran Times, Al Jazeera (works
  outside Israel), France 24.
- KNOWN BROKEN, not guessable around: Reuters and AP both discontinued
  their public RSS feeds around 2020-2021 — there is no current official
  feed to point at. See the Reuters/AP entries below for the workaround
  used instead (Google News RSS, clearly not the same thing as the wire
  service's own feed).
- REMOVED (developer-confirmed unusable): The Times of Israel (HTTP 403 /
  bot-WAF block via one client, malformed-XML via another - same underlying
  block, two symptoms), Press TV (SSL CERTIFICATE_VERIFY_FAILED - a
  genuinely broken/self-issued cert on their end, confirmed from multiple
  networks including outside Israel, not a geo-block or a local trust-store
  issue), and Tasnim News Agency / Mehr News Agency (developer-confirmed
  blocking access outright - their own site denied the request rather than
  resolving as a normal feed). Times of Israel's replacements (i24NEWS,
  Arutz Sheva/INN) and Al Mayadeen (Press TV's remaining replacement
  candidate, after Tasnim/Mehr were dropped) are themselves UNVERIFIED -
  run verify_sources.py and trim any that fail before treating this list
  as final.
- UNVERIFIED, best-known URL from documentation/training knowledge, not
  independently tested: Middle East Eye, RFI, i24NEWS, Arutz Sheva/Israel
  National News, Al Mayadeen. i24NEWS and Al Mayadeen especially are
  genuinely low-confidence guesses at the RSS path, not just an
  unconfirmed-but-likely URL - these outlets' feed conventions aren't
  well-documented, so a 404 on first try is a real possibility, not just a
  formality. Section-specific (Middle East / world) variants for BBC and
  France 24 are also unverified even though their general feeds are
  confirmed - a wrong section-path guess would 404 even though the
  outlet's RSS in general works.

Run this locally (not in a network-restricted sandbox) before trusting any
of the unconfirmed entries below - this is genuinely required this pass,
not just good practice:

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
    # The Times of Israel was dropped (see file-level note): confirmed
    # bot/WAF-blocked via two different HTTP clients, not a dead-but-fixable
    # URL. Replaced with two candidates below, both UNVERIFIED.
    {
        "name": "i24NEWS",
        "rss_url": "https://www.i24news.tv/en/rss",
        "perspective": "Israeli",
        # UNVERIFIED, LOW confidence - i24NEWS's feed conventions aren't
        # well-documented; this is a best guess at the path, not a
        # known-good URL with an unconfirmed status. Free, no paywall
        # (ad/subscription-model TV network, not a metered news paywall).
    },
    {
        "name": "Arutz Sheva - Israel National News",
        "rss_url": "https://www.israelnationalnews.com/Rss.aspx",
        "perspective": "Israeli",
        # UNVERIFIED, medium-low confidence. Free, no paywall.
    },
    {
        "name": "The Jerusalem Post",
        "rss_url": "https://www.jpost.com/rss/rssfeedsfrontpage.aspx",
        "perspective": "Israeli",
        # CONFIRMED (HTTP 200, 26 entries). JPost gates some articles/
        # columns behind "JPost Premium" while most daily news stays free -
        # a partial/metered paywall, flagged accordingly. Kept as the
        # Israeli perspective's solid, already-verified source regardless
        # of how the two candidates above test out.
        "paywall": True,
    },

    # --- Iranian state / pro-Iran-axis media ---
    # Included deliberately: this tool's purpose is comparative narrative
    # analysis across the political spectrum, and this perspective is a
    # required data point for that comparison.
    #
    # Press TV was dropped (see file-level note): confirmed
    # SSL CERTIFICATE_VERIFY_FAILED from multiple networks including
    # outside Israel - a genuinely broken/self-issued certificate on their
    # end, not a geo-block or a local trust-store issue.
    #
    # Tasnim News Agency and Mehr News Agency were tried as replacement
    # candidates and dropped: developer-confirmed blocking access (their own
    # site denied/blocked the request) rather than resolving as a normal
    # feed. Not guessed around - if you want to try either again later, an
    # alternate URL or an access-restriction workaround would need to be
    # found and re-verified from scratch, same as any other candidate.
    {
        "name": "Al Mayadeen English",
        "rss_url": "https://english.almayadeen.net/rss",
        "perspective": "Iranian_state",
        # UNVERIFIED, LOW confidence on the URL. Also worth noting for
        # accuracy: Al Mayadeen is a Beirut-registered, Lebanon-based
        # outlet editorially aligned with the Iran/Hezbollah "resistance
        # axis" - not literally Iranian state broadcasting the way Press TV
        # or Tehran Times are. Grouped under Iranian_state per explicit
        # request, as a fallback for this perspective if the two Iranian-
        # domestic candidates above fail to resolve - but if you want that
        # editorial distinction visible, consider a separate perspective
        # label for it instead. Free, no paywall.
    },
    {
        "name": "Tehran Times",
        "rss_url": "https://www.tehrantimes.com/rss",
        "perspective": "Iranian_state",
        # CONFIRMED (HTTP 200, 30 entries). Kept as the Iranian_state
        # perspective's solid, already-verified source regardless of how
        # the three candidates above test out.
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
