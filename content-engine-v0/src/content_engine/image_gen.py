"""DALL-E image generation for post visuals.

Generates a square (1024x1024) image suited for Instagram from a topic and
keywords. Uses the same LLM_API_KEY and LLM_API_BASE already configured for
caption generation, so no extra credentials are needed.

Note: The returned URL is a temporary OpenAI/Azure CDN link valid for ~1 hour.
      It is fetched immediately by Instagram during publishing, so expiry is
      not a problem in the generate-then-post flow.
"""

from __future__ import annotations

import os

import httpx
from dotenv import load_dotenv

load_dotenv()


class ImageGenError(RuntimeError):
    """Raised when image generation fails."""


def generate_image(topic: str, keywords: list[str], tone: str = "warm, aesthetic") -> str:
    """Generate a post image via DALL-E and return its URL.

    Args:
        topic:    What the post is about (used to guide the image prompt).
        keywords: List of keywords for additional visual context.
        tone:     Visual style hint passed to DALL-E.

    Returns:
        A publicly accessible image URL (valid for ~1 hour).
    """
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        raise ImageGenError("LLM_API_KEY missing — set it in your .env file.")

    keyword_str = ", ".join(keywords)
    prompt = (
        f"A high-quality, visually striking photo for an Instagram post about {topic}. "
        f"Visual themes: {keyword_str}. "
        f"Style: {tone}, professional photography, soft natural lighting, clean composition. "
        f"No text overlays, no watermarks, no logos."
    )

    payload = {
        "model": os.getenv("IMAGE_MODEL", "dall-e-3"),
        "prompt": prompt,
        "n": 1,
        "size": "1024x1024",
        "response_format": "url",
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    base_url = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")

    with httpx.Client(timeout=90) as client:
        r = client.post(f"{base_url}/images/generations", headers=headers, json=payload)
        if not r.is_success:
            raise ImageGenError(f"Image generation failed ({r.status_code}): {r.text}")
        data = r.json()
        try:
            url = data["data"][0]["url"]
        except (KeyError, IndexError) as exc:
            raise ImageGenError(f"Unexpected image response shape: {data}") from exc
        return url
