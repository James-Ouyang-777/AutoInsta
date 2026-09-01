#!/usr/bin/env python3
"""Create a brand post: scene image from approved character references + caption.

The image is generated via the image-edit endpoint with the approved
references/<character>.png files attached, so the characters stay on-model.
The caption is either omitted or a single short witty sentence — see
--caption below.

By default this PREVIEWS: it saves the image locally, uploads it to a public
URL, prints the caption, and leaves the post in pending_posts.json.
Publish it with --publish (or later via: python daily_post.py --retry-pending).

Usage:
    python create_post.py --scene "Jammy-O and Pineapple at a beach picnic"
    python create_post.py --scene "..." --characters jammy-o --publish
    python create_post.py --scene "..." --caption none
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from content_engine import brand
from content_engine.image_gen import ImageGenError, generate_scene_image, host_image_publicly
from content_engine.llm_adapter import LLMError
from content_engine.poster import PostError

from daily_post import _enqueue_pending_post, _post_with_retries, _remove_pending_post

_GENERATED_DIR = Path(__file__).parent / "generated"


def main() -> None:
    parser = argparse.ArgumentParser(description="Create (and optionally publish) a brand post.")
    parser.add_argument("--brand", default=None, help="Brand key under brands/ (default: $BRAND or jammy-o).")
    parser.add_argument("--scene", required=True, help="Scene description for the image.")
    parser.add_argument(
        "--characters",
        default="jammy-o,pineapple",
        help="Comma-separated character keys to feature (default: jammy-o,pineapple).",
    )
    parser.add_argument(
        "--topic",
        default=None,
        help="Caption topic override (default: derived from --scene).",
    )
    parser.add_argument(
        "--caption",
        choices=["witty", "none"],
        default="witty",
        help="'witty' (default): one short witty sentence. 'none': no caption at all.",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Publish to Instagram immediately. Without it, the post is generated and queued.",
    )
    args = parser.parse_args()

    now = datetime.datetime.now()
    style = brand.load_style(brand=args.brand)

    characters = [c.strip() for c in args.characters.split(",") if c.strip()]
    reference_paths = [brand.reference_image_path(key, brand=args.brand) for key in characters]

    # Step 1: scene image from approved references
    prompt = brand.scene_prompt(style, args.scene, characters)
    print(f"[{now}] Image prompt:\n{prompt}\n")
    print(f"[{now}] Generating scene image from references: {[p.name for p in reference_paths]}")
    try:
        image_bytes = generate_scene_image(prompt, reference_paths)
    except ImageGenError as e:
        print(f"[{now}] Image generation failed: {e}", file=sys.stderr)
        sys.exit(1)

    _GENERATED_DIR.mkdir(exist_ok=True)
    image_path = _GENERATED_DIR / f"post-{now.strftime('%Y%m%d-%H%M%S')}.png"
    image_path.write_bytes(image_bytes)
    print(f"[{now}] Image saved: {image_path}")

    # Step 2: caption — either none, or one short witty sentence
    topic = args.topic or args.scene
    if args.caption == "none":
        caption = ""
        print(f"[{now}] Caption: (none)")
    else:
        print(f"[{now}] Generating caption...")
        try:
            caption = brand.generate_short_caption(style, topic)
        except LLMError as e:
            print(f"[{now}] Caption generation failed: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"[{now}] Caption ready: {caption}\n")

    # Step 3: host publicly and queue
    print(f"[{now}] Uploading image for public hosting...")
    try:
        image_url = host_image_publicly(image_path)
    except ImageGenError as e:
        print(f"[{now}] Hosting failed: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"[{now}] Public URL: {image_url}")

    pending = _enqueue_pending_post(
        media_type="image",
        topic=topic,
        caption=caption,
        media_url=image_url,
    )
    print(f"[{now}] Queued pending post: {pending['id']}")

    if not args.publish:
        print(f"\n[{now}] Preview complete — nothing was published.")
        print(f"  Image:   {image_path}")
        print(f"  Publish: python daily_post.py --retry-pending")
        return

    print(f"[{now}] Publishing to Instagram...")
    try:
        post_id = _post_with_retries(pending, max_attempts=3)
    except PostError as e:
        print(f"[{now}] Post failed: {e}", file=sys.stderr)
        print(f"[{now}] Kept in queue. Retry with: python daily_post.py --retry-pending", file=sys.stderr)
        sys.exit(1)
    _remove_pending_post(pending["id"])
    print(f"[{now}] Done! Post ID: {post_id}")


if __name__ == "__main__":
    main()
