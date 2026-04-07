"""FastAPI application exposing the content generator."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from .generator import generate
from .rules import SUPPORTED_PLATFORMS

app = FastAPI(title="Content Engine v0", version="0.1.0")


class BrandProfile(BaseModel):
    voice: str = Field("", description="Brand voice")
    audience: str = Field("", description="Target audience")
    reading_level: str = Field("", description="Desired reading level")
    prohibited: list[str] = Field(default_factory=list, description="Prohibited phrases")


class GenerateRequest(BaseModel):
    platform: str
    topic: str
    keywords: list[str]
    brand: BrandProfile
    cta_style: str
    n_variants: int = Field(default_factory=lambda: int(os.getenv("DEFAULT_VARIANTS", "3")))

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, value: str) -> str:
        lowered = value.lower()
        if lowered not in SUPPORTED_PLATFORMS:
            raise ValueError(f"Platform must be one of {', '.join(SUPPORTED_PLATFORMS)}")
        return lowered

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, keywords: list[str]) -> list[str]:
        cleaned = [kw.strip() for kw in keywords if kw.strip()]
        if not cleaned:
            raise ValueError("At least one keyword is required")
        return cleaned


class GenerateResponse(BaseModel):
    platform: str
    topic: str
    variants: list[dict[str, Any]]


def request_to_payload(payload: GenerateRequest) -> GenerateResponse:
    try:
        variants = generate(
            payload.platform,
            payload.topic,
            payload.keywords,
            payload.brand.model_dump(),
            payload.cta_style,
            payload.n_variants,
        )
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return GenerateResponse(platform=payload.platform, topic=payload.topic, variants=variants)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/generate", response_model=GenerateResponse)
def post_generate(payload: GenerateRequest) -> GenerateResponse:
    return request_to_payload(payload)
