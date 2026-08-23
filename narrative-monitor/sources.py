"""RSS source list for the narrative monitor.

Each entry: {"name": str, "rss_url": str, "perspective": str}

perspective is one of: "Western", "Israeli", "Iranian_state", "Arab", "French".

Verification status (last run by the developer via `verify_sources.py`):
- CONFIRMED resolving: CNN World, BBC World News, The Jerusalem Post,
  Tehran Times, France 24, Le Monde (all HTTP 200 with parsed entries).
- DROPPED: The Times of Israel — HTTP 403 with 0 entries even with a
  browser-like User-Agent, the signature of bot/WAF protection rather than a
  dead URL. Working around that is out of scope (this project is "public
  sources only... no auth bypass"), so it's commented out below, same as
  Reuters.
- LEFT ACTIVE, verify-locally-may-fail-by-design: Press TV, Al Jazeera
  English. Both failed verification with SSL certificate errors, but the
  cause turned out to be network-level blocking, not a broken feed or a
  local trust-store issue (a `certifi` upgrade did not fix it). Diagnosed by
  testing the URLs directly in a browser, from a country (Israel) that
  legally mandates ISP/carrier-level blocking of Al Jazeera, and where
  Iranian state media such as Press TV is subject to similar filtering —
  the browser showed a certificate mismatch on the home network and a
  different (untrusted-CA) error on a mobile-carrier network, i.e. two
  different technical implementations of the same national-level block,
  not two independent broken servers. These feeds are expected to resolve
  normally from most other locations, including Streamlit Community
  Cloud's hosting infrastructure. If you're verifying/collecting from
  inside a country that blocks one of these outlets, either route around it
  (VPN egress outside that country) or accept that `feed_collector.py`
  will simply log a warning and skip that source for this run — it's
  designed to degrade gracefully per-source rather than crash.

Re-run this whenever the list changes or before a fresh deploy:

    python verify_sources.py
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
    # Dropped: confirmed via verify_sources.py to return HTTP 403 with 0
    # entries even with a browser-like User-Agent — bot/WAF protection, not a
    # dead URL. Not worked around (see file-level note above). Israeli
    # perspective is still covered by Jerusalem Post.
    # {
    #     "name": "The Times of Israel",
    #     "rss_url": "https://www.timesofisrael.com/feed/",
    #     "perspective": "Israeli",
    # },

    # --- Iranian state media ---
    # Included deliberately: this tool's purpose is comparative narrative
    # analysis across the political spectrum, and Iranian state outlets are
    # a required data point for that comparison. Both are publicly accessible
    # RSS feeds, no auth bypass involved.
    {
        "name": "Press TV",
        "rss_url": "https://www.presstv.ir/rss.xml",
        "perspective": "Iranian_state",
        # verify_sources.py / browser testing showed a cert error from
        # Israel specifically (see file-level note above) — network-level
        # blocking, not a dead feed. Re-verify from an unblocked network
        # before assuming this URL is actually broken.
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
        # Confirmed network-level block, not a dead feed: Al Jazeera is
        # legally blocked at the ISP/carrier level in Israel (2024 law), so
        # verification from an Israeli network will fail here regardless of
        # local Python/cert setup. See file-level note above. This is the
        # sole Arab-perspective source in this list — don't drop it on the
        # basis of a test run from a country where it's blocked by law.
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
