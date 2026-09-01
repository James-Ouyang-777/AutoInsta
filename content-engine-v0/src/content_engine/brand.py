"""Brand style spec — loads brand_style.yaml and assembles prompts from it.

brand_style.yaml is the single source of truth for character canon, visual
style, and caption voice. Everything that generates content (reference images,
post images, captions) should build its prompts through this module so the
canon is repeated verbatim on every generation.
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path
from textwrap import dedent

import yaml

from .llm_adapter import generate_caption as _generate_caption_llm
from .normalize import apply_prohibited, truncate

_BRANDS_ROOT = Path(__file__).resolve().parents[2] / "brands"

DEFAULT_BRAND = "jammy-o"


class BrandError(RuntimeError):
    """Raised when the brand spec is missing or malformed."""


def _default_brand() -> str:
    return os.getenv("BRAND", DEFAULT_BRAND)


def brand_dir(brand: str | None = None) -> Path:
    return _BRANDS_ROOT / (brand or _default_brand())


def load_style(path: Path | None = None, brand: str | None = None) -> dict:
    style_path = path or (brand_dir(brand) / "brand_style.yaml")
    if not style_path.exists():
        raise BrandError(f"Brand style spec not found: {style_path}")
    with open(style_path) as f:
        return yaml.safe_load(f)


def load_scenes(brand: str | None = None) -> list[dict]:
    scenes_path = brand_dir(brand) / "scenes.yaml"
    if not scenes_path.exists():
        raise BrandError(f"Scene rotation not found: {scenes_path}")
    with open(scenes_path) as f:
        data = yaml.safe_load(f)
    scenes = data.get("scenes") if isinstance(data, dict) else None
    if not scenes:
        raise BrandError(f"Scene rotation is empty: {scenes_path}")
    return scenes


def scene_for_date(date: datetime.date, brand: str | None = None) -> dict:
    """Deterministically pick today's scene from the brand's rotation."""
    scenes = load_scenes(brand)
    idx = date.toordinal() % len(scenes)
    return scenes[idx]


def character_keys(style: dict) -> list[str]:
    """All known character keys: the main character plus supporting cast."""
    return [style.get("main_character", "jammy-o"), *style.get("supporting_characters", {}).keys()]


def _character_block(style: dict, key: str) -> dict:
    if key == style.get("main_character", "jammy-o"):
        return style["character"]
    supporting = style.get("supporting_characters", {})
    if key not in supporting:
        raise BrandError(f"Unknown character '{key}'. Known: {character_keys(style)}")
    return supporting[key]


def character_sheet(style: dict, key: str) -> str:
    """The canonical one-paragraph description of a character."""
    c = _character_block(style, key)
    parts = [f"{c['name']}: {c['form']}.", f"Body: {c['body']}."]
    for field in ("lid", "label", "face", "limbs"):
        if c.get(field):
            parts.append(f"{field.capitalize()}: {c[field]}.")
    return " ".join(parts)


def reference_prompt(style: dict, key: str) -> str:
    """Prompt for a clean studio reference image of one character."""
    vs = style["visual_style"]
    return (
        f"Character reference image, {vs['rendering']}. "
        f"{character_sheet(style, key)} "
        f"Full body, front view, single character centered on a plain warm cream "
        f"studio background, {vs['lighting']}. "
        f"No label on the jar, no text anywhere, no watermarks, no other characters or props."
    )


def scene_prompt(style: dict, scene: str, characters: list[str]) -> str:
    """Prompt for a post image placing the referenced characters in a scene.

    Intended for the image-edit endpoint with the approved reference images
    attached — the prompt re-states each character's canon so the model keeps
    them on-model, and the scene text drives setting and lighting.
    """
    vs = style["visual_style"]
    sheets = " ".join(character_sheet(style, key) for key in characters)
    names = ", ".join(_character_block(style, key)["name"] for key in characters)
    return (
        f"{vs['rendering']}. "
        f"The attached reference images show the exact characters to use: {names}. "
        f"Keep every character exactly on-model: {sheets} "
        f"Scene: {scene}. "
        f"The characters are the clear heroes of the frame, square 1:1 composition. "
        f"Strictly no text or lettering anywhere, no labels on jars, no watermarks, "
        f"no logos, no realistic human faces, no photorealism — the whole world is "
        f"rendered in the same soft 3D cartoon style."
    )


def reference_image_path(key: str, brand: str | None = None) -> Path:
    """Path of the approved canonical reference for a character."""
    return brand_dir(brand) / "references" / f"{key}.png"


def short_caption_prompt(style: dict, topic: str) -> str:
    """Prompt for a single short witty caption sentence — no hashtags, no CTA block."""
    voice = style["voice"]
    prohibited = voice.get("prohibited", []) or []
    prohibited_line = ", ".join(prohibited) if prohibited else "none"
    return dedent(
        f"""
        Write exactly ONE short, witty sentence for an Instagram caption about jam.
        Scene: "{topic}".
        Voice: {voice['tone']}. {voice['person']}.
        At most one pun. No hashtags. {voice['emojis']}.
        Avoid these words/topics entirely: {prohibited_line}.
        Respond with strict JSON: {{"caption": str}}.
        """
    ).strip()


def generate_short_caption(style: dict, topic: str) -> str:
    """Generate and sanitize the single-sentence brand caption. Raises LLMError."""
    raw = _generate_caption_llm(short_caption_prompt(style, topic))
    prohibited = style["voice"].get("prohibited", [])
    max_chars = int(style["voice"].get("max_chars", 150))
    return truncate(apply_prohibited(raw, prohibited), max_chars)
