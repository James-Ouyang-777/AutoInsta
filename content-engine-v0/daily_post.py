#!/usr/bin/env python3
"""Daily travel post — picks today's topic from topics.yaml and posts to Instagram.

Run directly:
    python daily_post.py

Or via cron (see README for setup instructions).
Logs are written to stdout/stderr; redirect to a file in your cron entry.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

from content_engine.generator import GenerationError, generate
from content_engine.image_gen import ImageGenError, generate_image
from content_engine.poster import PostError, post_instagram


def _build_caption(variant: dict) -> str:
    parts = [variant.get("hook", ""), variant.get("body", "")]
    cta = variant.get("cta", "")
    if cta:
        parts.append(cta)
    hashtags = " ".join(variant.get("hashtags", []))
    if hashtags:
        parts.append(hashtags)
    return "\n\n".join(p for p in parts if p)


def main() -> None:
    now = datetime.datetime.now()
    print(f"[{now}] Starting daily post")

    # Load topics and pick today's
    config_path = Path(__file__).parent / "topics.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    topics = config["topics"]
    idx = datetime.date.today().toordinal() % len(topics)
    today = topics[idx]

    topic = today["topic"]
    keywords = [k.strip() for k in today["keywords"].split(",")]
    print(f"[{now}] Topic: {topic}")

    brand = {
        "voice": "inspiring, wanderlust-inducing",
        "audience": "travel enthusiasts and adventure seekers",
        "reading_level": "casual",
        "prohibited": [],
    }

    # Step 1: generate caption
    print(f"[{now}] Generating caption...")
    try:
        variants = generate(
            platform="instagram",
            topic=topic,
            keywords=keywords,
            brand=brand,
            cta_style="soft",
            n_variants=1,
        )
    except GenerationError as e:
        print(f"[{now}] Caption generation failed: {e}", file=sys.stderr)
        sys.exit(1)

    caption = _build_caption(variants[0])
    print(f"[{now}] Caption ready:\n{caption}\n")

    # Step 2: generate image
    print(f"[{now}] Generating image...")
    try:
        image_url = generate_image(
            topic=topic,
            keywords=keywords,
            tone="vibrant travel photography, golden hour lighting, cinematic",
        )
        print(f"[{now}] Image ready: {image_url}")
    except ImageGenError as e:
        print(f"[{now}] Image generation failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Step 3: post
    print(f"[{now}] Posting to Instagram...")
    try:
        post_id = post_instagram(caption=caption, image_url=image_url)
    except PostError as e:
        print(f"[{now}] Post failed: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[{now}] Done! Post ID: {post_id}")


if __name__ == "__main__":
    main()
