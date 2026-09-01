"""Minimal Instagram Graph API poster.

Requires:
  INSTAGRAM_USER_ID     — numeric Instagram user ID
  INSTAGRAM_ACCESS_TOKEN — long-lived access token with instagram_content_publish scope

Posting flow (photo):
  1. POST /{user_id}/media  → creates a media container, returns creation_id
  2. POST /{user_id}/media_publish  → publishes the container, returns post_id

Posting flow (video/Reel):
  Same as photo, but Instagram processes the video asynchronously — the
  container must reach status FINISHED before media_publish will succeed,
  so we poll the container's status_code between steps 1 and 2.
"""

from __future__ import annotations

import os
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

_GRAPH_BASE = "https://graph.instagram.com/v21.0"
_POLL_INTERVAL_SECONDS = 5
_MAX_PROCESSING_SECONDS = 300


class PostError(RuntimeError):
    """Raised when publishing to Instagram fails."""


def _credentials() -> tuple[str, str]:
    user_id = os.getenv("INSTAGRAM_USER_ID")
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    if not user_id or not token:
        raise PostError(
            "INSTAGRAM_USER_ID and INSTAGRAM_ACCESS_TOKEN must be set in the environment."
        )
    return user_id, token


def _create_container(client: httpx.Client, user_id: str, params: dict) -> str:
    r = client.post(f"/{user_id}/media", params=params)
    if not r.is_success:
        raise PostError(f"Media container creation failed ({r.status_code}): {r.text}")
    creation_id = r.json().get("id")
    if not creation_id:
        raise PostError(f"No container ID in response: {r.text}")
    return creation_id


def _wait_for_processing(client: httpx.Client, creation_id: str, token: str) -> None:
    """Poll a video container until Instagram finishes processing it."""
    waited = 0
    while waited < _MAX_PROCESSING_SECONDS:
        r = client.get(f"/{creation_id}", params={"fields": "status_code", "access_token": token})
        if not r.is_success:
            raise PostError(f"Container status check failed ({r.status_code}): {r.text}")
        status = r.json().get("status_code")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise PostError(f"Instagram failed to process the video: {r.text}")
        time.sleep(_POLL_INTERVAL_SECONDS)
        waited += _POLL_INTERVAL_SECONDS
    raise PostError(f"Video processing timed out after {_MAX_PROCESSING_SECONDS}s.")


def _publish(client: httpx.Client, user_id: str, creation_id: str, token: str) -> str:
    r = client.post(
        f"/{user_id}/media_publish",
        params={"creation_id": creation_id, "access_token": token},
    )
    if not r.is_success:
        raise PostError(f"Publish failed ({r.status_code}): {r.text}")
    post_id = r.json().get("id")
    if not post_id:
        raise PostError(f"No post ID in publish response: {r.text}")
    return post_id


def post_instagram(caption: str, image_url: str) -> str:
    """Upload a photo and publish it to Instagram. Returns the published post ID.

    Args:
        caption:   Full caption string (hook + body + hashtags).
        image_url: Publicly reachable URL of the image to post.
    """
    user_id, token = _credentials()
    with httpx.Client(base_url=_GRAPH_BASE, timeout=60) as client:
        creation_id = _create_container(
            client,
            user_id,
            {"image_url": image_url, "caption": caption, "access_token": token},
        )
        return _publish(client, user_id, creation_id, token)


def post_instagram_video(caption: str, video_url: str) -> str:
    """Upload a video as a Reel and publish it. Returns the published post ID.

    Args:
        caption:   Full caption string (hook + body + hashtags).
        video_url: Publicly reachable URL of the video to post (MP4, 9:16 works best).
    """
    user_id, token = _credentials()
    with httpx.Client(base_url=_GRAPH_BASE, timeout=60) as client:
        creation_id = _create_container(
            client,
            user_id,
            {
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption,
                "access_token": token,
            },
        )
        _wait_for_processing(client, creation_id, token)
        return _publish(client, user_id, creation_id, token)
