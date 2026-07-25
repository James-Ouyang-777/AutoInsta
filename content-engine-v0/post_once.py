#!/usr/bin/env python3
"""MVP: generate a caption + media and post once to Instagram.

Usage (auto-generate image via DALL-E — default):
    python post_once.py \
        --topic "morning coffee" \
        --keywords "coffee,ritual,morning"

Usage (auto-generate a 5-second video via fal.ai, posted as a Reel):
    python post_once.py \
        --topic "morning coffee" \
        --keywords "coffee,ritual,morning" \
        --type video

Usage (bring your own image):
    python post_once.py \
        --topic "morning coffee" \
        --keywords "coffee,ritual,morning" \
        --image-url "https://example.com/coffee.jpg"

Media URLs must be publicly accessible (Instagram fetches them server-side).
Set LLM_API_KEY, INSTAGRAM_USER_ID, and INSTAGRAM_ACCESS_TOKEN in .env first.
Video mode additionally requires FAL_KEY.
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()

from content_engine.generator import GenerationError, generate
from content_engine.image_gen import ImageGenError, generate_image
from content_engine.poster import PostError, post_instagram, post_instagram_video
from content_engine.video_gen import VideoGenError, generate_video


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
    parser = argparse.ArgumentParser(description="Generate caption + media and post to Instagram.")
    parser.add_argument("--topic", required=True, help="What the post is about")
    parser.add_argument("--keywords", required=True, help="Comma-separated keywords")
    parser.add_argument(
        "--type",
        choices=["image", "video"],
        default="image",
        help="Media type: 'image' (DALL-E photo post) or 'video' (fal.ai 5s Reel). Default: image.",
    )
    parser.add_argument(
        "--image-url",
        default=None,
        help="Publicly accessible image URL. Omit to auto-generate. (--type image only)",
    )
    parser.add_argument("--voice", default="friendly", help="Brand voice (default: friendly)")
    parser.add_argument("--audience", default="general", help="Target audience")
    parser.add_argument("--cta-style", default="soft", help="CTA style (soft/hard/question)")
    args = parser.parse_args()

    if args.type == "video" and args.image_url:
        parser.error("--image-url only applies to --type image")

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    brand = {
        "voice": args.voice,
        "audience": args.audience,
        "reading_level": "casual",
        "prohibited": [],
    }

    # Step 1: generate caption
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
        print(f"Caption generation failed: {e}", file=sys.stderr)
        sys.exit(1)

    caption = _build_caption(variants[0])
    print(f"\n--- Caption ---\n{caption}\n---------------\n")

    # Step 2: get or generate media, then post
    if args.type == "video":
        print("Generating 5-second video via fal.ai (this can take a few minutes)...")
        try:
            video_url = generate_video(topic=args.topic, keywords=keywords)
            print(f"Video URL: {video_url}\n")
        except VideoGenError as e:
            print(f"Video generation failed: {e}", file=sys.stderr)
            sys.exit(1)

        print("Posting Reel to Instagram (processing can take a minute)...")
        try:
            post_id = post_instagram_video(caption=caption, video_url=video_url)
        except PostError as e:
            print(f"Post failed: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        image_url = args.image_url
        if image_url:
            print(f"Using provided image: {image_url}")
        else:
            print("Generating image via DALL-E...")
            try:
                image_url = generate_image(topic=args.topic, keywords=keywords)
                print(f"Image URL: {image_url}\n")
            except ImageGenError as e:
                print(f"Image generation failed: {e}", file=sys.stderr)
                sys.exit(1)

        print("Posting to Instagram...")
        try:
            post_id = post_instagram(caption=caption, image_url=image_url)
        except PostError as e:
            print(f"Post failed: {e}", file=sys.stderr)
            sys.exit(1)

    print(f"Done! Post ID: {post_id}")


if __name__ == "__main__":
    main()
