"""High level content generation orchestration."""

from __future__ import annotations

from typing import Any

from .llm_adapter import LLMError, generate_variants
from .normalize import finalize_variant
from .rules import RULES
from .templates import build_prompt


class GenerationError(RuntimeError):
    """Raised when generation fails validation."""


def _ensure_keywords(keywords: list[str]) -> list[str]:
    return [kw.strip() for kw in keywords if kw.strip()]


def generate(
    platform: str,
    topic: str,
    keywords: list[str],
    brand: dict[str, Any],
    cta_style: str,
    n_variants: int,
) -> list[dict[str, Any]]:
    """Generate normalized variants for a platform."""
    if platform not in RULES:
        raise GenerationError(f"Unsupported platform: {platform}")

    keywords = _ensure_keywords(keywords)
    if not keywords:
        raise GenerationError("At least one keyword is required.")

    prompt = build_prompt(platform, topic, keywords, brand, cta_style, n_variants)

    try:
        raw_variants = generate_variants(prompt, n_variants)
    except LLMError as exc:
        raise GenerationError(str(exc)) from exc

    if not isinstance(raw_variants, list):
        raise GenerationError("LLM response malformed.")

    rules = RULES[platform]
    prohibited = brand.get("prohibited", []) if isinstance(brand, dict) else []

    normalized = []
    for variant in raw_variants[:n_variants]:
        if not isinstance(variant, dict):
            raise GenerationError("Variant must be an object.")
        normalized.append(finalize_variant(variant, rules, prohibited))
    return normalized
