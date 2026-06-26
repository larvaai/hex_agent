"""OpenAI-compatible LLM adapter — JSON-mode, lazy client, retry/backoff on transient errors, injectable. Epic E03."""
from __future__ import annotations

import json
import os
import time
from typing import Any

_client: Any = None
_sleep = time.sleep  # module-level so tests can monkeypatch it


def _defaults() -> dict[str, Any]:
    return {
        "base_url": os.getenv("LLM_BASE_URL", "http://localhost:1234/v1"),
        "api_key": os.getenv("LLM_API_KEY", "lm-studio"),
        "model": os.getenv("LLM_MODEL", "local-model"),
        "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "2048")),
        "timeout": float(os.getenv("LLM_TIMEOUT", "120")),       # was 600 — a hung socket no longer blocks 10 min
        "max_retries": int(os.getenv("LLM_MAX_RETRIES", "2")),
        "retry_base": float(os.getenv("LLM_RETRY_BASE", "0.5")),
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


def _is_transient(exc: Exception) -> bool:
    """Worth retrying: timeouts, dropped connections, rate limit (429), server errors (5xx).
    Permanent: client errors (4xx except 429) and anything we cannot classify. Duck-typed so we
    do not need to import openai's exception classes (keeps the adapter lazy + injectable)."""
    status = getattr(exc, "status_code", None)
    if not isinstance(status, int):
        status = getattr(exc, "status", None)
    if isinstance(status, int):
        return status == 429 or status >= 500
    name = type(exc).__name__.lower()
    return "timeout" in name or "connection" in name


def _is_connection_error(exc: Exception) -> bool:
    """The request never reached an HTTP status — the endpoint is unreachable (server down, wrong
    host:port), not a request the server rejected. Drives the actionable hint in the failure message
    (the #1 local-LLM failure is 'model loaded in the UI but the API server was never started')."""
    if isinstance(getattr(exc, "status_code", None), int) or isinstance(getattr(exc, "status", None), int):
        return False
    return "connection" in type(exc).__name__.lower()


def _is_response_format_error(exc: Exception) -> bool:
    """True when the server rejected ``response_format={"type":"json_object"}``.

    Several OpenAI-compatible local servers (llama.cpp, vLLM, newer LM Studio builds) only accept
    ``json_schema`` or ``text`` and 400 on ``json_object`` — e.g. "'response_format.type' must be
    'json_schema' or 'text'". The JSON gate parses plain text anyway, so we downgrade to text mode
    rather than fail the whole run; this keeps the agent working across servers with no config change."""
    return "response_format" in str(exc).lower()


def call_llm(messages, *, model=None, temperature=0.2, json_mode=True, client=None) -> str:
    """Call an OpenAI-compatible chat endpoint. Retries transient failures with exponential backoff;
    if the server rejects ``json_object`` it retries once in text mode; on permanent failure (or
    exhausted retries) returns a structured `final`/error JSON (never raises)."""
    cfg = _defaults()
    active = client if client is not None else _get_client()
    kwargs: dict[str, Any] = {"model": model or cfg["model"], "messages": messages,
                              "temperature": temperature, "max_tokens": cfg["max_tokens"]}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    attempts = max(1, cfg["max_retries"] + 1)
    last_exc: Exception | None = None
    attempt = 0
    downgraded = False
    while attempt < attempts:
        try:
            response = active.chat.completions.create(**kwargs)
            return response.choices[0].message.content or ""
        except Exception as exc:
            last_exc = exc
            # Server rejected json_object → downgrade to text once and retry without spending an
            # attempt (it is a config mismatch, not a flaky call). The JSON gate still parses the text.
            if json_mode and not downgraded and _is_response_format_error(exc):
                kwargs["response_format"] = {"type": "text"}
                downgraded = True
                continue
            if attempt + 1 < attempts and _is_transient(exc):
                _sleep(cfg["retry_base"] * (2 ** attempt))  # exp backoff: 0.5, 1.0, 2.0, ...
                attempt += 1
                continue
            break

    # Build an ACTIONABLE failure message: openai's APIConnectionError stringifies to a bare
    # "Connection error." that hides both the cause and the endpoint, so the user cannot tell a
    # dead server from a bad request. Surface the underlying cause and, for an unreachable endpoint,
    # name the URL + hint the server may be down.
    detail = str(last_exc)
    cause = last_exc.__cause__ if last_exc is not None else None
    if cause and str(cause) and str(cause) not in detail:
        detail = f"{detail} ({cause})"
    if last_exc is not None and _is_connection_error(last_exc):
        detail = f"{detail} — cannot reach the LLM at {cfg['base_url']}; is the server running?"
    return json.dumps(
        {"action": "final", "finish_reason": "error",
         "message": f"LLM request failed after {attempt + 1} attempt(s): {detail}"},
        ensure_ascii=False,
    )
