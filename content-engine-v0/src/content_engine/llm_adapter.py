"""Adapter responsible for LLM HTTP calls."""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()


class LLMError(RuntimeError):
    """Raised when the LLM response cannot be parsed."""


def _client(timeout: float) -> httpx.Client:
    return httpx.Client(timeout=timeout, base_url=os.getenv("LLM_API_BASE", ""))


def generate_variants(prompt: str, n: int) -> list[dict[str, Any]]:
    """Send prompt to the configured LLM and return parsed variants."""
    api_key = os.getenv("LLM_API_KEY")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    timeout = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))

    if not api_key:
        raise LLMError("LLM_API_KEY missing. Set it in the environment or .env file.")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You create marketing copy."},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    attempt = 0
    last_exc: Exception | None = None
    while attempt < 2:
        try:
            with _client(timeout) as client:
                response = client.post("/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                variants = parsed.get("variants")
                if not isinstance(variants, list):
                    raise LLMError("LLM response missing 'variants' list.")
                if len(variants) < n:
                    raise LLMError("LLM returned fewer variants than requested.")
                return variants
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, LLMError) as exc:
            last_exc = exc
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                break
            backoff = 2 ** attempt
            time.sleep(backoff)
            attempt += 1
        else:
            break

    raise LLMError(f"Failed to obtain variants: {last_exc}")
