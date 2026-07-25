"""fal.ai text-to-video generation for post visuals.

Generates a short (~5 second) vertical 9:16 video suited for Instagram Reels
from a topic and keywords, using fal.ai's queue API.

Requires:
  FAL_KEY          — fal.ai API key (from fal.ai/dashboard/keys)
  FAL_VIDEO_MODEL  — optional model override (default: Kling standard text-to-video)

The returned URL is a fal.ai CDN link that Instagram fetches server-side
during publishing, so no local download is needed.
"""

from __future__ import annotations

import os
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

_QUEUE_BASE = "https://queue.fal.run"
_DEFAULT_MODEL = "fal-ai/kling-video/v2.1/standard/text-to-video"
_POLL_INTERVAL_SECONDS = 5
_MAX_WAIT_SECONDS = 600


class VideoGenError(RuntimeError):
    """Raised when video generation fails."""


def generate_video(topic: str, keywords: list[str], tone: str = "cinematic, vibrant") -> str:
    """Generate a ~5 second vertical video via fal.ai and return its URL.

    Args:
        topic:    What the post is about (used to guide the video prompt).
        keywords: List of keywords for additional visual context.
        tone:     Visual style hint passed to the video model.

    Returns:
        A publicly accessible video URL.
    """
    api_key = os.getenv("FAL_KEY")
    if not api_key:
        raise VideoGenError("FAL_KEY missing — set it in your .env file.")

    model = os.getenv("FAL_VIDEO_MODEL", _DEFAULT_MODEL)
    keyword_str = ", ".join(keywords)
    prompt = (
        f"A short, visually stunning video for an Instagram Reel about {topic}. "
        f"Visual themes: {keyword_str}. "
        f"Style: {tone}, smooth camera movement, natural lighting, high detail. "
        f"No text overlays, no watermarks, no logos."
    )

    payload = {
        "prompt": prompt,
        "duration": "5",
        "aspect_ratio": "9:16",
    }
    headers = {
        "Authorization": f"Key {api_key}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=60) as client:
        # Submit the generation job to the queue
        r = client.post(f"{_QUEUE_BASE}/{model}", headers=headers, json=payload)
        if not r.is_success:
            raise VideoGenError(f"Video job submission failed ({r.status_code}): {r.text}")
        job = r.json()
        status_url = job.get("status_url")
        response_url = job.get("response_url")
        if not status_url or not response_url:
            raise VideoGenError(f"Unexpected queue response shape: {job}")

        # Poll until the job completes
        waited = 0
        while waited < _MAX_WAIT_SECONDS:
            r = client.get(status_url, headers=headers)
            if not r.is_success:
                raise VideoGenError(f"Status check failed ({r.status_code}): {r.text}")
            status = r.json().get("status")
            if status == "COMPLETED":
                break
            if status in ("FAILED", "CANCELLED"):
                raise VideoGenError(f"Video generation {status.lower()}: {r.text}")
            time.sleep(_POLL_INTERVAL_SECONDS)
            waited += _POLL_INTERVAL_SECONDS
        else:
            raise VideoGenError(
                f"Video generation timed out after {_MAX_WAIT_SECONDS}s (model: {model})."
            )

        # Fetch the result
        r = client.get(response_url, headers=headers)
        if not r.is_success:
            raise VideoGenError(f"Result fetch failed ({r.status_code}): {r.text}")
        data = r.json()
        try:
            url = data["video"]["url"]
        except (KeyError, TypeError) as exc:
            raise VideoGenError(f"Unexpected video response shape: {data}") from exc
        return url
