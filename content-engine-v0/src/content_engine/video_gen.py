"""fal.ai text-to-video generation for post visuals.

Generates a short (~5 second) vertical 9:16 video suited for Instagram Reels
from a topic and keywords, using fal.ai's queue API.

Requires:
  FAL_KEY / FAL_API_KEY
                   — fal.ai API key (from fal.ai/dashboard/keys)
  Model name is passed directly by caller (or defaults to Kling endpoint).

The returned URL is a fal.ai CDN link that Instagram fetches server-side
during publishing, so no local download is needed.
"""

from __future__ import annotations

import os

import fal_client
from dotenv import load_dotenv

load_dotenv()

_DEFAULT_MODEL = "fal-ai/kling-video/v3/pro/text-to-video"
_DEFAULT_IMAGE_TO_VIDEO_MODEL = "fal-ai/kling-video/v3/pro/image-to-video"


class VideoGenError(RuntimeError):
    """Raised when video generation fails."""


def _extract_video_url(data: dict) -> str | None:
    """Extract video URL from known fal response shapes."""
    video = data.get("video")
    if isinstance(video, dict) and isinstance(video.get("url"), str):
        return video["url"]

    videos = data.get("videos")
    if isinstance(videos, list) and videos:
        first = videos[0]
        if isinstance(first, dict) and isinstance(first.get("url"), str):
            return first["url"]

    output = data.get("output")
    if isinstance(output, dict):
        out_video = output.get("video")
        if isinstance(out_video, dict) and isinstance(out_video.get("url"), str):
            return out_video["url"]
        out_videos = output.get("videos")
        if isinstance(out_videos, list) and out_videos:
            first = out_videos[0]
            if isinstance(first, dict) and isinstance(first.get("url"), str):
                return first["url"]
    return None


def generate_video(
    topic: str,
    keywords: list[str],
    tone: str = "cinematic, vibrant",
    model: str | None = None,
    generate_audio: bool = True,
) -> str:
    """Generate a ~5 second vertical video via fal.ai and return its URL.

    Args:
        topic:          What the post is about (used to guide the video prompt).
        keywords:       List of keywords for additional visual context.
        tone:           Visual style hint passed to the video model.
        model:          Optional fal model route override.
        generate_audio: Whether to generate native audio (default: True).

    Returns:
        A publicly accessible video URL.
    """
    api_key = os.getenv("FAL_KEY") or os.getenv("FAL_API_KEY")
    if not api_key:
        raise VideoGenError("FAL_KEY (or FAL_API_KEY) missing — set it in your .env file.")

    model = model or _DEFAULT_MODEL
    keyword_str = ", ".join(keywords)
    prompt = (
        f"A short, visually stunning video for an Instagram Reel about {topic}. "
        f"Visual themes: {keyword_str}. "
        f"Style: {tone}, smooth camera movement, natural lighting, high detail. "
        f"No text overlays, no watermarks, no logos."
    )

    arguments = {
        "prompt": prompt,
        "duration": "5",
        "aspect_ratio": "9:16",
        "generate_audio": generate_audio,
    }
    # fal_client handles queue submit/status/result correctly across model families.
    os.environ["FAL_KEY"] = api_key
    try:
        data = fal_client.subscribe(model, arguments=arguments, with_logs=False)
    except Exception as exc:
        raise VideoGenError(f"Video generation failed for model '{model}': {exc}") from exc

    if not isinstance(data, dict):
        raise VideoGenError(f"Unexpected video response type: {type(data).__name__}")

    video_url = _extract_video_url(data)
    if not video_url:
        raise VideoGenError(f"Unexpected video response shape: {data}")
    return video_url


def generate_video_from_image(
    image_url: str,
    motion_prompt: str,
    duration: str = "5",
    generate_audio: bool = True,
    model: str | None = None,
) -> str:
    """Animate a still image into a short video via fal.ai image-to-video.

    Unlike generate_video, this keeps the exact characters/scene from the
    source image — no new image content is generated, only motion.

    Args:
        image_url:      Publicly accessible URL of the source still image.
        motion_prompt:  Describes the desired motion/animation.
        duration:       Video length in seconds as a string (3-15).
        generate_audio: Whether to generate native audio (default: True).
        model:          Optional fal model route override.

    Returns:
        A publicly accessible video URL.
    """
    api_key = os.getenv("FAL_KEY") or os.getenv("FAL_API_KEY")
    if not api_key:
        raise VideoGenError("FAL_KEY (or FAL_API_KEY) missing — set it in your .env file.")

    model = model or _DEFAULT_IMAGE_TO_VIDEO_MODEL
    arguments = {
        "start_image_url": image_url,
        "prompt": motion_prompt,
        "duration": duration,
        "generate_audio": generate_audio,
    }
    os.environ["FAL_KEY"] = api_key
    try:
        data = fal_client.subscribe(model, arguments=arguments, with_logs=False)
    except Exception as exc:
        raise VideoGenError(f"Image-to-video generation failed for model '{model}': {exc}") from exc

    if not isinstance(data, dict):
        raise VideoGenError(f"Unexpected video response type: {type(data).__name__}")

    video_url = _extract_video_url(data)
    if not video_url:
        raise VideoGenError(f"Unexpected video response shape: {data}")
    return video_url
