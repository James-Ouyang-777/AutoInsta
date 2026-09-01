"""DALL-E image generation for post visuals.

Generates a square (1024x1024) image suited for Instagram from a topic and
keywords. Uses the same LLM_API_KEY and LLM_API_BASE already configured for
caption generation, so no extra credentials are needed.

Note: The returned URL is a temporary OpenAI/Azure CDN link valid for ~1 hour.
      It is fetched immediately by Instagram during publishing, so expiry is
      not a problem in the generate-then-post flow.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()


class ImageGenError(RuntimeError):
    """Raised when image generation fails."""


def _upload_base64_to_cloudinary(b64_data: str) -> str:
    """Upload base64 image data to Cloudinary and return a public URL.

    Requires unsigned upload env vars:
      - CLOUDINARY_CLOUD_NAME
      - CLOUDINARY_UPLOAD_PRESET
    """
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
    upload_preset = os.getenv("CLOUDINARY_UPLOAD_PRESET")
    if not cloud_name or not upload_preset:
        raise ImageGenError(
            "Image API returned base64 (no URL). Configure CLOUDINARY_CLOUD_NAME and "
            "CLOUDINARY_UPLOAD_PRESET for automatic hosting."
        )

    # Decode/validate first so errors are clearer than downstream host errors.
    try:
        image_bytes = base64.b64decode(b64_data, validate=True)
    except Exception as exc:
        raise ImageGenError("Image API returned invalid base64 image data.") from exc

    upload_url = f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload"
    with httpx.Client(timeout=60) as client:
        r = client.post(
            upload_url,
            data={"upload_preset": upload_preset},
            files={"file": ("generated.png", image_bytes, "image/png")},
        )
        if not r.is_success:
            raise ImageGenError(f"Cloudinary upload failed ({r.status_code}): {r.text}")
        secure_url = r.json().get("secure_url")
        if not secure_url:
            raise ImageGenError(f"Cloudinary response missing secure_url: {r.text}")
        return secure_url


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

    model = os.getenv("IMAGE_MODEL", "gpt-image-1")

    payload = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": "1024x1024",
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    base_url = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")

    with httpx.Client(timeout=90) as client:
        r = client.post(f"{base_url}/images/generations", headers=headers, json=payload)
        if not r.is_success:
            try:
                err = r.json().get("error", {})
                msg = err.get("message", r.text)
                param = err.get("param")
                code = err.get("code")
            except Exception:
                msg = r.text
                param = None
                code = None

            if param == "model" or code == "invalid_value":
                raise ImageGenError(
                    f"Image model '{model}' is not available for this API key/provider. "
                    "Set IMAGE_MODEL in .env to a supported model and retry."
                )
            raise ImageGenError(f"Image generation failed ({r.status_code}): {msg}")
        data = r.json()
        try:
            first = data["data"][0]
            url = first.get("url")
            b64_json = first.get("b64_json")
        except (KeyError, IndexError) as exc:
            raise ImageGenError(f"Unexpected image response shape: {data}") from exc
        if not url:
            # Instagram requires a publicly reachable URL; many modern models
            # return b64 image bytes instead. Host it and continue.
            if b64_json:
                return _upload_base64_to_cloudinary(b64_json)
            raise ImageGenError("Image API returned neither URL nor base64 image data.")
        return url


def generate_scene_image(prompt: str, reference_paths: list[Path]) -> bytes:
    """Generate a post image from approved character references via /images/edits.

    The reference PNGs are attached so the model reproduces the exact approved
    characters; the prompt describes the scene. Returns raw PNG bytes.
    """
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        raise ImageGenError("LLM_API_KEY missing — set it in your .env file.")

    for path in reference_paths:
        if not path.exists():
            raise ImageGenError(
                f"Reference image missing: {path}. "
                "Generate and approve one with generate_reference.py first."
            )

    model = os.getenv("IMAGE_MODEL", "gpt-image-1")
    base_url = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")

    files = [
        ("image[]", (path.name, path.read_bytes(), "image/png"))
        for path in reference_paths
    ]
    data = {"model": model, "prompt": prompt, "n": "1", "size": "1024x1024"}

    with httpx.Client(timeout=300) as client:
        r = client.post(
            f"{base_url}/images/edits",
            headers={"Authorization": f"Bearer {api_key}"},
            data=data,
            files=files,
        )
        if not r.is_success:
            raise ImageGenError(f"Scene image generation failed ({r.status_code}): {r.text}")
        payload = r.json()
        try:
            first = payload["data"][0]
        except (KeyError, IndexError) as exc:
            raise ImageGenError(f"Unexpected image response shape: {payload}") from exc
        if first.get("b64_json"):
            try:
                return base64.b64decode(first["b64_json"], validate=True)
            except Exception as exc:
                raise ImageGenError("Image API returned invalid base64 image data.") from exc
        if first.get("url"):
            dl = client.get(first["url"])
            if not dl.is_success:
                raise ImageGenError(f"Downloading generated image failed ({dl.status_code}).")
            return dl.content
        raise ImageGenError("Image API returned neither URL nor base64 image data.")


def host_image_publicly(image_path: Path) -> str:
    """Upload a local image and return a public URL Instagram can fetch.

    Prefers Cloudinary when configured; otherwise uses fal.ai storage (the
    FAL_API_KEY already used for video generation), whose CDN URLs persist.
    """
    if os.getenv("CLOUDINARY_CLOUD_NAME") and os.getenv("CLOUDINARY_UPLOAD_PRESET"):
        return _upload_base64_to_cloudinary(base64.b64encode(image_path.read_bytes()).decode())

    fal_key = os.getenv("FAL_KEY") or os.getenv("FAL_API_KEY")
    if not fal_key:
        raise ImageGenError(
            "No public image host configured — set CLOUDINARY_CLOUD_NAME/"
            "CLOUDINARY_UPLOAD_PRESET or FAL_API_KEY in your .env file."
        )
    os.environ["FAL_KEY"] = fal_key
    import fal_client

    try:
        return fal_client.upload_file(str(image_path))
    except Exception as exc:
        raise ImageGenError(f"fal.ai upload failed: {exc}") from exc
