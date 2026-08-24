"""Topic string -> multilingual keyword taxonomy, via a single LLM call."""

from __future__ import annotations

import json
import logging

from utils import get_anthropic_client, safe_json_parse

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-5"

LANGUAGES = {"en": "English", "fr": "French", "he": "Hebrew"}

# Generous headroom over what a well-bounded response should need (see the
# explicit 5-8-terms cap in the prompt below), not a target to fill. A topic
# with unusually many named entities (e.g. "Lebanon": government, militias,
# multiple past/current leaders, cities...) previously ran past the old
# 2000-token budget before finishing the JSON, producing a truncated,
# unparseable response and a hard failure for the whole live search.
MAX_TOKENS = 4000
MAX_RETRIES = 2

SYSTEM_PROMPT = """You are building a search keyword taxonomy for a media-monitoring \
tool. Given a topic, produce keywords for filtering news article titles/summaries.

Return STRICT JSON only, no markdown fences, no commentary, matching exactly this shape:

{
  "strong": {"en": ["..."], "fr": ["..."], "he": ["..."]},
  "weak": {"en": ["..."], "fr": ["..."], "he": ["..."]}
}

Rules:
- "strong" terms are specific enough that a single match strongly indicates the \
article is about the topic (named entities, specific places, named actors, \
proper nouns, specific event names).
- "weak" terms are generic/related terms that need a second match to be a \
reliable signal (broad nouns, generic descriptors, adjacent topics).
- Cover entities, places, actors, and related terms for the topic in each of \
English, French, and Hebrew.
- Each language list should have 5-8 strong terms and 5-8 weak terms - pick the \
single most useful terms for filtering, don't try to be exhaustive. This is a \
hard cap: stay within it even for a topic with many named entities to choose from.
- All terms lowercase except proper nouns where casing matters for the language.
- Output valid JSON and nothing else."""

RETRY_NUDGE = (
    "\n\nYour previous response did not fit the required format within the length "
    "limit. Be more concise this time: stay strictly within 5-8 terms per bucket "
    "per language, and output nothing but the JSON object."
)


def generate_keywords(topic: str, model: str = MODEL) -> dict:
    """Call the LLM to build a multilingual strong/weak keyword taxonomy.

    One call in the common case; retries up to MAX_RETRIES times (nudging the
    model to be more concise) if the response comes back truncated or
    otherwise unparseable, before giving up.

    Returns:
        {
          "topic": str,
          "strong": {"en": [...], "fr": [...], "he": [...]},
          "weak": {"en": [...], "fr": [...], "he": [...]},
        }

    Raises RuntimeError if no attempt produces a parseable taxonomy.
    """
    client = get_anthropic_client()

    text = ""
    parsed = None
    for attempt in range(1, MAX_RETRIES + 1):
        system_prompt = SYSTEM_PROMPT + (RETRY_NUDGE if attempt > 1 else "")
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": f"Topic: {topic}"}],
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        parsed = safe_json_parse(text)
        if isinstance(parsed, dict) and "strong" in parsed and "weak" in parsed:
            break
        logger.warning(
            "keyword_generator: attempt %d/%d produced an unparseable response for topic %r "
            "(stop_reason=%r, likely truncated if 'max_tokens')",
            attempt,
            MAX_RETRIES,
            topic,
            getattr(response, "stop_reason", None),
        )
        parsed = None

    if parsed is None:
        raise RuntimeError(
            f"keyword_generator: could not parse a valid keyword taxonomy from the "
            f"LLM response for topic {topic!r} after {MAX_RETRIES} attempt(s). "
            f"Last raw response:\n{text[:1000]}"
        )

    # Defensively normalize: ensure every language key exists as a list, even
    # if the model dropped one.
    for bucket in ("strong", "weak"):
        bucket_val = parsed.get(bucket) or {}
        if not isinstance(bucket_val, dict):
            bucket_val = {}
        normalized = {}
        for lang in LANGUAGES:
            terms = bucket_val.get(lang, [])
            if isinstance(terms, list):
                normalized[lang] = [str(t).strip() for t in terms if str(t).strip()]
            else:
                normalized[lang] = []
        parsed[bucket] = normalized

    parsed["topic"] = topic
    return parsed


if __name__ == "__main__":
    import sys

    topic_arg = sys.argv[1] if len(sys.argv) > 1 else "US-Iran conflict"
    result = generate_keywords(topic_arg)
    print(json.dumps(result, indent=2, ensure_ascii=False))
