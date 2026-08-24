"""Shared helpers used across the pipeline modules."""

from __future__ import annotations

import json
import os
import re
import unicodedata


_DASH_CHARS = "‐‑‒–—―−"  # hyphen/en/em/minus variants


def slugify(topic: str) -> str:
    """Turn a free-text topic string into a filesystem-safe slug.

    "US-Iran conflict (2026)" -> "us-iran-conflict-2026"
    "Iran–USA" -> "iran-usa" (unicode dashes are normalized to "-" first;
    NFKD+ascii-ignore alone would just drop them, merging "Iran" and "USA")
    """
    text = re.sub(f"[{_DASH_CHARS}]", "-", topic)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "topic"


def safe_json_parse(text: str):
    """Defensively parse JSON out of an LLM response.

    LLMs frequently wrap JSON in markdown code fences, add leading/trailing
    prose, or produce near-valid JSON. This tries a few strategies before
    giving up, so a single malformed response never crashes the pipeline.

    Returns the parsed object, or None if nothing could be salvaged.
    """
    if not text:
        return None

    candidates = [text.strip()]

    # Strip ```json ... ``` or ``` ... ``` fences.
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence_match:
        candidates.append(fence_match.group(1).strip())

    # Grab the outermost {...} or [...] block.
    brace_match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if brace_match:
        candidates.append(brace_match.group(1).strip())

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue

    # Last resort: trim trailing commas, a common LLM slip-up, and retry.
    for candidate in candidates:
        try:
            repaired = re.sub(r",\s*([}\]])", r"\1", candidate)
            return json.loads(repaired)
        except (json.JSONDecodeError, TypeError):
            continue

    return None


def get_anthropic_client():
    """Build an Anthropic client using ANTHROPIC_API_KEY from the environment.

    Loads .env locally via python-dotenv if present. Never hardcode the key.
    Raises a clear RuntimeError if no key is configured anywhere (env or
    st.secrets, checked by the caller before this is invoked in app.py).
    """
    from dotenv import load_dotenv

    load_dotenv()

    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in, "
            "or set the environment variable / Streamlit secret directly."
        )
    return anthropic.Anthropic(api_key=api_key)
