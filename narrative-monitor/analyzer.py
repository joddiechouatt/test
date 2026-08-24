"""Articles -> per-article LLM analysis (narrative, tone, blame, disinfo signals)."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import logging
import os
import time

from utils import get_anthropic_client, safe_json_parse

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-5"
CACHE_DIR = os.path.join(os.path.dirname(__file__), "data", ".cache")

MAX_RETRIES = 3
RETRY_SLEEP_BASE = 2.0  # seconds, doubles each retry
MAX_WORKERS = 5  # concurrent LLM calls for cache-miss articles - network-bound
                  # work parallelizes well; kept modest to stay clear of
                  # per-account rate limits rather than maximize throughput

SYSTEM_PROMPT = """You are a media analyst. Given a news article's title and summary, \
analyze how it frames the story. Return STRICT JSON only, no markdown fences, no \
commentary, matching exactly this shape:

{
  "relevance_score": 0,
  "main_narrative": "",
  "tone": "",
  "blame_attribution": "",
  "key_claims": [""],
  "disinfo_signals": [""],
  "disinfo_score": 0
}

Field rules:
- relevance_score: integer 0-5. Is this article actually substantively about the \
given topic (5) or barely/tangentially related or not related at all (0)?
- main_narrative: one sentence describing how this specific article frames the story.
- tone: a single word/short phrase, e.g. neutral, alarmist, triumphalist, defensive, \
sympathetic, accusatory, dismissive.
- blame_attribution: who/what the article frames as responsible for the situation, \
in a few words. Use "none/not applicable" if the article doesn't assign blame.
- key_claims: list of the article's main factual claims, as short strings.
- disinfo_signals: list of specific disinformation-risk indicators present, e.g. \
"unsourced claim", "loaded/emotional language", "single anonymous source", \
"conflates unrelated events". Empty list if none observed.
- disinfo_score: integer 0-5, overall disinformation risk (0 = none observed, \
5 = severe).

