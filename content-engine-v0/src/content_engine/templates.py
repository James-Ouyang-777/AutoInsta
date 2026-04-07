"""Prompt templates for LLM generation."""

from __future__ import annotations

from textwrap import dedent

from .rules import RULES


def _format_brand(brand: dict[str, object]) -> str:
    voice = brand.get("voice", "")
    audience = brand.get("audience", "")
    reading_level = brand.get("reading_level", "")
    prohibited = brand.get("prohibited", []) or []
    prohibited_lines = "\n".join(f"- {phrase}" for phrase in prohibited)
    return dedent(
        f"""
        Voice: {voice}
        Audience: {audience}
        Reading level: {reading_level}
        Prohibited phrases:\n{prohibited_lines or '- none'}
        """
    ).strip()


def build_prompt(
    platform: str,
    topic: str,
    keywords: list[str],
    brand: dict[str, object],
    cta_style: str,
    n_variants: int,
) -> str:
    """Return a compact system+user prompt enforcing platform rules."""
    if platform not in RULES:
        raise ValueError(f"Unsupported platform: {platform}")

    rules = RULES[platform]
    keyword_line = ", ".join(keywords)
    brand_block = _format_brand(brand)

    limit_note = (
        f"Hard cap body length at {rules.max_chars} characters. "
        if rules.max_chars is not None
        else ""
    )

    platform_directives = {
        "x": "Keep hooks punchy, bodies <= 280 characters, max 2 hashtags.",
        "linkedin": "Professional tone, keep concise (<<3000 chars), max 5 hashtags.",
        "instagram": "Use warm tone, allow emojis, target <=250 characters, max 10 hashtags.",
        "youtube_shorts": "Return title and description fields, description brief, optionally include #shorts once.",
        "tiktok": "Casual tone, keep bodies around 150 characters, max 4 hashtags.",
    }[platform]

    return dedent(
        f"""
        You are an expert marketing copywriter.
        Generate {n_variants} distinct {platform} post variants about "{topic}".
        Keywords: {keyword_line}.
        CTA style: {cta_style}.
        Brand profile:\n{brand_block}
        Requirements: {platform_directives} {limit_note}Limit hashtags to {rules.max_hashtags}.
        Ensure each variant has unique hooks, enforced prohibited phrase removal, and reading level alignment.
        Respond with strict JSON: {{"variants": [{{"hook": str, "body": str, "hashtags": [str], "cta": str}}]}}.
        """
    ).strip()
