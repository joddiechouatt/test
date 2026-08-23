"""Topic string -> multilingual keyword taxonomy, via a single LLM call."""

from __future__ import annotations

import json

from utils import get_anthropic_client, safe_json_parse

MODEL = "claude-sonnet-4-5"

LANGUAGES = {"en": "English", "fr": "French", "he": "Hebrew"}

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
- Each language list should have at least 5 strong terms and 5 weak terms.
- All terms lowercase except proper nouns where casing matters for the language.
- Output valid JSON and nothing else."""


def generate_keywords(topic: str, model: str = MODEL) -> dict:
    """Call the LLM once to build a multilingual strong/weak keyword taxonomy.

    Returns:
        {
          "topic": str,
          "strong": {"en": [...], "fr": [...], "he": [...]},
          "weak": {"en": [...], "fr": [...], "he": [...]},
        }

    Raises RuntimeError if the LLM response can't be parsed into valid JSON
    after defensive repair attempts.
    """
    client = get_anthropic_client()

    response = client.messages.create(
        model=model,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Topic: {topic}"}],
    )

    text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )
    parsed = safe_json_parse(text)

    if not isinstance(parsed, dict) or "strong" not in parsed or "weak" not in parsed:
        raise RuntimeError(
            f"keyword_generator: could not parse a valid keyword taxonomy from the "
            f"LLM response for topic {topic!r}. Raw response:\n{text[:1000]}"
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
