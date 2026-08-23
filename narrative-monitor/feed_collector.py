"""Fetch, filter, and normalize articles from the RSS sources in sources.py."""

from __future__ import annotations

import logging
import time
from html import unescape
from html.parser import HTMLParser

import feedparser

from sources import SOURCES

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 narrative-monitor/1.0"
)


class _TagStripper(HTMLParser):
    """Minimal HTML-tag stripper for RSS summaries (which are often HTML)."""

    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def get_text(self):
        return "".join(self.parts)


def _strip_html(text: str) -> str:
    if not text:
        return ""
    stripper = _TagStripper()
    try:
        stripper.feed(text)
        return unescape(stripper.get_text()).strip()
    except Exception:  # noqa: BLE001 - never let a malformed snippet crash collection
        return unescape(text).strip()


def _flatten_keywords(keywords: dict) -> dict:
    """Flatten the {strong/weak: {lang: [...]}} structure into two lower-cased sets."""
    flat = {"strong": set(), "weak": set()}
    for bucket in ("strong", "weak"):
        by_lang = keywords.get(bucket, {}) or {}
        for terms in by_lang.values():
            for term in terms or []:
                term = str(term).strip().lower()
                if term:
                    flat[bucket].add(term)
    return flat


def _matches(text: str, flat_keywords: dict) -> bool:
    text_l = text.lower()
    strong_hit = any(term in text_l for term in flat_keywords["strong"])
    if strong_hit:
        return True
    weak_hits = sum(1 for term in flat_keywords["weak"] if term in text_l)
    return weak_hits >= 2


def _fetch_one_source(source: dict):
    """Fetch and parse a single RSS source. Never raises - returns [] on failure."""
    name = source["name"]
    url = source["rss_url"]
    try:
        parsed = feedparser.parse(url, request_headers={"User-Agent": USER_AGENT})
        if parsed.bozo and not parsed.entries:
            raise parsed.bozo_exception or RuntimeError("feedparser reported bozo with no entries")
        return parsed.entries
    except Exception as exc:  # noqa: BLE001 - log and continue, never crash the pipeline
        logger.warning("feed_collector: failed to fetch %r (%s): %s", name, url, exc)
        return []


def collect_articles(keywords: dict, sources: list | None = None, delay: float = 0.0) -> list[dict]:
    """Fetch every source, filter by keyword match, normalize, and dedupe.

    Args:
        keywords: taxonomy from keyword_generator.generate_keywords().
        sources: override the source list (mainly for testing); defaults to SOURCES.
        delay: optional seconds to sleep between source fetches, to be polite.

    Returns:
        List of normalized article dicts:
        {source, perspective, title, summary, link, published}
    """
    sources = sources if sources is not None else SOURCES
    flat_keywords = _flatten_keywords(keywords)

    collected: list[dict] = []
    seen = set()

    for source in sources:
        entries = _fetch_one_source(source)
        kept_from_source = 0

        for entry in entries:
            title = _strip_html(entry.get("title", ""))
            summary = _strip_html(entry.get("summary", "") or entry.get("description", ""))
            link = (entry.get("link", "") or "").strip()
            published = entry.get("published", "") or entry.get("updated", "") or ""

            if not title and not summary:
                continue

            combined_text = f"{title} {summary}"
            if not _matches(combined_text, flat_keywords):
                continue

            dedupe_key = (link.lower() if link else "") or title.strip().lower()
            if not dedupe_key or dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            collected.append(
                {
                    "source": source["name"],
                    "perspective": source["perspective"],
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "published": published,
                }
            )
            kept_from_source += 1

        logger.info(
            "feed_collector: %s -> %d entries fetched, %d kept after filtering",
            source["name"],
            len(entries),
            kept_from_source,
        )

        if delay:
            time.sleep(delay)

    return collected


if __name__ == "__main__":
    import json
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if len(sys.argv) > 1:
        from keyword_generator import generate_keywords

        kw = generate_keywords(sys.argv[1])
    else:
        # Minimal built-in fallback so this can be smoke-tested without an API key.
        kw = {
            "strong": {"en": ["iran"], "fr": ["iran"], "he": ["איראן"]},
            "weak": {"en": ["nuclear", "sanctions"], "fr": [], "he": []},
        }

    articles = collect_articles(kw)
    print(f"Collected {len(articles)} articles")
    print(json.dumps(articles[:5], indent=2, ensure_ascii=False))
