from content_engine.normalize import apply_prohibited, finalize_variant, sanitize_hashtags, truncate
from content_engine.rules import RULES
from content_engine.templates import build_prompt


def test_hashtag_dedupe_and_limit():
    tags = ["#One", "two", "Two", "THREE", "four", "five"]
    result = sanitize_hashtags(tags, 3)
    assert result == ["#one", "#two", "#three"]


def test_truncate_x_body():
    long_text = "x" * 500
    truncated = truncate(long_text, RULES["x"].max_chars)
    assert len(truncated) <= RULES["x"].max_chars


def test_prohibited_removed():
    text = "This guarantees results now!"
    cleaned = apply_prohibited(text, ["guarantees results"])
    assert "guarantees results" not in cleaned.lower()


def test_prompt_contains_topic_and_keywords():
    prompt = build_prompt(
        "x",
        "Launch",
        ["alpha", "beta"],
        {"voice": "bold", "audience": "founders", "reading_level": "grade 8", "prohibited": []},
        "question",
        2,
    )
    assert "Launch" in prompt
    assert "alpha, beta" in prompt


def test_finalize_variant_caps_hashtags():
    variant = {
        "hook": "Hook",
        "body": "Body",
        "hashtags": ["Test", "Test", "Another"],
        "cta": "Call",
    }
    finalized = finalize_variant(variant, RULES["x"], [])
    assert finalized["hashtags"] == ["#test", "#another"]
