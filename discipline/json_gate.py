"""Parse + repair the model's JSON action; raise JsonGateError on failure. Epic E02.

The gate is **deterministic-first**: it tries the raw text unchanged, then a ladder of
increasingly aggressive — but still pure ``str -> str`` — repair candidates, then an
``ast.literal_eval`` fallback. Valid JSON is always recovered by the *first* (raw)
candidate, so a well-formed object is never mutated by a repair rule.

Repair rules (ported from the my_agents output_gate, re-homed here) cover what local /
open models actually emit: markdown fences, surrounding prose, trailing commas, Python
literals (``True``/``False``/``None``), unquoted keys, single-quoted tokens, and raw
control characters inside strings. Each rule is a total function on arbitrary text.
"""
from __future__ import annotations

import ast
import json
import re
from typing import Any, Callable


class JsonGateError(ValueError):
    def __init__(self, message: str, *, stage: str = "parse", candidate: str = "") -> None:
        super().__init__(message)
        self.stage = stage
        self.candidate = candidate


# ── deterministic repair rules (pure str -> str) ─────────────────────────────


def strip_bom(text: str) -> str:
    return (text or "").lstrip("﻿").strip()


def strip_markdown_fence(text: str) -> str:
    """Return the contents of the first ```-fenced block, else the text unchanged."""
    match = re.search(r"```(?:json|JSON)?\s*(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def _extract_balanced_region(text: str, open_char: str, close_char: str) -> str | None:
    best: str | None = None
    for start, char in enumerate(text):
        if char != open_char:
            continue
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            current = text[index]
            if escaped:
                escaped = False
                continue
            if current == "\\":
                escaped = True
                continue
            if current == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if current == open_char:
                depth += 1
            elif current == close_char:
                depth -= 1
                if depth == 0:
                    candidate = text[start:index + 1]
                    if best is None or len(candidate) > len(best):
                        best = candidate
                    break
    return best


def extract_largest_json_region(text: str) -> str:
    """Extract the largest balanced ``{...}`` or ``[...]`` region from noisy text."""
    text = text.strip()
    obj = _extract_balanced_region(text, "{", "}")
    arr = _extract_balanced_region(text, "[", "]")
    if obj and arr:
        return obj if len(obj) >= len(arr) else arr
    return obj or arr or text


def remove_trailing_commas(text: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", text)


def _replace_identifiers_outside_strings(text: str, replacements: dict[str, str]) -> str:
    result: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if escaped:
            result.append(char)
            escaped = False
            index += 1
            continue
        if char == "\\":
            result.append(char)
            escaped = True
            index += 1
            continue
        if char == '"':
            result.append(char)
            in_string = not in_string
            index += 1
            continue
        if not in_string and (char.isalpha() or char == "_"):
            start = index
            index += 1
            while index < len(text) and (text[index].isalnum() or text[index] == "_"):
                index += 1
            word = text[start:index]
            result.append(replacements.get(word, word))
            continue
        result.append(char)
        index += 1
    return "".join(result)


def replace_python_literals(text: str) -> str:
    return _replace_identifiers_outside_strings(text, {"True": "true", "False": "false", "None": "null"})


def quote_unquoted_keys(text: str) -> str:
    """Quote bare identifier keys (``{key: ...}`` -> ``{"key": ...}``) outside strings."""
    result: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if escaped:
            result.append(char)
            escaped = False
            index += 1
            continue
        if char == "\\":
            result.append(char)
            escaped = True
            index += 1
            continue
        if char == '"':
            result.append(char)
            in_string = not in_string
            index += 1
            continue
        if not in_string and char in "{,":
            result.append(char)
            index += 1
            start = index
            while index < len(text) and text[index].isspace():
                result.append(text[index])
                index += 1
            key_start = index
            if index < len(text) and (text[index].isalpha() or text[index] == "_"):
                index += 1
                while index < len(text) and (text[index].isalnum() or text[index] == "_"):
                    index += 1
                key = text[key_start:index]
                whitespace_start = index
                while index < len(text) and text[index].isspace():
                    index += 1
                if index < len(text) and text[index] == ":":
                    result.append(f'"{key}"')
                    result.append(text[whitespace_start:index])
                    continue
            result.append(text[key_start:index])
            if index == start:
                continue
            continue
        result.append(char)
        index += 1
    return "".join(result)


def escape_control_chars_in_strings(text: str) -> str:
    repaired: list[str] = []
    in_string = False
    escaped = False
    for char in text:
        if escaped:
            repaired.append(char)
            escaped = False
            continue
        if char == "\\":
            repaired.append(char)
            escaped = True
            continue
        if char == '"':
            repaired.append(char)
            in_string = not in_string
            continue
        if in_string and char == "\n":
            repaired.append("\\n")
            continue
        if in_string and char == "\r":
            repaired.append("\\r")
            continue
        if in_string and char == "\t":
            repaired.append("\\t")
            continue
        repaired.append(char)
    return "".join(repaired)


def _find_single_quote_end(text: str, start: int) -> int | None:
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "'":
            return index
    return None


def _looks_like_json_single_quoted_token(text: str, start: int, end: int) -> bool:
    previous_index = start - 1
    while previous_index >= 0 and text[previous_index].isspace():
        previous_index -= 1
    previous = text[previous_index] if previous_index >= 0 else ""
    next_index = end + 1
    while next_index < len(text) and text[next_index].isspace():
        next_index += 1
    next_char = text[next_index] if next_index < len(text) else ""
    return previous in "{[,:" or next_char == ":"


def convert_single_quoted_values(text: str) -> str:
    """Convert Python-style single-quoted JSON tokens that sit outside double-quoted strings."""
    repaired: list[str] = []
    in_double_string = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if escaped:
            repaired.append(char)
            escaped = False
            index += 1
            continue
        if char == "\\":
            repaired.append(char)
            escaped = True
            index += 1
            continue
        if char == '"':
            repaired.append(char)
            in_double_string = not in_double_string
            index += 1
            continue
        if char == "'" and not in_double_string:
            closing = _find_single_quote_end(text, index + 1)
            if closing is not None and _looks_like_json_single_quoted_token(text, index, closing):
                literal = text[index:closing + 1]
                try:
                    value = ast.literal_eval(literal)
                except Exception:
                    value = literal[1:-1]
                repaired.append(json.dumps(value, ensure_ascii=False))
                index = closing + 1
                continue
        repaired.append(char)
        index += 1
    return "".join(repaired)


def balance_trailing_delimiters(text: str) -> str:
    stack: list[str] = []
    in_string = False
    escaped = False
    for char in text:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char in "{[":
            stack.append(char)
        elif char == "}" and stack and stack[-1] == "{":
            stack.pop()
        elif char == "]" and stack and stack[-1] == "[":
            stack.pop()
    if in_string or len(stack) > 3:
        return text
    closing = {"{": "}", "[": "]"}
    return text + "".join(closing[item] for item in reversed(stack))


def light_json_repair(text: str, *, extract_region: bool = True) -> str:
    """Apply the full deterministic repair pipeline. Total on arbitrary text."""
    repaired = strip_bom(text)
    repaired = strip_markdown_fence(repaired)
    if extract_region:
        repaired = extract_largest_json_region(repaired)
    repaired = remove_trailing_commas(repaired)
    repaired = replace_python_literals(repaired)
    repaired = quote_unquoted_keys(repaired)
    repaired = escape_control_chars_in_strings(repaired)
    repaired = convert_single_quoted_values(repaired)
    repaired = balance_trailing_delimiters(repaired)
    return repaired.strip()


# Legacy bracket-balancer kept as a cheap last-ditch candidate (strict subset of the
# pipeline above); preserved so behavior is a superset of the original gate.
def _repair(candidate: str) -> str:
    fixed = remove_trailing_commas(candidate)
    return balance_trailing_delimiters(fixed)


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*", "", t).strip()
        t = re.sub(r"```$", "", t).strip()
    return t


# ── candidate ladder + load ──────────────────────────────────────────────────


def _safe(fn: Callable[[str], str], text: str) -> str | None:
    """Apply a repair rule, swallowing any failure so the gate never leaks."""
    try:
        return fn(text)
    except Exception:
        return None


def _candidates(raw: str) -> list[str]:
    """Ordered, de-duplicated repair candidates — raw first, most aggressive last."""
    out: list[str] = []
    seen: set[str] = set()

    def add(value: str | None) -> None:
        if value is None:
            return
        if value not in seen:
            seen.add(value)
            out.append(value)

    base = strip_bom(raw)
    add(base)
    fenced = _safe(strip_markdown_fence, base)
    add(fenced)
    # Repair the WHOLE text without region-extraction first: this closes a truncated
    # outer object (e.g. '{"a": {"b": 1}') instead of extract-region prematurely
    # returning the balanced inner object. Raw stays candidate #1 so valid JSON is untouched.
    add(_safe(lambda t: light_json_repair(t, extract_region=False), base))
    region_src = fenced if fenced is not None else base
    add(_safe(extract_largest_json_region, region_src))
    add(_safe(light_json_repair, base))
    add(_safe(_repair, region_src))
    return out


def try_literal_eval(candidate: str) -> dict[str, Any] | None:
    try:
        parsed = ast.literal_eval(candidate)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _load_object(text: str) -> dict[str, Any] | None:
    for candidate in _candidates(text):
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    # ast.literal_eval fallback (handles single-quoted dicts json can't, but only dicts)
    for candidate in _candidates(text):
        obj = try_literal_eval(candidate)
        if obj is not None:
            return obj
    return None


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse one JSON object from model output, repairing common breakage.

    Field-agnostic: callers that require a specific key (e.g. 'action' or
    'decision') validate it themselves. Raises JsonGateError when no object can
    be recovered.
    """
    raw = strip_bom(text or "")
    obj = _load_object(raw)
    if obj is None:
        raise JsonGateError("Could not parse a JSON object from model output.", candidate=raw[:200])
    return obj


# Control verbs the loop dispatches on; anything else in 'action' is a misplaced tool name.
_CONTROL_VERBS = frozenset({"tool", "final", "delegate"})
# Envelope keys that are NEVER tool args — everything else at the top level of a tool call is.
_ENVELOPE_KEYS = frozenset(
    {"action", "tool", "name", "args", "finish_reason", "message", "target", "spec",
     "policy", "thought", "reasoning", "thinking", "observation"}
)


def normalize_action(obj: dict[str, Any]) -> dict[str, Any]:
    """Coerce the action shapes local models actually emit into the canonical envelope.

    Three observed breakages, all of which parse as valid JSON yet leave the loop unable to
    dispatch (so it wastes the parse-error / step budget or fails outright):

      (a) tool params flattened to the TOP LEVEL instead of nested under 'args' —
          ``{"action":"tool","tool":"fs_write","path":"x","content":"y"}``  → args was {} → wrote to the dir.
      (b) the tool NAME used as the 'action' value —
          ``{"action":"fs_write","path":"x"}``                              → verb wasn't 'tool' → "unknown action".
      (c) 'args' delivered as a JSON STRING instead of an object —
          ``{"action":"tool","tool":"X","args":"{\\"path\\":\\"x\\"}"}``     → not a dict → dropped.

    Canonical envelopes are returned untouched (the common case stays a no-op)."""
    if not isinstance(obj, dict):
        return obj
    out = dict(obj)
    action = out.get("action")
    tool = out.get("tool") or out.get("name")

    # (b) action carries a non-control verb, there's no explicit tool, it isn't a final
    # (no 'message'), and there ARE leftover param keys → the action value IS the tool name.
    if (
        isinstance(action, str)
        and action not in _CONTROL_VERBS
        and tool is None
        and "message" not in out
        and any(k not in _ENVELOPE_KEYS for k in out)
    ):
        tool = action
        out["action"] = "tool"

    if tool is not None and not out.get("tool"):
        out["tool"] = tool

    if out.get("action") == "tool":
        args = out.get("args")
        # (c) args double-encoded as a JSON string → decode to an object.
        if isinstance(args, str):
            try:
                decoded = json.loads(args)
            except (json.JSONDecodeError, ValueError):
                decoded = None
            if isinstance(decoded, dict):
                out["args"] = args = decoded
        # (a) no usable args object → gather the leftover top-level keys into args.
        if not isinstance(args, dict) or not args:
            leftover = {k: v for k, v in out.items() if k not in _ENVELOPE_KEYS}
            if leftover:
                out["args"] = leftover
                for key in leftover:
                    out.pop(key, None)
    return out


def parse_action(text: str) -> dict[str, Any]:
    """Parse one JSON action object from model output, repairing common breakage."""
    obj = normalize_action(parse_json_object(text))
    if "action" not in obj:
        raise JsonGateError("Missing required 'action' field.", stage="schema", candidate=str(obj)[:200])
    return obj


def build_retry_message(error: JsonGateError) -> str:
    """A corrective re-prompt that shows the model the exact shape to copy. A local model recovers
    far better from a concrete skeleton than from an abstract 'return a valid action' instruction."""
    return (
        f"PARSE ERROR (stage={error.stage}): your last message was not a single valid JSON action.\n"
        "Reply with EXACTLY ONE JSON object — no prose, no markdown fences, no comments, no trailing text.\n"
        "Use one of these shapes:\n"
        '  {"action":"tool","tool":"<exact_tool_name>","args":{...}}\n'
        '  {"action":"final","message":"<your answer>","finish_reason":"done"}\n'
        "Your reply must start with { and end with }."
    )
