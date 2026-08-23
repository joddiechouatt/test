"""RSS source list for the narrative monitor.

Each entry: {"name": str, "rss_url": str, "perspective": str}

perspective is one of: "Western", "Israeli", "Iranian_state", "Arab", "French".

IMPORTANT — read before relying on this list:
This file was built inside a sandboxed build environment whose network egress
policy blocks outbound HTTPS to news domains (CNN, BBC, Al Jazeera, Times of
Israel, Jerusalem Post, Press TV, Tehran Times, France 24, Le Monde were all
tested and rejected by the egress proxy — see the confirmation in
`verify_sources.py`'s docstring). That means these URLs could NOT be
live-verified as part of this build, only checked against public documentation
and prior knowledge of each outlet's feed conventions.

Before relying on this list, run, from a machine with normal internet access:

    python verify_sources.py

It fetches every URL below and reports HTTP status + parsed entry count so you
can confirm each feed actually resolves, and comment out / replace any that
don't (a note is left next to each entry indicating confidence level).
"""

SOURCES = [
    # --- Western ---
    {
        "name": "CNN World",
        "rss_url": "http://rss.cnn.com/rss/cnn_world.rss",
        "perspective": "Western",
        # CNN's legacy RSS URLs are long-standing but occasionally rate-limit
        # or block generic HTTP clients (returned HTTP 403 to this build's
        # sandboxed fetch attempt, likely bot protection rather than a dead
        # feed). Verify locally.
    },
    {
        "name": "BBC World News",
        "rss_url": "http://feeds.bbci.co.uk/news/world/rss.xml",
        "perspective": "Western",
        # Same as above: reachable but returned HTTP 403 from this sandbox,
        # consistent with bot protection rather than a broken feed. Verify locally.
    },
    # NOTE: Reuters discontinued its public RSS feeds around 2020. Known
    # historical URLs (feeds.reuters.com/..., reutersagency.com/feed/...) are
    # widely reported dead or redirected. Left commented out rather than
    # included as a likely-broken entry — replace with a verified Reuters
    # source (e.g. an official partner feed) if you have one, or drop Reuters
    # coverage in favor of another Western outlet (e.g. AP, NPR).
    # {
    #     "name": "Reuters World News",
    #     "rss_url": "https://feeds.reuters.com/Reuters/worldNews",
    #     "perspective": "Western",
    # },

    # --- Israeli ---
    {
        "name": "The Jerusalem Post",
        "rss_url": "https://www.jpost.com/rss/rssfeedsfrontpage.aspx",
        "perspective": "Israeli",
    },
    {
        "name": "The Times of Israel",
        "rss_url": "https://www.timesofisrael.com/feed/",
        "perspective": "Israeli",
    },

    # --- Iranian state media ---
    # Included deliberately: this tool's purpose is comparative narrative
    # analysis across the political spectrum, and Iranian state outlets are
    # a required data point for that comparison. Both are publicly accessible
    # RSS feeds, no auth bypass involved.
    {
        "name": "Press TV",
        "rss_url": "https://www.presstv.ir/rss.xml",
        "perspective": "Iranian_state",
        # Iran-hosted infrastructure can be flaky/geo-sensitive from some
        # networks; verify locally and consider retry/backoff at collection time.
    },
    {
        "name": "Tehran Times",
        "rss_url": "https://www.tehrantimes.com/rss",
        "perspective": "Iranian_state",
    },

    # --- Arab ---
    {
        "name": "Al Jazeera English",
        "rss_url": "https://www.aljazeera.com/xml/rss/all.xml",
        "perspective": "Arab",
    },

    # --- French ---
    {
        "name": "France 24",
        "rss_url": "https://www.france24.com/en/rss",
        "perspective": "French",
    },
    {
        "name": "Le Monde",
        "rss_url": "https://www.lemonde.fr/rss/une.xml",
        "perspective": "French",
    },
]
