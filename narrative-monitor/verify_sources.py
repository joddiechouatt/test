"""Standalone script: verify every RSS URL in sources.py actually resolves.

Run this locally (NOT inside a network-restricted sandbox) before trusting
sources.py:

    python verify_sources.py

For each source it prints the HTTP status, whether feedparser could parse it,
and how many entries it found. Anything that fails should be fixed or
commented out in sources.py.

Build-environment note: this script itself could not be run to completion
during the initial build of this project because the build sandbox's network
egress policy blocks outbound requests to news domains (confirmed: CNN, BBC,
Al Jazeera, Times of Israel, Jerusalem Post, Press TV, Tehran Times,
France 24, and Le Monde were all rejected at the proxy with connection
errors). Run it yourself on a normal machine to get real results.
"""

from __future__ import annotations

import sys

import feedparser
import requests

from sources import SOURCES

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def verify_source(source: dict, timeout: int = 15) -> dict:
    name = source["name"]
    url = source["rss_url"]
    result = {"name": name, "url": url, "ok": False, "detail": ""}
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        parsed = feedparser.parse(resp.content)
        n_entries = len(parsed.entries)
        ok = resp.status_code == 200 and n_entries > 0 and not (
            parsed.bozo and n_entries == 0
        )
        result["ok"] = ok
        result["detail"] = f"HTTP {resp.status_code} | entries={n_entries} | bozo={parsed.bozo}"
    except Exception as exc:  # noqa: BLE001 - report any failure, don't crash
        result["detail"] = f"{type(exc).__name__}: {exc}"
    return result


def main() -> int:
    print(f"Verifying {len(SOURCES)} RSS sources...\n")
    all_ok = True
    for source in SOURCES:
        result = verify_source(source)
        status = "OK  " if result["ok"] else "FAIL"
        all_ok = all_ok and result["ok"]
        print(f"[{status}] {result['name']:25s} {result['detail']}")
        print(f"       {result['url']}")
    print()
    if not all_ok:
        print("One or more sources failed. Comment them out or fix the URL in sources.py.")
    else:
        print("All sources resolved successfully.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
