"""Fetch each article's full body text, with the RSS summary as a fallback.

Analysis is far more accurate against the actual article than against an
RSS summary/dek, which is often just a one-line teaser the outlet (or an
aggregator) wrote for the feed rather than a representative sample of the
piece's own framing, tone, or claims. This module tries to fetch and
extract the real body text for each collected article; feed_collector's
RSS summary stays as the fallback for whatever fails - a network error, a
paywall stub, a JS-rendered page trafilatura can't parse out of static
HTML, or a site that blocks non-browser requests outright. All of those
are routine here, not exceptional - the whole point of this module is to
degrade to the summary silently rather than let a fetch failure break
anything downstream.
"""

from __future__ import annotations

import concurrent.futures
import logging

import requests
import trafilatura

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 12  # tighter than feed_collector's 15s - this runs once per
                       # article rather than once per source, so a single slow
                       # site shouldn't eat as much of the pipeline's time budget
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 narrative-monitor/1.0"
)
MAX_WORKERS = 8  # article-page fetches are network-bound and independent of
                  # each other, same reasoning as analyzer.py's LLM call pool -
                  # kept a bit higher since a plain GET is cheaper than an LLM
                  # call and outlet servers tolerate more concurrency than that

MIN_EXTRACTED_CHARS = 200   # shorter than this is almost always a paywall
                             # stub, a cookie-consent interstitial, or a
                             # failed extraction - not a real article body
MAX_CONTENT_CHARS = 4000    # caps LLM cost/latency per article: long enough
                             # to read the piece's actual framing, short
                             # enough that a full topic run (dozens of
                             # articles) doesn't multiply token spend by
                             # sending each one's entire multi-thousand-word
                             # body through the model


def _fetch_one(url: str) -> str | None:
    """Best-effort fetch + extraction of one article's main body text.

    Never raises - returns None on any failure (network error, non-200,
    an extraction that comes back empty or too short to be a real article)
    so the caller always has a clean signal to fall back to the RSS
    summary on.
    """
    if not url:
        return None
    try:
        response = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT
        )
        if response.status_code != 200:
            return None
        extracted = trafilatura.extract(
            response.text,
            include_comments=False,
            include_tables=False,
            favor_precision=True,  # prefer "clean but maybe incomplete" over
                                    # "complete but full of nav/ad boilerplate" -
                                    # boilerplate leaking into an LLM narrative
                                    # analysis is worse than a slightly short
                                    # extraction
        )
    except Exception as exc:  # noqa: BLE001 - one article's fetch failing must
                               # never take the whole pipeline down with it
        logger.info("article_fetcher: failed to fetch %s: %s", url, exc)
        return None

    if not extracted or len(extracted) < MIN_EXTRACTED_CHARS:
        return None
    return extracted[:MAX_CONTENT_CHARS]


def fetch_full_text_for_articles(
    articles: list[dict], progress_callback=None
) -> list[dict]:
    """Mutate-and-return each article dict with two new fields:

        "full_text":     the extracted body text, or None if unavailable.
        "content_source": "full_text" or "summary_only" - which one
                          analyzer.py actually ends up sending to the LLM,
                          surfaced so the UI/README can be honest about it
                          rather than silently claiming full-text coverage
                          it didn't get.

    Fetched concurrently (MAX_WORKERS at a time) since these are
    independent, network-bound requests - same rationale as
    analyzer.analyze_articles's thread pool for LLM calls.

    progress_callback(done, total), if given, is called once per article
    as it completes. Always invoked on the calling thread, never a worker
    - same contract as analyze_articles's callback, so it's safe to drive
    a Streamlit progress line with even though fetching itself is
    multi-threaded.
    """
    total = len(articles)
    if total == 0:
        return articles

    done = 0

    def _report():
        nonlocal done
        done += 1
        if progress_callback:
            progress_callback(done, total)

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(MAX_WORKERS, total)) as pool:
        future_map = {
            pool.submit(_fetch_one, article.get("link", "")): article
            for article in articles
        }
        for future in concurrent.futures.as_completed(future_map):
            article = future_map[future]
            try:
                full_text = future.result()
            except Exception as exc:  # noqa: BLE001 - never crash the batch
                logger.warning(
                    "article_fetcher: worker failed for %s: %s", article.get("link"), exc
                )
                full_text = None
            article["full_text"] = full_text
            article["content_source"] = "full_text" if full_text else "summary_only"
            _report()

    return articles


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.bbc.com/news"
    text = _fetch_one(url)
    if text:
        print(f"Extracted {len(text)} chars from {url}:\n")
        print(text[:1000])
    else:
        print(f"Extraction failed or returned nothing usable for {url}.")
