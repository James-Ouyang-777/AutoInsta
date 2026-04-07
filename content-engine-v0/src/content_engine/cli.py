"""Typer-based CLI entry point."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
import yaml

from .generator import generate
from .rules import SUPPORTED_PLATFORMS

app = typer.Typer(help="Generate platform-specific social content.")


def _load_brand(brand_path: Optional[Path]) -> dict:
    if not brand_path:
        return {}
    data = yaml.safe_load(brand_path.read_text())
    if not isinstance(data, dict):
        raise typer.BadParameter("Brand file must define a mapping.")
    return data


@app.command("generate")
def generate_command(
    platform: str = typer.Option(..., help="Target platform", case_sensitive=False),
    topic: str = typer.Option(..., help="Content topic"),
    keywords: str = typer.Option(..., help="Comma separated keywords"),
    voice: str = typer.Option("", help="Brand voice"),
    audience: str = typer.Option("", help="Target audience"),
    reading_level: str = typer.Option("", help="Reading level"),
    prohibited: str = typer.Option("", help="Prohibited phrases, comma separated"),
    cta_style: str = typer.Option("soft", help="CTA style"),
    n: int = typer.Option(3, help="Number of variants"),
    out: Optional[Path] = typer.Option(None, help="Optional output file"),
    brand: Optional[Path] = typer.Option(None, help="Path to brand YAML"),
):
    """Generate content variants via CLI."""
    platform_key = platform.lower()
    if platform_key not in SUPPORTED_PLATFORMS:
        raise typer.BadParameter(f"Platform must be one of {', '.join(SUPPORTED_PLATFORMS)}")

    brand_profile = {
        "voice": voice,
        "audience": audience,
        "reading_level": reading_level,
        "prohibited": [p.strip() for p in prohibited.split(",") if p.strip()],
    }

    if brand:
        brand_profile.update(_load_brand(brand))

    keyword_list = [kw.strip() for kw in keywords.split(",") if kw.strip()]

    variants = generate(platform_key, topic, keyword_list, brand_profile, cta_style, n)
    payload = {"platform": platform_key, "topic": topic, "variants": variants}
    output_json = json.dumps(payload, ensure_ascii=False, indent=2)

    if out:
        out.write_text(output_json)
        typer.echo(f"Wrote {len(variants)} variants to {out}")
    else:
        typer.echo(output_json)


def app_wrapper():  # pragma: no cover - console entry alias
    app()


if __name__ == "__main__":  # pragma: no cover
    app()
