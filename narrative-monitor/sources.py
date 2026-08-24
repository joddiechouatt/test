"""RSS source list for the narrative monitor, grouped by perspective and
mapped per-topic so a topic only activates the perspectives relevant to it.

Each entry: {
    "name": str,
    "rss_url": str,
    "perspective": str,
    "language": str,       # "en" or "fr" - the edition actually being fetched
    "paywall": bool,       # optional, defaults to False if absent
    "verified": bool|None, # True = confirmed resolving via verify_sources.py;
                            # False = confirmed broken/blocked (excluded, not
                            # listed as an active entry at all - see REMOVED
                            # notes below); None = not yet tested this pass.
}

perspective is one of: "Western", "Israeli", "Iranian_axis", "Gulf",
"Qatari", "Turkish", "Maghreb", "Egyptian", "French".

"paywall" (defaults to False if absent) marks a source known to gate some/
all article content behind a subscription — app.py shows a 🔒 badge next to
these. Full article bodies are never fetched by this project regardless
(only RSS title/summary), but the "Open article" link a reader clicks
through to may hit a paywall, which is worth flagging honestly.

WHICH SOURCES A TOPIC USES: not every source is attached to every topic.
TOPIC_PERSPECTIVES (below) maps a featured topic string to the perspectives
relevant to it (e.g. a North-Africa-focused topic has no obvious reason to
pull Turkish or Gulf sources). Use get_sources_for_topic(topic) rather than
SOURCES directly when collecting for a specific topic - see its docstring
for how an unmapped (free-text/live-search) topic falls back.

============================================================================
VERIFICATION STATUS — read before trusting this list
============================================================================
This file could NOT be live-verified from the build environment for this
pass - outbound HTTPS to every candidate domain is blocked by that
sandbox's egress policy (confirmed again this pass on alarabiya.net and
trtworld.com, both EGRESS_BLOCKED - consistent with every prior check in
this project's history). Of the ~20 candidate feeds requested for this
MENA-wide expansion, only the four below have ever been confirmed by
actually running verify_sources.py on a real network (developer-run,
earlier passes) - everything else is a best-known-URL guess, graded by
confidence, with `"verified": None`:

- CONFIRMED (verified=True): BBC World News (general world feed),
  The Jerusalem Post, Al Jazeera English (works outside Israel; blocked at
  the ISP/carrier level inside Israel by law - not a dead feed), France 24
  (general feed).
- REMOVED (verified=False, confirmed unusable, not listed as active
  entries): The Times of Israel and i24NEWS (dropped this pass - i24NEWS
  wasn't in the requested candidate list for this restructure; Times of
  Israel remains bot/WAF-blocked per earlier passes). Every Iranian-
  domestic outlet tried: Press TV (SSL CERTIFICATE_VERIFY_FAILED - a
  genuinely broken/self-issued cert, confirmed from multiple networks
  including outside Israel and Streamlit Cloud itself), Tasnim News
  Agency / Mehr News Agency (blocking access outright per developer
  report), and IRNA (reported failing before being added here at all) -
  per explicit instruction, none of these are to be used; the Iranian_axis
  perspective represents this viewpoint via Al Mayadeen / Al-Manar instead.
  Tehran Times had been this perspective's one CONFIRMED-working domestic
  source but is excluded per that same instruction - see its entry, kept
  commented out below, if that call should be revisited.
- UNVERIFIED (verified=None) — every other entry below, including all of
  Gulf, Qatari's Al Jazeera is the exception (confirmed), Turkish, Maghreb,
  Egyptian, and the new French addition (L'Orient-Le Jour). These are
  best-known URLs from documentation/training knowledge, not independently
  tested. Several (Al Arabiya, Daily Sabah, Ahram Online, L'Orient-Le Jour
  especially) are genuinely low-confidence guesses at the RSS path - these
  outlets' feed conventions aren't well-documented in a way I can vouch
  for, so a 404 on first try is a real possibility for most of them.

Run this locally (not in a network-restricted sandbox) - genuinely
required before trusting any UNVERIFIED entry below, not just good
practice, given how many are new this pass:

    python verify_sources.py

It updates nothing automatically - after running it, come back and set
each entry's "verified" field to match, and drop (or comment out, per the
style already used below) anything confirmed broken.
============================================================================
"""

