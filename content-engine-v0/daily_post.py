#!/usr/bin/env python3
"""Daily travel post — picks today's topic from topics.yaml and posts to Instagram.

Run directly:
    python daily_post.py            # photo post (DALL-E image)
    python daily_post.py --type video   # 5-second Reel (fal.ai video)

Or via cron (see README for setup instructions).
Logs are written to stdout/stderr; redirect to a file in your cron entry.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

from content_engine.generator import GenerationError, generate
from content_engine.image_gen import ImageGenError, generate_image
from content_engine.poster import PostError, post_instagram, post_instagram_video
from content_engine.video_gen import VideoGenError, generate_video


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
    parser = argparse.ArgumentParser(description="Post today's travel content to Instagram.")
    parser.add_argument(
        "--type",
        choices=["image", "video"],
        default="image",
        help="Media type: 'image' (DALL-E photo) or 'video' (fal.ai 5s Reel). Default: image.",
    )
    args = parser.parse_args()

    now = datetime.datetime.now()
    print(f"[{now}] Starting daily post (type: {args.type})")

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

    # Step 2: generate media and post
    if args.type == "video":
        print(f"[{now}] Generating video via fal.ai...")
        try:
            video_url = generate_video(
                topic=topic,
                keywords=keywords,
                tone="vibrant travel cinematography, golden hour lighting, sweeping drone shots",
            )
            print(f"[{now}] Video ready: {video_url}")
        except VideoGenError as e:
            print(f"[{now}] Video generation failed: {e}", file=sys.stderr)
            sys.exit(1)

        print(f"[{now}] Posting Reel to Instagram...")
        try:
            post_id = post_instagram_video(caption=caption, video_url=video_url)
        except PostError as e:
            print(f"[{now}] Post failed: {e}", file=sys.stderr)
            sys.exit(1)
    else:
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

        print(f"[{now}] Posting to Instagram...")
        try:
            post_id = post_instagram(caption=caption, image_url=image_url)
        except PostError as e:
            print(f"[{now}] Post failed: {e}", file=sys.stderr)
            sys.exit(1)

    print(f"[{now}] Done! Post ID: {post_id}")


if __name__ == "__main__":
    main()
