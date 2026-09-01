#!/usr/bin/env python3
"""Daily travel post — picks today's topic from topics.yaml and posts to Instagram.

Run directly:
    python daily_post.py            # photo post (DALL-E image)
    python daily_post.py --type video   # 5-second Reel (fal.ai video)
    python daily_post.py --type video --dry-run-video  # generate only, don't publish
    python daily_post.py --type video --video-model fal-ai/kling-video/v3/pro/text-to-video

Or via cron (see README for setup instructions).
Logs are written to stdout/stderr; redirect to a file in your cron entry.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
import uuid
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

from content_engine.generator import GenerationError, generate
from content_engine.image_gen import ImageGenError, generate_image
from content_engine.poster import PostError, post_instagram, post_instagram_video
from content_engine.video_gen import VideoGenError, generate_video

_PENDING_QUEUE_PATH = Path(__file__).parent / "pending_posts.json"


def _build_caption(variant: dict) -> str:
    parts = [variant.get("hook", ""), variant.get("body", "")]
    cta = variant.get("cta", "")
    if cta:
        parts.append(cta)
    hashtags = " ".join(variant.get("hashtags", []))
    if hashtags:
        parts.append(hashtags)
    return "\n\n".join(p for p in parts if p)


def _load_pending_queue() -> list[dict]:
    if not _PENDING_QUEUE_PATH.exists():
        return []
    try:
        data = json.loads(_PENDING_QUEUE_PATH.read_text())
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Pending queue is invalid JSON: {_PENDING_QUEUE_PATH}") from exc
    if not isinstance(data, list):
        raise RuntimeError(f"Pending queue must be a list: {_PENDING_QUEUE_PATH}")
    return [item for item in data if isinstance(item, dict)]


def _save_pending_queue(queue: list[dict]) -> None:
    _PENDING_QUEUE_PATH.write_text(json.dumps(queue, indent=2))


def _enqueue_pending_post(media_type: str, topic: str, caption: str, media_url: str) -> dict:
    entry = {
        "id": str(uuid.uuid4()),
        "created_at": datetime.datetime.now().isoformat(),
        "media_type": media_type,
        "topic": topic,
        "caption": caption,
        "media_url": media_url,
        "attempts": 0,
        "last_error": None,
    }
    queue = _load_pending_queue()
    queue.append(entry)
    _save_pending_queue(queue)
    return entry


def _remove_pending_post(entry_id: str) -> None:
    queue = _load_pending_queue()
    queue = [item for item in queue if item.get("id") != entry_id]
    _save_pending_queue(queue)


def _record_pending_failure(entry_id: str, error_message: str) -> None:
    queue = _load_pending_queue()
    for item in queue:
        if item.get("id") == entry_id:
            item["attempts"] = int(item.get("attempts", 0)) + 1
            item["last_error"] = error_message
            item["last_attempted_at"] = datetime.datetime.now().isoformat()
            break
    _save_pending_queue(queue)


def _is_non_retryable_post_error(message: str) -> bool:
    lowered = message.lower()
    return (
        "session has expired" in lowered
        or "error validating access token" in lowered
        or '"code":190' in lowered
    )


def _post_entry(entry: dict) -> str:
    media_type = entry.get("media_type")
    caption = entry.get("caption", "")
    media_url = entry.get("media_url", "")
    if media_type == "video":
        return post_instagram_video(caption=caption, video_url=media_url)
    if media_type == "image":
        return post_instagram(caption=caption, image_url=media_url)
    raise PostError(f"Unsupported pending media_type: {media_type}")


def _post_with_retries(entry: dict, max_attempts: int) -> str:
    last_exc: PostError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return _post_entry(entry)
        except PostError as exc:
            last_exc = exc
            error_message = str(exc)
            if _is_non_retryable_post_error(error_message):
                raise
            if attempt < max_attempts:
                sleep_seconds = min(30, attempt * 5)
                print(
                    f"[{datetime.datetime.now()}] Post attempt {attempt}/{max_attempts} failed, "
                    f"retrying in {sleep_seconds}s..."
                )
                time.sleep(sleep_seconds)
    raise PostError(str(last_exc))


def _retry_pending_posts(max_attempts: int, retry_all: bool) -> tuple[int, int]:
    queue = _load_pending_queue()
    if not queue:
        print(f"[{datetime.datetime.now()}] No pending posts in {_PENDING_QUEUE_PATH}.")
        return 0, 0

    targets = queue if retry_all else queue[:1]
    successes = 0
    failures = 0

    for entry in targets:
        entry_id = entry.get("id", "<unknown>")
        media_type = entry.get("media_type", "<unknown>")
        print(f"[{datetime.datetime.now()}] Retrying pending {media_type} post: {entry_id}")
        try:
            post_id = _post_with_retries(entry, max_attempts=max_attempts)
        except PostError as exc:
            failures += 1
            _record_pending_failure(entry_id, str(exc))
            print(f"[{datetime.datetime.now()}] Pending post failed: {exc}", file=sys.stderr)
        else:
            successes += 1
            _remove_pending_post(entry_id)
            print(f"[{datetime.datetime.now()}] Pending post published. Post ID: {post_id}")

    return successes, failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Post today's travel content to Instagram.")
    parser.add_argument(
        "--type",
        choices=["image", "video"],
        default="image",
        help="Media type: 'image' (DALL-E photo) or 'video' (fal.ai 5s Reel). Default: image.",
    )
    parser.add_argument(
        "--dry-run-video",
        action="store_true",
        help=(
            "When used with --type video, generate the Reel URL via fal.ai and exit "
            "without posting to Instagram."
        ),
    )
    parser.add_argument(
        "--video-model",
        default=None,
        help=(
            "fal.ai model route override (video only), e.g. "
            "fal-ai/kling-video/v3/pro/text-to-video. "
            "If omitted, the built-in default is used."
        ),
    )
    parser.add_argument(
        "--retry-pending",
        action="store_true",
        help="Retry posting from the saved pending queue without generating new media.",
    )
    parser.add_argument(
        "--retry-all-pending",
        action="store_true",
        help="When used with --retry-pending, attempt all queued posts (oldest first).",
    )
    parser.add_argument(
        "--max-post-attempts",
        type=int,
        default=3,
        help="Maximum posting attempts per item before leaving it in the pending queue.",
    )
    args = parser.parse_args()
    if args.dry_run_video and args.type != "video":
        parser.error("--dry-run-video can only be used with --type video")
    if args.video_model and args.type != "video":
        parser.error("--video-model can only be used with --type video")
    if args.retry_all_pending and not args.retry_pending:
        parser.error("--retry-all-pending requires --retry-pending")
    if args.max_post_attempts < 1:
        parser.error("--max-post-attempts must be >= 1")
    if args.retry_pending and args.dry_run_video:
        parser.error("--retry-pending cannot be combined with --dry-run-video")

    if args.retry_pending:
        successes, failures = _retry_pending_posts(
            max_attempts=args.max_post_attempts, retry_all=args.retry_all_pending
        )
        if failures:
            print(
                f"[{datetime.datetime.now()}] Retry complete: {successes} published, {failures} failed.",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"[{datetime.datetime.now()}] Retry complete: {successes} published, 0 failed.")
        return

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
                model=args.video_model,
            )
            print(f"[{now}] Video ready: {video_url}")
        except VideoGenError as e:
            print(f"[{now}] Video generation failed: {e}", file=sys.stderr)
            sys.exit(1)

        pending = _enqueue_pending_post(
            media_type="video",
            topic=topic,
            caption=caption,
            media_url=video_url,
        )
        print(f"[{now}] Saved pending post: {pending['id']}")

        if args.dry_run_video:
            print(f"[{now}] Dry run complete. Skipping Instagram publish.")
            return

        print(f"[{now}] Posting Reel to Instagram...")
        try:
            post_id = _post_with_retries(pending, max_attempts=args.max_post_attempts)
        except PostError as e:
            _record_pending_failure(pending["id"], str(e))
            print(f"[{now}] Post failed: {e}", file=sys.stderr)
            print(
                f"[{now}] Pending post kept. Retry with: python daily_post.py --retry-pending",
                file=sys.stderr,
            )
            sys.exit(1)
        _remove_pending_post(pending["id"])
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

        pending = _enqueue_pending_post(
            media_type="image",
            topic=topic,
            caption=caption,
            media_url=image_url,
        )
        print(f"[{now}] Saved pending post: {pending['id']}")

        print(f"[{now}] Posting to Instagram...")
        try:
            post_id = _post_with_retries(pending, max_attempts=args.max_post_attempts)
        except PostError as e:
            _record_pending_failure(pending["id"], str(e))
            print(f"[{now}] Post failed: {e}", file=sys.stderr)
            print(
                f"[{now}] Pending post kept. Retry with: python daily_post.py --retry-pending",
                file=sys.stderr,
            )
            sys.exit(1)
        _remove_pending_post(pending["id"])

    print(f"[{now}] Done! Post ID: {post_id}")


if __name__ == "__main__":
    main()