SOURCES = [
    # =========================================================================
    # Western
    # =========================================================================
    {
        "name": "BBC News - World",
        "rss_url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "perspective": "Western",
        "language": "en",
        "verified": True,  # HTTP 200, 38 entries (developer-run verify_sources.py)
    },
    # Reuters discontinued its public RSS feeds around 2020. No historical
    # URL still works (feeds.reuters.com/..., reutersagency.com/feed/...) -
    # confirmed dead across multiple earlier passes on this file. Workaround:
    # Google News RSS scoped to the outlet's domain. This is NOT Reuters'
    # own feed - it's Google's aggregation/excerpt, so summaries are shorter
    # and the framing is Google's snippet choice, not Reuters' own dek.
    # Also carries reuters.com's own subscriber paywall on the linked-through
    # articles.
    {
        "name": "Reuters (via Google News)",
        "rss_url": "https://news.google.com/rss/search?q=when:1d+site:reuters.com&hl=en-US&gl=US&ceid=US:en",
        "perspective": "Western",
        "language": "en",
        "paywall": True,
        "verified": None,
    },
    # Associated Press wound down its direct public feeds in the same era -
    # apnews.com has no first-party RSS. Same Google News workaround.
    {
        "name": "AP News (via Google News)",
        "rss_url": "https://news.google.com/rss/search?q=when:1d+site:apnews.com&hl=en-US&gl=US&ceid=US:en",
        "perspective": "Western",
        "language": "en",
        "verified": None,
    },

    # =========================================================================
    # Israeli
    # =========================================================================
    # The Times of Israel and i24NEWS (added in an earlier pass) are dropped:
    # not part of this restructure's requested candidate list. Times of
    # Israel remains confirmed bot/WAF-blocked from earlier passes if you
    # want to re-add it anyway.
    {
        "name": "Arutz Sheva - Israel National News",
        "rss_url": "https://www.israelnationalnews.com/Rss.aspx",
        "perspective": "Israeli",
        "language": "en",
        "verified": None,  # medium-low confidence on the URL
    },
    {
        "name": "The Jerusalem Post",
        "rss_url": "https://www.jpost.com/rss/rssfeedsfrontpage.aspx",
        "perspective": "Israeli",
        "language": "en",
        # JPost gates some articles/columns behind "JPost Premium" while
        # most daily news stays free - a partial/metered paywall.
        "paywall": True,
        "verified": True,  # HTTP 200, 26 entries (developer-run verify_sources.py)
    },

    # =========================================================================
    # Iranian / axis
    # =========================================================================
    # Deliberately NOT Iranian-domestic media: Press TV, Tasnim News Agency,
    # Mehr News Agency, and IRNA were all tried across earlier passes and
    # confirmed unreachable (broken cert, access blocked outright, or
    # reported failing before being added at all) - per explicit
    # instruction, none of these are used. This perspective represents the
    # pro-Iran narrative via accessible Beirut-based "resistance axis"
    # media instead, which is also why it's named Iranian_axis rather than
    # Iranian_state.
    #
    # Tehran Times had been this perspective's one CONFIRMED-working
    # domestic source (HTTP 200, 30 entries, verified twice in earlier
    # passes) - kept below, commented out, in case excluding it turns out
    # to be the wrong call once the axis candidates are actually tested.
    # {
    #     "name": "Tehran Times",
    #     "rss_url": "https://www.tehrantimes.com/rss",
    #     "perspective": "Iranian_axis",
    #     "language": "en",
    #     "verified": True,
    # },
    {
        "name": "Al Mayadeen English",
        "rss_url": "https://english.almayadeen.net/rss",
        "perspective": "Iranian_axis",
        "language": "en",
        # Beirut-registered, Lebanon-based, editorially aligned with the
        # Iran/Hezbollah "resistance axis" - not Iranian state broadcasting
        # itself. Primary source for this perspective per request.
        "verified": None,  # low confidence on the URL
    },
    {
        "name": "Al-Manar",
        "rss_url": "https://english.almanar.com.lb/feed",
        "perspective": "Iranian_axis",
        "language": "en",
        # Hezbollah's own media arm, Beirut-based. Secondary source per
        # request, kept if it resolves.
        "verified": None,  # low confidence on the URL (guessed /feed path)
    },

    # =========================================================================
    # Gulf (anti-Iran axis)
    # =========================================================================
    {
        "name": "Al Arabiya English",
        "rss_url": "https://english.alarabiya.net/rss.xml",
        "perspective": "Gulf",
        "language": "en",
        "verified": None,  # low confidence on the URL
    },
    {
        "name": "Arab News",
        "rss_url": "https://www.arabnews.com/rss.xml",
        "perspective": "Gulf",
        "language": "en",
        "verified": None,  # medium confidence
    },
    {
        "name": "The National (UAE)",
        "rss_url": "https://www.thenationalnews.com/rss.xml",
        "perspective": "Gulf",
        "language": "en",
        # Abu Dhabi Media outlet with a metered subscription tier on part
        # of its content.
        "paywall": True,
        "verified": None,  # low-medium confidence on the URL
    },

    # =========================================================================
    # Qatari / pan-Arab
    # =========================================================================
    {
        "name": "Al Jazeera English",
        "rss_url": "https://www.aljazeera.com/xml/rss/all.xml",
        "perspective": "Qatari",
        "language": "en",
        # Legally blocked at the ISP/carrier level inside Israel (2024 law)
        # - not a dead feed; works normally from most other locations
        # including Streamlit Community Cloud.
        "verified": True,  # HTTP 200 (developer-run verify_sources.py)
    },

    # =========================================================================
    # Turkish
    # =========================================================================
    {
        "name": "TRT World",
        "rss_url": "https://www.trtworld.com/rss",
        "perspective": "Turkish",
        "language": "en",
        "verified": None,  # medium-low confidence
    },
    {
        "name": "Daily Sabah",
        "rss_url": "https://www.dailysabah.com/rss",
        "perspective": "Turkish",
        "language": "en",
        "verified": None,  # low confidence - Daily Sabah's feeds have
        # historically been per-category with numeric IDs
        # (dailysabah.com/rssFeed/<id>); this is a guess at a simpler
        # general path that may not exist. Check their site footer for the
        # real feed link if this 404s.
    },

    # =========================================================================
    # North Africa / Maghreb (French-language editions used throughout)
    # =========================================================================
    {
        "name": "Jeune Afrique",
        "rss_url": "https://www.jeuneafrique.com/feed/",
        "perspective": "Maghreb",
        "language": "fr",
        "verified": None,  # medium confidence
    },
    {
        "name": "TSA - Tout Sur l'Algerie",
        "rss_url": "https://www.tsa-algerie.com/feed/",
        "perspective": "Maghreb",
        "language": "fr",
        "verified": None,  # medium confidence
    },
    {
        "name": "Hespress (French edition)",
        "rss_url": "https://fr.hespress.com/feed",
        "perspective": "Maghreb",
        "language": "fr",
        # Hespress's main site is Arabic-language; this is their French
        # edition (fr.hespress.com), chosen to match this perspective's
        # French-language framing and this project's en/fr/he keyword
        # matching.
        "verified": None,  # low-medium confidence
    },
    {
        "name": "Morocco World News",
        "rss_url": "https://www.moroccoworldnews.com/feed/",
        "perspective": "Maghreb",
        "language": "en",
        # English-language by design (per request), unlike the other three
        # Maghreb sources above.
        "verified": None,  # medium confidence
    },

    # =========================================================================
    # Egyptian
    # =========================================================================
    {
        "name": "Ahram Online",
        "rss_url": "https://english.ahram.org.eg/rss.aspx",
        "perspective": "Egyptian",
        "language": "en",
        "verified": None,  # low-medium confidence on the URL
    },
    {
        "name": "Egypt Independent",
        "rss_url": "https://egyptindependent.com/feed/",
        "perspective": "Egyptian",
        "language": "en",
        "verified": None,  # medium confidence
    },

    # =========================================================================
    # French
    # =========================================================================
    {
        "name": "France 24",
        "rss_url": "https://www.france24.com/en/rss",
        "perspective": "French",
        "language": "en",
        # Switched back to the general feed (from an unverified Middle-East
        # -section variant used in an earlier pass) since it's the one
        # actually CONFIRMED working, and this restructure's stakes are
        # higher with more perspectives depending on a stable core.
        "verified": True,  # HTTP 200, 23 entries (developer-run verify_sources.py)
    },
    {
        "name": "RFI",
        "rss_url": "https://www.rfi.fr/en/rss",
        "perspective": "French",
        "language": "en",
        "verified": None,  # best-known URL, not independently tested
    },
    {
        "name": "L'Orient-Le Jour",
        "rss_url": "https://www.lorientlejour.com/rss.xml",
        "perspective": "French",
        "language": "fr",
        # Lebanese francophone daily; has a metered subscription tier
        # ("L'Orient Today" / subscriber-only pieces) alongside free content.
        "paywall": True,
        "verified": None,  # low confidence on the URL
    },
]


