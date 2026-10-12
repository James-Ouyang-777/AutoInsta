"""Append-only media production log.

Every generated still/video should land here with a clear status so we can
always answer: what did we make, what got posted, and what's the CDN link?

Log file: content-engine-v0/media_log.jsonl (one JSON object per line).
"""

from __future__ import annotations

import datetime
import json
import os
import uuid
from pathlib import Path
from typing import Any, Iterable

_LOG_PATH = Path(__file__).resolve().parents[2] / "media_log.jsonl"

# Status values
STATUS_GENERATED = "generated"  # video ready, not intended for IG yet / in progress
STATUS_PREVIEW = "preview"  # --no-publish completed
STATUS_POSTED = "posted"
STATUS_CAPTION_FAILED = "caption_failed"
STATUS_POST_FAILED = "post_failed"
STATUS_UNPOSTED = "unposted"  # ready to post (has video_url), not on IG yet


def log_path() -> Path:
    return _LOG_PATH


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def append_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Append one entry and return it (with id/created_at filled if missing)."""
    record = dict(entry)
    record.setdefault("id", str(uuid.uuid4()))
    record.setdefault("created_at", _now())
    record.setdefault("github_run_id", os.getenv("GITHUB_RUN_ID"))
    record.setdefault("github_run_url", (
        f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
        if os.getenv("GITHUB_REPOSITORY") and os.getenv("GITHUB_RUN_ID")
        else None
    ))
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def update_entry(entry_id: str, **fields: Any) -> dict[str, Any]:
    """Rewrite the log replacing the matching id. Returns updated record."""
    rows = list(iter_entries())
    updated: dict[str, Any] | None = None
    out: list[dict[str, Any]] = []
    for row in rows:
        if row.get("id") == entry_id:
            row = {**row, **fields, "updated_at": _now()}
            updated = row
        out.append(row)
    if updated is None:
        raise KeyError(f"media log entry not found: {entry_id}")
    with open(_LOG_PATH, "w", encoding="utf-8") as f:
        for row in out:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return updated


def iter_entries() -> Iterable[dict[str, Any]]:
    if not _LOG_PATH.exists():
        return []
    rows: list[dict[str, Any]] = []
    with open(_LOG_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def get_entry(entry_id: str) -> dict[str, Any] | None:
    for row in iter_entries():
        if row.get("id") == entry_id:
            return row
    return None


def find_by_video_url(video_url: str) -> dict[str, Any] | None:
    matches = [r for r in iter_entries() if r.get("video_url") == video_url]
    return matches[-1] if matches else None


def already_posted_video_url(video_url: str) -> bool:
    return any(
        r.get("video_url") == video_url and r.get("status") == STATUS_POSTED
        for r in iter_entries()
    )


def already_posted_scene_on_date(scene: str, day: str, brand: str | None = None) -> bool:
    """True if we already marked this brand+scene as posted on YYYY-MM-DD."""
    for r in iter_entries():
        if r.get("status") != STATUS_POSTED:
            continue
        if brand and r.get("brand") != brand:
            continue
        created = (r.get("created_at") or "")[:10]
        if created == day and (r.get("scene") or "").strip() == scene.strip():
            return True
    return False


def list_entries(
    *,
    status: str | None = None,
    brand: str | None = None,
    limit: int | None = 20,
) -> list[dict[str, Any]]:
    rows = list(iter_entries())
    if brand:
        rows = [r for r in rows if r.get("brand") == brand]
    if status == "unposted":
        rows = [
            r
            for r in rows
            if r.get("video_url")
            and r.get("status") in {STATUS_GENERATED, STATUS_PREVIEW, STATUS_CAPTION_FAILED, STATUS_POST_FAILED, STATUS_UNPOSTED}
        ]
    elif status:
        rows = [r for r in rows if r.get("status") == status]
    rows.reverse()  # newest first
    if limit is not None:
        rows = rows[:limit]
    return rows


def format_entry(row: dict[str, Any]) -> str:
    status = row.get("status", "?")
    created = row.get("created_at", "?")
    brand = row.get("brand", "?")
    video = row.get("video_url") or "(no video url)"
    post_id = row.get("instagram_post_id") or "-"
    scene = " ".join((row.get("scene") or "").split())
    if len(scene) > 90:
        scene = scene[:87] + "..."
    return (
        f"{created}  [{status}]  {brand}  id={row.get('id')}\n"
        f"  scene: {scene}\n"
        f"  video: {video}\n"
        f"  ig_post: {post_id}"
    )
