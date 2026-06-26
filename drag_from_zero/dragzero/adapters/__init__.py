"""Adapters — concrete implementations that sit *behind* the ports.

Direction of dependency is one-way: adapters import the core seam (`LLM`), the
core never imports adapters. Swapping FakeLLM for a real local LLM is a new
adapter here and nothing else.
"""
from .llm_local import (
    LLMFormatError,
    OpenAICompatLLM,
    RecordedLLM,
    build_messages,
    coerce_response,
    extract_json,
    solo_fallback,
)

__all__ = [
    "LLMFormatError",
    "OpenAICompatLLM",
    "RecordedLLM",
    "build_messages",
    "coerce_response",
    "extract_json",
    "solo_fallback",
]