Output valid JSON and nothing else."""


def _cache_key(article: dict) -> str:
    basis = (article.get("link") or "") + "|" + (article.get("title") or "")
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _cache_path(key: str) -> str:
    return os.path.join(CACHE_DIR, f"{key}.json")


def _load_from_cache(key: str) -> dict | None:
    path = _cache_path(key)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _save_to_cache(key: str, analysis: dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(_cache_path(key), "w", encoding="utf-8") as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.warning("analyzer: failed to write cache for key %s: %s", key, exc)


_DEFAULT_ANALYSIS = {
    "relevance_score": 0,
    "main_narrative": "",
    "tone": "unknown",
    "blame_attribution": "none/not applicable",
    "key_claims": [],
    "disinfo_signals": [],
    "disinfo_score": 0,
    "analysis_error": None,
}


def _normalize_analysis(parsed: dict) -> dict:
    result = dict(_DEFAULT_ANALYSIS)
    result["analysis_error"] = None
    if not isinstance(parsed, dict):
        return result

    try:
        result["relevance_score"] = max(0, min(5, int(parsed.get("relevance_score", 0))))
    except (TypeError, ValueError):
        result["relevance_score"] = 0
    result["main_narrative"] = str(parsed.get("main_narrative", "") or "")
    result["tone"] = str(parsed.get("tone", "") or "unknown")
    result["blame_attribution"] = str(parsed.get("blame_attribution", "") or "none/not applicable")

    key_claims = parsed.get("key_claims", [])
    result["key_claims"] = [str(c) for c in key_claims] if isinstance(key_claims, list) else []

    disinfo_signals = parsed.get("disinfo_signals", [])
    result["disinfo_signals"] = (
        [str(s) for s in disinfo_signals] if isinstance(disinfo_signals, list) else []
    )

    try:
        result["disinfo_score"] = max(0, min(5, int(parsed.get("disinfo_score", 0))))
    except (TypeError, ValueError):
        result["disinfo_score"] = 0

    return result


def _analyze_one(client, article: dict, model: str) -> dict:
    """Call the LLM once for a single article. Never raises: on any failure it
    returns a safe default analysis dict flagged with analysis_error."""
    user_content = (
        f"Title: {article.get('title', '')}\n"
        f"Summary: {article.get('summary', '')}\n"
        f"Source: {article.get('source', '')} (perspective: {article.get('perspective', '')})"
    )

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=1000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            text = "".join(
                block.text for block in response.content if getattr(block, "type", None) == "text"
            )
            parsed = safe_json_parse(text)
            if parsed is None:
                raise ValueError(f"could not parse JSON from LLM response: {text[:500]!r}")
            return _normalize_analysis(parsed)
        except Exception as exc:  # noqa: BLE001 - retry transient errors, never crash
            last_error = exc
            is_last = attempt == MAX_RETRIES
            logger.warning(
                "analyzer: attempt %d/%d failed for %r: %s",
                attempt,
                MAX_RETRIES,
                article.get("title", "")[:60],
                exc,
            )
            if not is_last:
                time.sleep(RETRY_SLEEP_BASE * attempt)

    result = dict(_DEFAULT_ANALYSIS)
    result["analysis_error"] = str(last_error)
    return result


def analyze_articles(
    articles: list[dict],
    model: str = MODEL,
    use_cache: bool = True,
    progress_callback=None,
) -> list[dict]:
    """Run one LLM analysis call per article and merge the result into each dict.

    Cache hits are resolved immediately on the calling thread; cache misses
    are analyzed concurrently (MAX_WORKERS at a time) via a thread pool -
    these are network-bound LLM calls, so threading cuts real wall-clock time
    substantially for topics with many articles, instead of paying for each
    one sequentially. Original article order is preserved in the output
    regardless of completion order.

    Uses a disk cache (data/.cache/<hash>.json) keyed by link+title so re-runs
    over unchanged articles don't repay the LLM cost. A single bad/unparseable
    article never crashes the batch - it's flagged with analysis_error instead.

    progress_callback(done, total), if given, is called once per article as
    it completes (cache hit or freshly analyzed). Always called from the
    calling thread - never from a worker - so it's safe to drive UI updates
    with (e.g. a Streamlit placeholder), even though analysis itself runs
    across multiple threads.
    """
    client = get_anthropic_client()
    total = len(articles)
    results: list[dict | None] = [None] * total
    done = 0

    def _report():
        nonlocal done
        done += 1
        if progress_callback:
            progress_callback(done, total)

    to_fetch = []
    for i, article in enumerate(articles):
        key = _cache_key(article)
        cached = _load_from_cache(key) if use_cache else None
        if cached is not None:
            merged = dict(article)
            merged.update(cached)
            results[i] = merged
            logger.info("analyzer: [%d/%d] cache hit: %s", i + 1, total, article.get("title", "")[:60])
            _report()
        else:
            to_fetch.append((i, article, key))

    if to_fetch:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(to_fetch))) as pool:
            future_map = {
                pool.submit(_analyze_one, client, article, model): (i, article, key)
                for i, article, key in to_fetch
            }
            for future in concurrent.futures.as_completed(future_map):
                i, article, key = future_map[future]
                try:
                    analysis = future.result()
                except Exception as exc:  # noqa: BLE001 - never crash the batch
                    analysis = dict(_DEFAULT_ANALYSIS)
                    analysis["analysis_error"] = str(exc)
                if use_cache and analysis.get("analysis_error") is None:
                    _save_to_cache(key, analysis)
                merged = dict(article)
                merged.update(analysis)
                results[i] = merged
                logger.info("analyzer: [%d/%d] analyzed: %s", done + 1, total, article.get("title", "")[:60])
                _report()

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    sample_articles = [
        {
            "source": "BBC World News",
            "perspective": "Western",
            "title": "Iran and US resume indirect talks over nuclear program",
            "summary": "Officials from Iran and the United States held a new round of "
            "indirect negotiations mediated by Oman, focused on nuclear enrichment limits.",
            "link": "https://example.com/1",
            "published": "2026-01-05",
        },
        {
            "source": "Press TV",
            "perspective": "Iranian_state",
            "title": "Iran vows firm response to US 'aggression' in the region",
            "summary": "Iranian officials condemned what they called Washington's "
            "provocative military posture, warning of a decisive response.",
            "link": "https://example.com/2",
            "published": "2026-01-05",
        },
        {
            "source": "The Jerusalem Post",
            "perspective": "Israeli",
            "title": "Analysis: Iran's nuclear timeline shortens amid new IAEA report",
            "summary": "A new IAEA assessment suggests Iran's breakout time has "
            "shortened, raising alarm among Israeli officials.",
            "link": "https://example.com/3",
            "published": "2026-01-06",
        },
    ]

    results = analyze_articles(sample_articles)
    print(json.dumps(results, indent=2, ensure_ascii=False))
