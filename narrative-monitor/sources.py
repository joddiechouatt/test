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
Live-tested for real via a GitHub Actions run (.github/workflows/
verify-sources.yml, run #1, 2026-08-24) — GitHub-hosted runners have normal
internet access, unlike the build sandbox this file was originally drafted
in (which had every news/RSS domain egress-blocked; the workflow exists
specifically so this project doesn't depend on a local machine to verify
sources). Full result: 12/22 resolved, 10/22 failed.

- CONFIRMED (verified=True, 12): BBC News - World, Reuters (via Google
  News), AP News (via Google News), Arutz Sheva, The Jerusalem Post,
  Al Jazeera English, Jeune Afrique, TSA - Tout Sur l'Algerie, Hespress
  (French edition), Egypt Independent, France 24, RFI.
- FAILED (verified=False, 10, commented out below with the exact error):
  Al Mayadeen English (403), Al-Manar (404), Al Arabiya English (403),
  Arab News (403), The National/UAE (404), TRT World (404), Daily Sabah
  (200 but 0 entries / malformed), Morocco World News (403), Ahram Online
  (403), L'Orient-Le Jour (404). 403s read as bot/WAF blocking (out of
  scope to defeat, per this project's public-sources-only stance, same
  treatment as the earlier Times of Israel drop); 404s mean the guessed
  RSS path is wrong, not necessarily that the outlet has no feed at all.
- REMOVED earlier passes (not re-tested here, kept commented out further
  below): Times of Israel, i24NEWS, Tehran Times, Press TV, Tasnim News
  Agency, Mehr News Agency, IRNA — see git history / README for why each
  was dropped.

⚠️ Three perspectives currently have ZERO working sources as a result:
Iranian_axis, Gulf, Turkish. See README's Sources section for the
discussion of what to do about this.

