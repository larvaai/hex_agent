"""Parse + repair the model's JSON action; raise JsonGateError on failure. Epic E02."""
from __future__ import annotations

import json
import re
from typing import Any


class JsonGateError(ValueError):
    def __init__(self, message: str, *, stage: str = "parse", candidate: str = "") -> None:
        super().__init__(message)
        self.stage = stage
        self.candidate = candidate


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*", "", t).strip()
        t = re.sub(r"```$", "", t).strip()
    return t


def _repair(candidate: str) -> str:
    # drop trailing commas before } or ]
    fixed = re.sub(r",\s*([}\]])", r"\1", candidate)
    # balance brackets that are open outside of strings
    stack: list[str] = []
    in_string = False
    escaped = False
    for ch in fixed:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch == "}" and stack and stack[-1] == "{":
            stack.pop()
        elif ch == "]" and stack and stack[-1] == "[":
            stack.pop()
    closing = {"{": "}", "[": "]"}
    return fixed + "".join(closing[item] for item in reversed(stack))


def _load_object(text: str) -> dict[str, Any] | None:
    for variant in (text, _repair(text)):
        try:
            parsed = json.loads(variant)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def parse_action(text: str) -> dict[str, Any]:
    """Parse one JSON action object from model output, repairing common breakage."""
    raw = _strip_fences(text or "")
    obj = _load_object(raw)
    if obj is None:
        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", raw):
            for variant in (raw[match.start():], _repair(raw[match.start():])):
                try:
                    parsed, _ = decoder.raw_decode(variant)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    obj = parsed
                    break
            if obj is not None:
                break
    if obj is None:
        raise JsonGateError("Could not parse a JSON object from model output.", candidate=raw[:200])
    if "action" not in obj:
        raise JsonGateError("Missing required 'action' field.", stage="schema", candidate=str(obj)[:200])
    return obj


def build_retry_message(error: JsonGateError) -> str:
    return (
        "Your previous output was not a valid action object "
        f"(stage={error.stage}). Return exactly ONE JSON object with an 'action' field "
        "and no markdown fences or prose."
    )
