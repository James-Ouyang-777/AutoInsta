"""Normalization utilities for generated content."""

from __future__ import annotations

import re
from typing import Iterable

from .rules import PlatformRules


def truncate(text: str, limit: int | None) -> str:
    if limit is None:
        return text
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def sanitize_hashtags(tags: Iterable[str], max_count: int) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        normalized = re.sub(r"[^0-9a-z_]+", "", tag.lower())
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(f"#{normalized}")
        if len(cleaned) >= max_count:
            break
    return cleaned


def apply_prohibited(text: str, prohibited: Iterable[str]) -> str:
    result = text
    for phrase in prohibited:
        if not phrase:
            continue
        pattern = re.compile(re.escape(phrase), flags=re.IGNORECASE)
        result = pattern.sub("", result)
    return re.sub(r"\s+", " ", result).strip()


def finalize_variant(variant: dict, platform_rules: PlatformRules, prohibited: Iterable[str]) -> dict:
    hook = apply_prohibited(variant.get("hook", ""), prohibited)
    body = apply_prohibited(variant.get("body", ""), prohibited)
    hashtags = sanitize_hashtags(variant.get("hashtags", []), platform_rules.max_hashtags)
    cta = apply_prohibited(variant.get("cta", ""), prohibited)

    finalized = {
        "hook": truncate(hook, platform_rules.max_chars),
        "body": truncate(body, platform_rules.max_chars),
        "hashtags": hashtags,
        "cta": truncate(cta, platform_rules.max_chars),
    }

    if platform_rules.name == "youtube_shorts":
        finalized.setdefault("title", truncate(variant.get("title", hook), 100))
        finalized.setdefault("description", truncate(variant.get("description", body), None))

    return finalized
