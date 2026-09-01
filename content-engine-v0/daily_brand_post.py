#!/usr/bin/env python3
"""Daily brand post — picks today's scene from the rotation, generates a still,
animates it into a Reel, and publishes it to Instagram.

Stateless by design: today's scene is chosen deterministically from
brands/<brand>/scenes.yaml via date.toordinal() % len(scenes), so running
this once a day from an external scheduler (cron, GitHub Actions) needs no
"last posted" bookkeeping and self-heals if a day is skipped. There is no
pending-queue integration here — on failure this simply exits non-zero so
the scheduler can alert; the next day's run picks fresh content.

Usage:
    python daily_brand_post.py --no-publish        # preview, don't post
    python daily_brand_post.py                      # generate and publish
    python daily_brand_post.py --brand jammy-o --date 2026-09-05   # preview a future slot
    python daily_brand_post.py --scene "Jammy-O surfing at sunset" # one-off override
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv

load_dotenv()

from content_engine import brand
from content_engine.image_gen import ImageGenError, generate_scene_image, host_image_publicly
from content_engine.llm_adapter import LLMError
from content_engine.poster import PostError
from content_engine.video_gen import VideoGenError, generate_video_from_image

from daily_post import _post_with_retries

_GENERATED_DIR = Path(__file__).parent / "generated"

_DEFAULT_MOTION = (
    "Bring this exact scene to life with subtle, natural motion. Keep every "
    "character, color, and background element exactly as shown — do not add "
    "new characters, objects, or text. Camera slowly pushes in."
)

_LOCAL_TZ = ZoneInfo("America/New_York")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and publish today's brand post as a Reel.")
    parser.add_argument("--brand", default=None, help="Brand key under brands/ (default: $BRAND or jammy-o).")
    parser.add_argument(
        "--date",
        default=None,
        help="Override the date used to pick today's scene (YYYY-MM-DD). Default: today in America/New_York.",
    )
    parser.add_argument("--scene", default=None, help="Override the scene text instead of using the rotation.")
    parser.add_argument("--duration", default="5", help="Video length in seconds, 3-15 (default: 5).")
    parser.add_argument(
        "--caption",
        choices=["witty", "none"],
        default="witty",
        help="'witty' (default): one short witty sentence. 'none': no caption at all.",
    )
    parser.add_argument(
        "--no-publish",
        action="store_true",
        help="Generate the still and video and print the result, but don't post to Instagram.",
    )
    args = parser.parse_args()

    now = datetime.datetime.now()
    if args.date:
        today = datetime.date.fromisoformat(args.date)
    else:
        today = datetime.datetime.now(_LOCAL_TZ).date()

    style = brand.load_style(brand=args.brand)

    if args.scene:
        scene_entry = {"scene": args.scene}
    else:
        scenes = brand.load_scenes(brand=args.brand)
        idx = today.toordinal() % len(scenes)
        scene_entry = scenes[idx]
        print(f"[{now}] Scene rotation index {idx}/{len(scenes)} for {today.isoformat()}")

    scene_text = scene_entry["scene"]
    characters = scene_entry.get("characters") or brand.character_keys(style)
    motion = scene_entry.get("motion") or _DEFAULT_MOTION
    print(f"[{now}] Scene: {scene_text}")
    print(f"[{now}] Characters: {characters}")

    reference_paths = [brand.reference_image_path(key, brand=args.brand) for key in characters]

    # Step 1: still image from approved references
    prompt = brand.scene_prompt(style, scene_text, characters)
    print(f"[{now}] Generating scene image from references: {[p.name for p in reference_paths]}")
    try:
        image_bytes = generate_scene_image(prompt, reference_paths)
    except ImageGenError as e:
        print(f"[{now}] Image generation failed: {e}", file=sys.stderr)
        sys.exit(1)

    _GENERATED_DIR.mkdir(exist_ok=True)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    image_path = _GENERATED_DIR / f"post-{stamp}.png"
    image_path.write_bytes(image_bytes)
    print(f"[{now}] Image saved: {image_path}")

    # Step 2: host the still publicly so fal can animate it
    print(f"[{now}] Uploading still for public hosting...")
    try:
        image_url = host_image_publicly(image_path)
    except ImageGenError as e:
        print(f"[{now}] Hosting failed: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"[{now}] Public still URL: {image_url}")

    # Step 3: animate into a short video
    print(f"[{now}] Motion prompt:\n{motion}\n")
    print(f"[{now}] Generating video (duration={args.duration}s)...")
    try:
        video_url = generate_video_from_image(image_url, motion, duration=args.duration)
    except VideoGenError as e:
        print(f"[{now}] Video generation failed: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"[{now}] Video ready: {video_url}")

    video_path = _GENERATED_DIR / f"video-{stamp}.mp4"
    with httpx.Client(timeout=120) as client:
        r = client.get(video_url)
        r.raise_for_status()
        video_path.write_bytes(r.content)
    print(f"[{now}] Video saved locally: {video_path}")

    # Step 4: caption
    if args.caption == "none":
        caption = ""
        print(f"[{now}] Caption: (none)")
    else:
        print(f"[{now}] Generating caption...")
        try:
            caption = brand.generate_short_caption(style, scene_text)
        except LLMError as e:
            print(f"[{now}] Caption generation failed: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"[{now}] Caption ready: {caption}\n")

    if args.no_publish:
        print(f"\n[{now}] Preview complete — nothing was published.")
        print(f"  Image: {image_path}")
        print(f"  Video: {video_path}")
        print(f"  CDN URL: {video_url}")
        print(f"  Caption: {caption or '(none)'}")
        return

    print(f"[{now}] Publishing Reel to Instagram...")
    entry = {"media_type": "video", "caption": caption, "media_url": video_url}
    try:
        post_id = _post_with_retries(entry, max_attempts=3)
    except PostError as e:
        print(f"[{now}] Post failed: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"[{now}] Done! Post ID: {post_id}")


if __name__ == "__main__":
    main()
