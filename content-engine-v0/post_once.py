#!/usr/bin/env python3
"""MVP: generate a caption and post a single photo to Instagram.

Usage:
    python post_once.py \
        --topic "morning coffee" \
        --keywords "coffee,ritual,morning" \
        --image-url "https://example.com/coffee.jpg"

The image URL must be publicly accessible (Instagram fetches it server-side).
Set INSTAGRAM_USER_ID and INSTAGRAM_ACCESS_TOKEN in your .env file first.
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()

from content_engine.generator import GenerationError, generate
from content_engine.poster import PostError, post_instagram


def _build_caption(variant: dict) -> str:
    """Assemble hook + body + cta + hashtags into a single caption string."""
    parts = [variant.get("hook", ""), variant.get("body", "")]
    cta = variant.get("cta", "")
    if cta:
        parts.append(cta)
    hashtags = " ".join(variant.get("hashtags", []))
    if hashtags:
        parts.append(hashtags)
    return "\n\n".join(p for p in parts if p)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate caption and post to Instagram.")
    parser.add_argument("--topic", required=True, help="What the post is about")
    parser.add_argument("--keywords", required=True, help="Comma-separated keywords")
    parser.add_argument("--image-url", required=True, help="Publicly accessible image URL")
    parser.add_argument("--voice", default="friendly", help="Brand voice (default: friendly)")
    parser.add_argument("--audience", default="general", help="Target audience")
    parser.add_argument("--cta-style", default="soft", help="CTA style (soft/hard/question)")
    args = parser.parse_args()

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    brand = {
        "voice": args.voice,
        "audience": args.audience,
        "reading_level": "casual",
        "prohibited": [],
    }

    print(f"Generating caption for: {args.topic!r}")
    try:
        variants = generate(
            platform="instagram",
            topic=args.topic,
            keywords=keywords,
            brand=brand,
            cta_style=args.cta_style,
            n_variants=1,
        )
    except GenerationError as e:
        print(f"Generation failed: {e}", file=sys.stderr)
        sys.exit(1)

    caption = _build_caption(variants[0])
    print(f"\n--- Caption ---\n{caption}\n---------------\n")

    print("Posting to Instagram...")
    try:
        post_id = post_instagram(caption=caption, image_url=args.image_url)
    except PostError as e:
        print(f"Post failed: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Done! Post ID: {post_id}")


if __name__ == "__main__":
    main()
