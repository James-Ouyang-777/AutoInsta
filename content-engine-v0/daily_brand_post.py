#!/usr/bin/env python3
"""Daily brand post — picks today's scene from the rotation, generates a still,
animates it into a Reel, and publishes it to Instagram.

Stateless scene pick: today's scene is chosen deterministically from
brands/<brand>/scenes.yaml via date.toordinal() % len(scenes).

Every generated video is recorded in media_log.jsonl with status
(preview / posted / caption_failed / post_failed) and CDN URL so nothing
is lost when a later step fails.

Usage:
    python daily_brand_post.py --no-publish        # preview, don't post
    python daily_brand_post.py                      # generate and publish
    python daily_brand_post.py --brand jammy-o --date 2026-09-05
    python media_cli.py list --status unposted      # recover unfinished videos
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

from content_engine import brand, media_log
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
    parser.add_argument("--brand", default=None, help="Brand key under brands/ (default: $BRAND or kittenz).")
    parser.add_argument(
        "--date",
        default=None,
        help="Override the date used to pick today's scene (YYYY-MM-DD). Default: today in America/New_York.",
    )
    parser.add_argument("--scene", default=None, help="Override the scene text instead of using the rotation.")
    parser.add_argument("--duration", default="10", help="Video length in seconds, 3-15 (default: 10).")
    parser.add_argument(
        "--caption",
        choices=["witty", "none"],
        default="witty",
        help="'witty' (default): AI-reaction caption from brand voice. 'none': no caption.",
    )
    parser.add_argument(
        "--no-audio",
        action="store_true",
        help="Disable native audio generation (silent Reel). Audio is on by default.",
    )
    parser.add_argument(
        "--no-publish",
        action="store_true",
        help="Generate the still and video and print the result, but don't post to Instagram.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Post even if this brand+scene was already marked posted today.",
    )
    args = parser.parse_args()

    now = datetime.datetime.now()
    if args.date:
        today = datetime.date.fromisoformat(args.date)
    else:
        today = datetime.datetime.now(_LOCAL_TZ).date()

    brand_key = args.brand or brand._default_brand()
    style = brand.load_style(brand=args.brand)

    if args.scene:
        scene_entry = {"scene": args.scene}
        scene_idx = None
    else:
        scenes = brand.load_scenes(brand=args.brand)
        scene_idx = today.toordinal() % len(scenes)
        scene_entry = scenes[scene_idx]
        print(f"[{now}] Scene rotation index {scene_idx}/{len(scenes)} for {today.isoformat()}")

    scene_text = scene_entry["scene"]
    characters = scene_entry.get("characters") or brand.character_keys(style)
    motion = scene_entry.get("motion") or _DEFAULT_MOTION
    print(f"[{now}] Brand: {brand_key}")
    print(f"[{now}] Scene: {scene_text}")
    print(f"[{now}] Characters: {characters}")

    if (
        not args.no_publish
        and not args.force
        and media_log.already_posted_scene_on_date(scene_text, today.isoformat(), brand=brand_key)
    ):
        print(
            f"[{now}] Skipping publish: this brand+scene is already marked posted today "
            f"({today.isoformat()}). Use --force to override, or python media_cli.py list.",
            file=sys.stderr,
        )
        sys.exit(0)

    reference_paths = [brand.reference_image_path(key, brand=args.brand) for key in characters]

    # Step 1: still image from approved references
    prompt = brand.scene_prompt(style, scene_text, characters)
    print(f"[{now}] Generating scene image from references: {[p.name for p in reference_paths]}")
    try:
        image_bytes = generate_scene_image(prompt, reference_paths)
    except ImageGenError as e:
        media_log.append_entry(
            {
                "brand": brand_key,
                "scene": scene_text,
                "scene_index": scene_idx,
                "date": today.isoformat(),
                "characters": list(characters),
                "duration": args.duration,
                "audio": not args.no_audio,
                "video_url": None,
                "caption": None,
                "status": media_log.STATUS_POST_FAILED,
                "instagram_post_id": None,
                "error": f"image_generation_failed: {e}",
                "source": "daily_brand_post",
            }
        )
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
    # Don't spam huge data-URIs into logs
    image_url_log = "(data-uri)" if image_url.startswith("data:") else image_url
    print(f"[{now}] Public still URL: {image_url_log}")

    # Step 3: animate into a short video
    with_audio = not args.no_audio
    motion_prompt = brand.motion_prompt_with_sound(style, motion, with_audio=with_audio)
    print(f"[{now}] Motion prompt:\n{motion_prompt}\n")
    print(f"[{now}] Generating video (duration={args.duration}s, audio={with_audio})...")
    try:
        video_url = generate_video_from_image(
            image_url,
            motion_prompt,
            duration=args.duration,
            generate_audio=with_audio,
            negative_prompt=brand.sound_negative_prompt(style) if with_audio else None,
        )
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

    # Record immediately so a later caption/post failure never loses the CDN link.
    log_entry = media_log.append_entry(
        {
            "brand": brand_key,
            "scene": scene_text,
            "scene_index": scene_idx,
            "date": today.isoformat(),
            "characters": list(characters),
            "duration": args.duration,
            "audio": with_audio,
            "image_path": str(image_path),
            "image_url": None if image_url.startswith("data:") else image_url,
            "video_path": str(video_path),
            "video_url": video_url,
            "caption": None,
            "status": media_log.STATUS_GENERATED,
            "instagram_post_id": None,
            "error": None,
            "source": "daily_brand_post",
        }
    )
    print(f"[{now}] Media log id: {log_entry['id']}")
    print(f"[{now}] MEDIA_LOG video_url={video_url}")

    # Step 4: caption
    caption = ""
    if args.caption == "none":
        print(f"[{now}] Caption: (none)")
    else:
        print(f"[{now}] Generating caption...")
        try:
            caption = brand.generate_short_caption(style, scene_text)
        except LLMError as e:
            media_log.update_entry(
                log_entry["id"],
                status=media_log.STATUS_CAPTION_FAILED,
                error=str(e),
            )
            print(f"[{now}] Caption generation failed: {e}", file=sys.stderr)
            print(
                f"[{now}] Video is saved. Retry with: "
                f"python media_cli.py post {log_entry['id']}",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"[{now}] Caption ready: {caption}\n")
        media_log.update_entry(log_entry["id"], caption=caption)

    if args.no_publish:
        media_log.update_entry(log_entry["id"], status=media_log.STATUS_PREVIEW, caption=caption)
        print(f"\n[{now}] Preview complete — nothing was published.")
        print(f"  Image: {image_path}")
        print(f"  Video: {video_path}")
        print(f"  CDN URL: {video_url}")
        print(f"  Caption: {caption or '(none)'}")
        print(f"  Log id: {log_entry['id']}")
        return

    print(f"[{now}] Publishing Reel to Instagram...")
    entry = {"media_type": "video", "caption": caption, "media_url": video_url}
    try:
        post_id = _post_with_retries(entry, max_attempts=3)
    except PostError as e:
        media_log.update_entry(
            log_entry["id"],
            status=media_log.STATUS_POST_FAILED,
            caption=caption,
            error=str(e),
        )
        print(f"[{now}] Post failed: {e}", file=sys.stderr)
        print(
            f"[{now}] Video is saved. Retry with: "
            f"python media_cli.py post {log_entry['id']}",
            file=sys.stderr,
        )
        sys.exit(1)

    media_log.update_entry(
        log_entry["id"],
        status=media_log.STATUS_POSTED,
        caption=caption,
        instagram_post_id=post_id,
        error=None,
    )
    print(f"[{now}] Done! Post ID: {post_id}")
    print(f"[{now}] MEDIA_LOG posted id={log_entry['id']} video_url={video_url}")


if __name__ == "__main__":
    main()
