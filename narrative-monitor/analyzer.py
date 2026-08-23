"""Articles -> per-article LLM analysis (narrative, tone, blame, disinfo signals)."""

from __future__ import annotations

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
BETWEEN_CALLS_SLEEP = 0.3  # light rate-limit courtesy delay

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


def analyze_articles(articles: list[dict], model: str = MODEL, use_cache: bool = True) -> list[dict]:
    """Run one LLM analysis call per article and merge the result into each dict.

    Uses a disk cache (data/.cache/<hash>.json) keyed by link+title so re-runs
    over unchanged articles don't repay the LLM cost. A single bad/unparseable
    article never crashes the batch - it's flagged with analysis_error instead.
    """
    client = get_anthropic_client()
    analyzed = []

    for i, article in enumerate(articles):
        key = _cache_key(article)
        cached = _load_from_cache(key) if use_cache else None

        if cached is not None:
            analysis = cached
            logger.info("analyzer: [%d/%d] cache hit: %s", i + 1, len(articles), article.get("title", "")[:60])
        else:
            analysis = _analyze_one(client, article, model)
            if use_cache and analysis.get("analysis_error") is None:
                _save_to_cache(key, analysis)
            logger.info("analyzer: [%d/%d] analyzed: %s", i + 1, len(articles), article.get("title", "")[:60])
            time.sleep(BETWEEN_CALLS_SLEEP)

        merged = dict(article)
        merged.update(analysis)
        analyzed.append(merged)

    return analyzed


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
