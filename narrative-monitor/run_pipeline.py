"""CLI: run the full pipeline for a topic and write data/<topic_slug>.json.

Usage:
    python run_pipeline.py "US-Iran conflict"
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

from analyzer import analyze_articles
from feed_collector import collect_articles
from keyword_generator import generate_keywords
from utils import slugify

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

logger = logging.getLogger(__name__)


def run(topic: str, relevance_floor: int = 0) -> str:
    """Run keyword generation -> collection -> analysis -> save. Returns the
    path to the written JSON file."""

    print(f"[1/3] Generating keyword taxonomy for topic: {topic!r}")
    keywords = generate_keywords(topic)
    n_terms = sum(len(v) for bucket in ("strong", "weak") for v in keywords[bucket].values())
    print(f"      -> {n_terms} keyword terms across en/fr/he")

    print("[2/3] Collecting articles from RSS sources...")
    articles = collect_articles(keywords)
    print(f"      -> {len(articles)} articles matched the keyword filter")

    print("[3/3] Analyzing articles with the LLM (this may take a while)...")
    analyzed = analyze_articles(articles)

    relevant = [a for a in analyzed if a.get("relevance_score", 0) >= max(relevance_floor, 3)]
    errors = [a for a in analyzed if a.get("analysis_error")]

    os.makedirs(DATA_DIR, exist_ok=True)
    slug = slugify(topic)
    out_path = os.path.join(DATA_DIR, f"{slug}.json")

    payload = {
        "topic": topic,
        "topic_slug": slug,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "keywords": keywords,
        "articles": analyzed,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("\n--- Summary ---")
    print(f"Topic:              {topic}")
    print(f"Collected:          {len(articles)}")
    print(f"Analyzed:           {len(analyzed)}")
    print(f"Relevant (>=3):     {len(relevant)}")
    print(f"Analysis errors:    {len(errors)}")
    print(f"Written to:         {out_path}")

    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the narrative-monitor pipeline for a topic.")
    parser.add_argument("topic", help="Topic string, e.g. 'US-Iran conflict'")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable INFO-level logging from pipeline modules"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s"
    )

    try:
        run(args.topic)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
