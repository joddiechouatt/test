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
PREFILTER_CACHE_DIR = os.path.join(os.path.dirname(__file__), "data", ".cache_prefilter")

MAX_RETRIES = 3
RETRY_SLEEP_BASE = 2.0  # seconds, doubles each retry
MAX_WORKERS = 5  # concurrent LLM calls for cache-miss articles - network-bound
                  # work parallelizes well; kept modest to stay clear of
                  # per-account rate limits rather than maximize throughput

# Below this, an article isn't considered substantively about the topic and
# is dropped by filter_by_relevance() before the (much more expensive)
# full-text fetch + full analysis ever run on it. Also the threshold app.py
# applies again, post-analysis, as a final display filter - see that
# module's own use of RELEVANCE_FLOOR for why a second check there still
# matters even with this prefilter in place.
RELEVANCE_FLOOR = 3

PREFILTER_SYSTEM_PROMPT = """You are a relevance classifier for a media monitoring tool. \
Given a news article's title and a short summary, judge only whether the article is \
substantively about the given topic. Return STRICT JSON only, no markdown fences, no \
commentary, matching exactly this shape:

{"relevance_score": 0}

relevance_score: integer 0-5. 5 = clearly, substantively about the topic. 0 = \
unrelated or only mentions it in passing. Judge from the title and summary alone - \
they may be brief, so use your best judgment rather than demanding certainty.

Output valid JSON and nothing else."""

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
    # content_source is part of the key so a run that only had the RSS
    # summary available (fetch failed, paywalled, ...) never masks a later
    # run that succeeds at fetching the full article - without this, the
    # first (weaker) analysis would get served from cache forever.
    basis = (
        (article.get("link") or "")
        + "|" + (article.get("title") or "")
        + "|" + (article.get("content_source") or "")
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _prefilter_cache_key(article: dict) -> str:
    # No content_source component here (unlike _cache_key above) - the
    # prefilter always judges the RSS summary, never the full article, so
    # there's only ever one basis to key on for a given link+title.
    basis = (article.get("link") or "") + "|" + (article.get("title") or "")
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _cache_path(key: str, cache_dir: str = CACHE_DIR) -> str:
    return os.path.join(cache_dir, f"{key}.json")


def _load_from_cache(key: str, cache_dir: str = CACHE_DIR) -> dict | None:
    path = _cache_path(key, cache_dir)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _save_to_cache(key: str, analysis: dict, cache_dir: str = CACHE_DIR) -> None:
    os.makedirs(cache_dir, exist_ok=True)
    try:
        with open(_cache_path(key, cache_dir), "w", encoding="utf-8") as f:
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


def _prefilter_one(client, article: dict, model: str) -> int:
    """Cheap relevance-only LLM call against title+summary. Never raises -
    returns 0 (fail closed) on any failure after retries, same as
    _analyze_one's total-failure behavior, so a persistent API problem
    drops an article rather than letting it through unfiltered into the
    much more expensive full-text-fetch + full-analysis steps."""
    user_content = (
        f"Title: {article.get('title', '')}\n"
        f"Summary: {article.get('summary', '')}"
    )

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=100,  # just {"relevance_score": N} - no reason to
                                  # allow anywhere near _analyze_one's budget
                system=PREFILTER_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            text = "".join(
                block.text for block in response.content if getattr(block, "type", None) == "text"
            )
            parsed = safe_json_parse(text)
            if parsed is None:
                raise ValueError(f"could not parse JSON from LLM response: {text[:500]!r}")
            return max(0, min(5, int(parsed.get("relevance_score", 0))))
        except Exception as exc:  # noqa: BLE001 - retry transient errors, never crash
            last_error = exc
            is_last = attempt == MAX_RETRIES
            logger.warning(
                "analyzer: prefilter attempt %d/%d failed for %r: %s",
                attempt, MAX_RETRIES, article.get("title", "")[:60], exc,
            )
            if not is_last:
                time.sleep(RETRY_SLEEP_BASE * attempt)

    logger.warning(
        "analyzer: prefilter gave up on %r after %d attempts (%s) - dropping it",
        article.get("title", "")[:60], MAX_RETRIES, last_error,
    )
    return 0


def filter_by_relevance(
    articles: list[dict],
    model: str = MODEL,
    use_cache: bool = True,
    relevance_floor: int = RELEVANCE_FLOOR,
    progress_callback=None,
) -> list[dict]:
    """Drop articles that aren't substantively about the topic, judged from
    title+summary alone, *before* the expensive steps (full-text fetch,
    full narrative analysis) ever run on them.

    This is a genuine two-phase filter, not a duplicate of app.py's
    post-analysis RELEVANCE_FLOOR check: that later check still matters
    even with this prefilter in place, because analyze_articles computes
    its own relevance_score against the *full* article when one was
    fetched - richer context than this prefilter had, so it can
    legitimately disagree (in either direction) with this pass's summary-
    only judgment. This prefilter's only job is to cheaply skip articles
    unlikely to survive that final check at all, not to be the last word.

    Concurrent (MAX_WORKERS at a time) and disk-cached (data/.cache_prefilter/
    <hash>.json, keyed by link+title only - always the summary, so unlike
    analyze_articles's cache there's no content_source to key on) - same
    patterns as analyze_articles, see its docstring.

    progress_callback(done, total), if given, is called once per article as
    it completes (cache hit or freshly scored) - same contract as
    analyze_articles's callback.

    Returns the subset of `articles` whose relevance_score >= relevance_floor,
    in original order, each carrying a new "prefilter_relevance_score" field.
    """
    client = get_anthropic_client()
    total = len(articles)
    scores: list[int | None] = [None] * total
    done = 0

    def _report():
        nonlocal done
        done += 1
        if progress_callback:
            progress_callback(done, total)

    to_score = []
    for i, article in enumerate(articles):
        key = _prefilter_cache_key(article)
        cached = _load_from_cache(key, PREFILTER_CACHE_DIR) if use_cache else None
        if cached is not None:
            scores[i] = cached.get("relevance_score", 0)
            _report()
        else:
            to_score.append((i, article, key))

    if to_score:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(to_score))) as pool:
            future_map = {
                pool.submit(_prefilter_one, client, article, model): (i, article, key)
                for i, article, key in to_score
            }
            for future in concurrent.futures.as_completed(future_map):
                i, article, key = future_map[future]
                try:
                    score = future.result()
                except Exception:  # noqa: BLE001 - never crash the batch; fail closed
                    score = 0
                scores[i] = score
                if use_cache:
                    _save_to_cache(key, {"relevance_score": score}, PREFILTER_CACHE_DIR)
                _report()

    survivors = []
    for article, score in zip(articles, scores):
        if (score or 0) >= relevance_floor:
            merged = dict(article)
            merged["prefilter_relevance_score"] = score
            survivors.append(merged)

    logger.info(
        "analyzer: prefilter kept %d/%d articles (relevance_score >= %d)",
        len(survivors), total, relevance_floor,
    )
    return survivors