# ============================================================================
# Per-topic source sets
# ============================================================================
# Maps a featured topic string to the perspectives relevant to it, so a
# topic doesn't pull from a single giant global pool of every perspective
# regardless of relevance (e.g. a Strait of Hormuz analysis has no obvious
# reason to include Maghreb or Egyptian sources).
#
# Keyed by the exact topic string used elsewhere in the app (FEATURED_TOPICS
# in app.py). A topic not listed here - i.e. any free-text live search - has
# no reliable way to be classified into a perspective subset without another
# LLM call, so get_sources_for_topic() falls back to every active source for
# those; see its docstring.
TOPIC_PERSPECTIVES: dict[str, list[str]] = {
    "Iran–USA": ["Western", "Israeli", "Iranian_axis", "Gulf", "Qatari", "French"],
    "Strait of Hormuz": ["Western", "Israeli", "Iranian_axis", "Gulf", "Qatari", "French"],
    "Turkey–Israel": [
        "Western", "Israeli", "Iranian_axis", "Gulf", "Qatari", "Turkish", "French",
    ],
    # Add further featured topics here as they're introduced - e.g. a
    # North-Africa-focused topic would list ["Western", "Maghreb", "French",
    # "Qatari"] or similar, activating the Maghreb sources above instead of
    # the conflict-actor perspectives.
}


def get_sources_for_topic(topic: str) -> list[dict]:
    """Return the SOURCES entries relevant to `topic`.

    Featured topics (keys of TOPIC_PERSPECTIVES) use their curated
    perspective subset. Any other topic - i.e. a free-text live search -
    falls back to every source in SOURCES: there's no reliable way to infer
    which perspectives are relevant to arbitrary user-typed text without an
    extra LLM call, which this project doesn't spend on the collection step.
    """
    perspectives = TOPIC_PERSPECTIVES.get(topic)
    if perspectives is None:
        return list(SOURCES)
    return [s for s in SOURCES if s["perspective"] in perspectives]
