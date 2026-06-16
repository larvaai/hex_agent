"""OpenAI-compatible LLM adapter — JSON-mode, lazy client, injectable for tests. Epic E03."""
from __future__ import annotations

import json
import os
from typing import Any

# Lazy module-level client cache. Importing this module does NOT build a client
# and does NOT import the openai package — that happens on first real call.
_client: Any = None


def _defaults() -> dict[str, Any]:
    return {
        "base_url": os.getenv("LLM_BASE_URL", "http://localhost:1234/v1"),
        "api_key": os.getenv("LLM_API_KEY", "lm-studio"),
        "model": os.getenv("LLM_MODEL", "local-model"),
        "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "2048")),
        "timeout": float(os.getenv("LLM_TIMEOUT", "600")),
    }


def _get_client() -> Any:
    global _client
    if _client is None:
        from openai import OpenAI  # lazy import

        cfg = _defaults()
        _client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"], timeout=cfg["timeout"])
    return _client


def reset_client() -> None:
    global _client
    _client = None


def call_llm(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float = 0.2,
    json_mode: bool = True,
    client: Any = None,
) -> str:
    """
    Call an OpenAI-compatible chat endpoint.

    - `json_mode=True` sets response_format=json_object so the model returns JSON.
    - `client` can be injected (for tests); otherwise a lazy module client is used.
    - On error, returns a structured `final` JSON string (never raises into the loop).
    """
    cfg = _defaults()
    active = client if client is not None else _get_client()
    kwargs: dict[str, Any] = {
        "model": model or cfg["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": cfg["max_tokens"],
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        response = active.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""
    except Exception as exc:
        return json.dumps(
            {"action": "final", "finish_reason": "error", "message": f"LLM request failed: {exc}"},
            ensure_ascii=False,
        )