def _analyze_one(client, article: dict, model: str) -> dict:
    """Call the LLM once for a single article. Never raises: on any failure it
    returns a safe default analysis dict flagged with analysis_error."""
    # Prefer the full article body (article_fetcher.py) over the RSS
    # summary when one was actually fetched - a short feed teaser is a much
    # weaker basis for judging narrative framing/tone/blame than the real
    # piece. Falls back to the summary whenever full_text is missing (fetch
    # failed, paywalled, JS-rendered page, etc.) - every article still gets
    # analyzed either way, just on a shorter basis. The label told to the
    # model reflects which one it's actually reading, since a one-paragraph
    # summary and a multi-paragraph article warrant different confidence in
    # e.g. disinfo_signals - "sparse because it's short" isn't the same as
    # "sparse because the analysis missed something".
    full_text = article.get("full_text")
    if full_text:
        content_label, content = "Full article text", full_text
    else:
        content_label, content = "Summary (full article text unavailable)", article.get("summary", "")
    user_content = (
        f"Title: {article.get('title', '')}\n"
        f"{content_label}: {content}\n"
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
            "source": "Al Mayadeen English",
            "perspective": "Iranian_axis",
            "title": "Iran vows firm response to US 'aggression' in the region",
            "summary": "Officials condemned what they called Washington's "
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
