"""Platform-specific normalization rules."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PlatformRules:
    name: str
    max_chars: Optional[int]
    max_hashtags: int
    extra: dict


RULES: dict[str, PlatformRules] = {
    "x": PlatformRules(
        name="x",
        max_chars=280,
        max_hashtags=2,
        extra={"tone": "concise, punchy"},
    ),
    "linkedin": PlatformRules(
        name="linkedin",
        max_chars=3000,
        max_hashtags=5,
        extra={"tone": "professional"},
    ),
    "instagram": PlatformRules(
        name="instagram",
        max_chars=250,
        max_hashtags=10,
        extra={"tone": "playful, emoji-friendly"},
    ),
    "youtube_shorts": PlatformRules(
        name="youtube_shorts",
        max_chars=None,
        max_hashtags=5,
        extra={"requires_title": True},
    ),
    "tiktok": PlatformRules(
        name="tiktok",
        max_chars=150,
        max_hashtags=4,
        extra={"tone": "casual"},
    ),
}

SUPPORTED_PLATFORMS = tuple(RULES.keys())
