#!/usr/bin/env python3
"""Generate and approve canonical character reference images.

Candidates are saved locally under references/candidates/ so nothing is lost
when the API's temporary URL expires. Approving a candidate copies it to
references/<character>.png — the canonical reference the posting pipeline can
use for character consistency.

Usage:
    python generate_reference.py                          # 1 Jammy-O candidate
    python generate_reference.py --character pineapple -n 3
    python generate_reference.py --approve references/candidates/jammy-o-....png
"""

from __future__ import annotations

import argparse
import base64
import datetime
import os
import shutil
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

from content_engine import brand


def _dirs(brand_name: str | None) -> tuple[Path, Path]:
    references_dir = brand.brand_dir(brand_name) / "references"
    return references_dir, references_dir / "candidates"


def _generate(prompt: str, n: int) -> list[bytes]:
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        sys.exit("LLM_API_KEY missing — set it in your .env file.")
    base_url = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
    model = os.getenv("IMAGE_MODEL", "gpt-image-1")

    payload = {"model": model, "prompt": prompt, "n": n, "size": "1024x1024"}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    with httpx.Client(timeout=180) as client:
        r = client.post(f"{base_url}/images/generations", headers=headers, json=payload)
        if not r.is_success:
            sys.exit(f"Image generation failed ({r.status_code}): {r.text}")
        images = []
        for item in r.json().get("data", []):
            if item.get("b64_json"):
                images.append(base64.b64decode(item["b64_json"]))
            elif item.get("url"):
                dl = client.get(item["url"])
                dl.raise_for_status()
                images.append(dl.content)
        if not images:
            sys.exit("Image API returned no images.")
        return images


def _approve(candidate: Path, references_dir: Path, keys: list[str]) -> None:
    if not candidate.exists():
        sys.exit(f"Candidate not found: {candidate}")
    # Candidate filenames start with the character key, e.g. jammy-o-20260802-....png
    stem = candidate.stem
    character = next((k for k in keys if stem.startswith(k)), None)
    if character is None:
        sys.exit(f"Cannot infer character from filename '{candidate.name}' (known: {keys}).")
    target = references_dir / f"{character}.png"
    shutil.copyfile(candidate, target)
    print(f"Approved: {candidate.name} -> {target}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate/approve character reference images.")
    parser.add_argument("--brand", default=None, help="Brand key under brands/ (default: $BRAND or jammy-o).")
    parser.add_argument("--character", default=None, help="Which character to generate (default: brand's main character).")
    parser.add_argument("-n", type=int, default=1, help="Number of candidates (default: 1).")
    parser.add_argument(
        "--approve",
        metavar="CANDIDATE_PNG",
        help="Promote a candidate to the canonical reference (references/<character>.png).",
    )
    args = parser.parse_args()

    style = brand.load_style(brand=args.brand)
    keys = brand.character_keys(style)
    character = args.character or keys[0]
    if character not in keys:
        parser.error(f"Unknown character '{character}'. Known: {keys}")

    references_dir, candidates_dir = _dirs(args.brand)

    if args.approve:
        _approve(Path(args.approve), references_dir, keys)
        return

    prompt = brand.reference_prompt(style, character)
    print(f"Prompt:\n{prompt}\n")

    candidates_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    for i, image_bytes in enumerate(_generate(prompt, args.n), start=1):
        path = candidates_dir / f"{character}-{stamp}-{i}.png"
        path.write_bytes(image_bytes)
        print(f"Saved candidate: {path}")

    print("\nReview the candidates, then approve one with:")
    print(f"  python generate_reference.py --approve {candidates_dir}/<file>.png")


if __name__ == "__main__":
    main()