Re-run this workflow (Actions tab → "Verify RSS Sources" → Run workflow,
or `python verify_sources.py` on any machine with real network access) any
time this list changes, and update the "verified" field + comment/uncomment
entries to match.
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
        "verified": True,  # HTTP 200, 29 entries (GH Actions run #1)
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
        "verified": True,  # HTTP 200, 100 entries (GH Actions run #1)
    },
    # Associated Press wound down its direct public feeds in the same era -
    # apnews.com has no first-party RSS. Same Google News workaround.
    {
        "name": "AP News (via Google News)",
        "rss_url": "https://news.google.com/rss/search?q=when:1d+site:apnews.com&hl=en-US&gl=US&ceid=US:en",
        "perspective": "Western",
        "language": "en",
        "verified": True,  # HTTP 200, 100 entries (GH Actions run #1)
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
        "verified": True,  # HTTP 200, 10 entries (GH Actions run #1)
    },
    {
        "name": "The Jerusalem Post",
        "rss_url": "https://www.jpost.com/rss/rssfeedsfrontpage.aspx",
        "perspective": "Israeli",
        "language": "en",
        # JPost gates some articles/columns behind "JPost Premium" while
        # most daily news stays free - a partial/metered paywall.
        "paywall": True,
        "verified": True,  # HTTP 200, 26 entries (GH Actions run #1)
    },

    # =========================================================================
    # Iranian / axis — ⚠️ ZERO working sources, see README
    # =========================================================================
    # Deliberately NOT Iranian-domestic media: Press TV, Tasnim News Agency,
    # Mehr News Agency, and IRNA were all tried across earlier passes and
    # confirmed unreachable (broken cert, access blocked outright, or
    # reported failing before being added at all) - per explicit
    # instruction, none of these are used. This perspective represents the
    # pro-Iran narrative via accessible Beirut-based "resistance axis"
    # media instead, which is also why it's named Iranian_axis rather than
    # Iranian_state. Both current candidates for that also failed real
    # testing (GH Actions run #1) - commented out below. This perspective
    # is currently EMPTY: no active source carries it.
    #
    # Tehran Times had been this perspective's one CONFIRMED-working
    # domestic source (HTTP 200, 30 entries, verified twice in earlier
    # passes) - kept below, commented out, in case excluding it turns out
    # to be the wrong call.
    # {
    #     "name": "Tehran Times",
    #     "rss_url": "https://www.tehrantimes.com/rss",
    #     "perspective": "Iranian_axis",
    #     "language": "en",
    #     "verified": True,
    # },
    # {
    #     "name": "Al Mayadeen English",
    #     "rss_url": "https://english.almayadeen.net/rss",
    #     "perspective": "Iranian_axis",
    #     "language": "en",
    #     "verified": False,  # HTTP 403, 0 entries, bozo=1 (GH Actions run #1) - bot/WAF block
    # },
    # {
    #     "name": "Al-Manar",
    #     "rss_url": "https://english.almanar.com.lb/feed",
    #     "perspective": "Iranian_axis",
    #     "language": "en",
    #     "verified": False,  # HTTP 404, 0 entries, bozo=1 (GH Actions run #1) - wrong/dead path
    # },

    # =========================================================================
    # Gulf (anti-Iran axis) — ⚠️ ZERO working sources, see README
    # =========================================================================
    # {
    #     "name": "Al Arabiya English",
    #     "rss_url": "https://english.alarabiya.net/rss.xml",
    #     "perspective": "Gulf",
    #     "language": "en",
    #     "verified": False,  # HTTP 403, 0 entries, bozo=1 (GH Actions run #1) - bot/WAF block
    # },
    # {
    #     "name": "Arab News",
    #     "rss_url": "https://www.arabnews.com/rss.xml",
    #     "perspective": "Gulf",
    #     "language": "en",
    #     "verified": False,  # HTTP 403, 0 entries, bozo=1 (GH Actions run #1) - bot/WAF block
    # },
    # {
    #     "name": "The National (UAE)",
    #     "rss_url": "https://www.thenationalnews.com/rss.xml",
    #     "perspective": "Gulf",
    #     "language": "en",
    #     "paywall": True,
    #     "verified": False,  # HTTP 404, 0 entries, bozo=1 (GH Actions run #1) - wrong/dead path
    # },

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
        # including Streamlit Community Cloud and GitHub Actions runners.
        "verified": True,  # HTTP 200, 25 entries (GH Actions run #1)
    },

    # =========================================================================
    # Turkish — ⚠️ ZERO working sources, see README
    # =========================================================================
    # {
    #     "name": "TRT World",
    #     "rss_url": "https://www.trtworld.com/rss",
    #     "perspective": "Turkish",
    #     "language": "en",
    #     "verified": False,  # HTTP 404, 0 entries (GH Actions run #1) - wrong/dead path
    # },
    # {
    #     "name": "Daily Sabah",
    #     "rss_url": "https://www.dailysabah.com/rss",
    #     "perspective": "Turkish",
    #     "language": "en",
    #     "verified": False,  # HTTP 200 but 0 entries, bozo=1 (GH Actions run #1) - feed
    #     # reached but empty/malformed; Daily Sabah's real feeds have
    #     # historically been per-category with numeric IDs
    #     # (dailysabah.com/rssFeed/<id>) - this generic path isn't it.
    # },

    # =========================================================================
    # North Africa / Maghreb (French-language editions used throughout)
    # =========================================================================
    {
        "name": "Jeune Afrique",
        "rss_url": "https://www.jeuneafrique.com/feed/",
        "perspective": "Maghreb",
        "language": "fr",
        "verified": True,  # HTTP 200, 30 entries (GH Actions run #1)
    },
    {
        "name": "TSA - Tout Sur l'Algerie",
        "rss_url": "https://www.tsa-algerie.com/feed/",
        "perspective": "Maghreb",
        "language": "fr",
        "verified": True,  # HTTP 200, 10 entries (GH Actions run #1)
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
        "verified": True,  # HTTP 200, 10 entries (GH Actions run #1)
    },
    # {
    #     "name": "Morocco World News",
    #     "rss_url": "https://www.moroccoworldnews.com/feed/",
    #     "perspective": "Maghreb",
    #     "language": "en",
    #     "verified": False,  # HTTP 403, 0 entries, bozo=1 (GH Actions run #1) - bot/WAF block
    # },

    # =========================================================================
    # Egyptian
    # =========================================================================
    # {
    #     "name": "Ahram Online",
    #     "rss_url": "https://english.ahram.org.eg/rss.aspx",
    #     "perspective": "Egyptian",
    #     "language": "en",
    #     "verified": False,  # HTTP 403, 0 entries, bozo=1 (GH Actions run #1) - bot/WAF block
    # },
    {
        "name": "Egypt Independent",
        "rss_url": "https://egyptindependent.com/feed/",
        "perspective": "Egyptian",
        "language": "en",
        "verified": True,  # HTTP 200, 10 entries (GH Actions run #1)
    },

    # =========================================================================
    # French
    # =========================================================================
    {
        "name": "France 24",
        "rss_url": "https://www.france24.com/en/rss",
        "perspective": "French",
        "language": "en",
        "verified": True,  # HTTP 200, 23 entries (GH Actions run #1)
    },
    {
        "name": "RFI",
        "rss_url": "https://www.rfi.fr/en/rss",
        "perspective": "French",
        "language": "en",
        "verified": True,  # HTTP 200, 21 entries (GH Actions run #1)
    },
    # {
    #     "name": "L'Orient-Le Jour",
    #     "rss_url": "https://www.lorientlejour.com/rss.xml",
    #     "perspective": "French",
    #     "language": "fr",
    #     "paywall": True,
    #     "verified": False,  # HTTP 404, 0 entries, bozo=1 (GH Actions run #1) - wrong/dead path
    # },
]


# ============================================================================
# Per-topic source sets
# ============================================================================
# Maps a featured topic string to the perspectives relevant to it, so a
# topic doesn't pull from a single giant global pool of every perspective
# regardless of relevance (e.g. a Strait of Hormuz analysis has no obvious
# reason to include Maghreb or Egyptian sources).
#
# Kept as-is even though Iranian_axis/Gulf/Turkish currently have zero
# active sources (see the ⚠️ warnings above): the mapping still describes
# which perspectives are conceptually relevant to each topic, and any
# source added back to one of those perspectives later flows into these
# topics automatically without touching this dict again.
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
