#!/usr/bin/env python3
"""Inspect and act on the media production log.

Examples:
    python media_cli.py list
    python media_cli.py list --status unposted
    python media_cli.py list --status posted --limit 50
    python media_cli.py show <id>
    python media_cli.py post <id>                 # post an unposted entry's video_url
    python media_cli.py post <id> --caption "..." # override caption
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()

from content_engine import brand, media_log
from content_engine.poster import PostError, post_instagram_video


def cmd_list(args: argparse.Namespace) -> None:
    rows = media_log.list_entries(status=args.status, brand=args.brand, limit=args.limit)
    if not rows:
        print("No matching media log entries.")
        print(f"Log file: {media_log.log_path()}")
        return
    for row in rows:
        print(media_log.format_entry(row))
        print()
    print(f"{len(rows)} shown · log: {media_log.log_path()}")


def cmd_show(args: argparse.Namespace) -> None:
    row = media_log.get_entry(args.id)
    if not row:
        sys.exit(f"No entry: {args.id}")
    print(media_log.format_entry(row))
    if row.get("caption"):
        print(f"  caption: {row['caption']}")
    if row.get("image_url"):
        print(f"  image: {row['image_url']}")
    if row.get("error"):
        print(f"  error: {row['error']}")
    if row.get("github_run_url"):
        print(f"  run: {row['github_run_url']}")


def cmd_post(args: argparse.Namespace) -> None:
    row = media_log.get_entry(args.id)
    if not row:
        sys.exit(f"No entry: {args.id}")
    video_url = row.get("video_url")
    if not video_url:
        sys.exit(f"Entry {args.id} has no video_url")
    if media_log.already_posted_video_url(video_url) and not args.force:
        sys.exit(
            f"This video_url is already marked posted. Pass --force to post again.\n"
            f"video: {video_url}"
        )

    caption = args.caption
    if caption is None:
        caption = row.get("caption") or ""
    if not caption and args.caption_mode != "none":
        style = brand.load_style(brand=row.get("brand"))
        scene = row.get("scene") or "kitten mini-story"
        try:
            caption = brand.generate_short_caption(style, scene)
        except Exception as exc:
            sys.exit(f"Caption generation failed: {exc}")

    print(f"Posting {args.id}")
    print(f"  video: {video_url}")
    print(f"  caption: {caption or '(none)'}")
    try:
        post_id = post_instagram_video(caption=caption or "", video_url=video_url)
    except PostError as exc:
        media_log.update_entry(
            args.id,
            status=media_log.STATUS_POST_FAILED,
            error=str(exc),
            caption=caption,
        )
        sys.exit(f"Post failed: {exc}")

    media_log.update_entry(
        args.id,
        status=media_log.STATUS_POSTED,
        instagram_post_id=post_id,
        caption=caption,
        error=None,
    )
    print(f"Done! Post ID: {post_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Media production log CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List recent media log entries")
    p_list.add_argument("--status", default=None, help="posted|preview|unposted|caption_failed|post_failed|...")
    p_list.add_argument("--brand", default=None)
    p_list.add_argument("--limit", type=int, default=20)
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="Show one entry by id")
    p_show.add_argument("id")
    p_show.set_defaults(func=cmd_show)

    p_post = sub.add_parser("post", help="Publish an existing log entry's video_url")
    p_post.add_argument("id")
    p_post.add_argument("--caption", default=None, help="Override caption text")
    p_post.add_argument(
        "--caption-mode",
        choices=["auto", "none"],
        default="auto",
        help="If entry has no caption, auto-generate (default) or leave empty",
    )
    p_post.add_argument("--force", action="store_true", help="Allow re-posting an already-posted video_url")
    p_post.set_defaults(func=cmd_post)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
