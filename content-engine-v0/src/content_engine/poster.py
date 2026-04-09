"""Minimal Instagram Graph API poster.

Requires:
  INSTAGRAM_USER_ID     — numeric Instagram user ID
  INSTAGRAM_ACCESS_TOKEN — long-lived access token with instagram_content_publish scope

Posting flow (photo):
  1. POST /{user_id}/media  → creates a media container, returns creation_id
  2. POST /{user_id}/media_publish  → publishes the container, returns post_id
"""

from __future__ import annotations

import os

import httpx
from dotenv import load_dotenv

load_dotenv()

_GRAPH_BASE = "https://graph.instagram.com/v21.0"


class PostError(RuntimeError):
    """Raised when publishing to Instagram fails."""


def post_instagram(caption: str, image_url: str) -> str:
    """Upload a photo and publish it to Instagram. Returns the published post ID.

    Args:
        caption:   Full caption string (hook + body + hashtags).
        image_url: Publicly reachable URL of the image to post.

    Returns:
        The Instagram post ID string.
    """
    user_id = os.getenv("INSTAGRAM_USER_ID")
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")

    if not user_id or not token:
        raise PostError(
            "INSTAGRAM_USER_ID and INSTAGRAM_ACCESS_TOKEN must be set in the environment."
        )

    with httpx.Client(base_url=_GRAPH_BASE, timeout=60) as client:
        # Step 1: create media container
        r = client.post(
            f"/{user_id}/media",
            params={
                "image_url": image_url,
                "caption": caption,
                "access_token": token,
            },
        )
        if not r.is_success:
            raise PostError(f"Media container creation failed ({r.status_code}): {r.text}")
        creation_id = r.json().get("id")
        if not creation_id:
            raise PostError(f"No container ID in response: {r.text}")

        # Step 2: publish
        r = client.post(
            f"/{user_id}/media_publish",
            params={
                "creation_id": creation_id,
                "access_token": token,
            },
        )
        if not r.is_success:
            raise PostError(f"Publish failed ({r.status_code}): {r.text}")
        post_id = r.json().get("id")
        if not post_id:
            raise PostError(f"No post ID in publish response: {r.text}")

        return post_id
