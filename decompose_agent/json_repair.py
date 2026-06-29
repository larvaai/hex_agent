"""Parse + repair the model's JSON, raising JsonGateError on failure.

Deterministic-first ladder ported from discipline/json_gate.py:305-394 — it tries the raw
text unchanged, then increasingly aggressive but still pure ``str -> str`` repairs, then an
``ast.literal_eval`` fallback. Valid JSON is recovered by the *first* (raw) candidate, so a
well-formed object is never mutated.

Two call types, two recoveries:
  * ``propose`` → an action object (``parse_action`` + ``normalize_action``, json_gate.py:420-472).
  * ``decompose`` → a children LIST (``parse_children``), since the worker emits a JSON array.

Every repair rule swallows its own exception, so the ladder is total over arbitrary bytes.
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


def _repair(candidate: str) -> str:
    return balance_trailing_delimiters(remove_trailing_commas(candidate))


# ── candidate ladder + load ──────────────────────────────────────────────────


def _safe(fn: Callable[[str], str], text: str) -> str | None:
    """Apply a repair rule, swallowing any failure so the ladder never leaks."""
    try:
        return fn(text)
    except Exception:
        return None


def _candidates(raw: str) -> list[str]:
    """Ordered, de-duplicated repair candidates — raw first, most aggressive last."""
    out: list[str] = []
    seen: set[str] = set()

    def add(value: str | None) -> None:
        if value is None or value in seen:
            return
        seen.add(value)
        out.append(value)

    base = strip_bom(raw)
    add(base)
    fenced = _safe(strip_markdown_fence, base)
    add(fenced)
    # Repair WHOLE text without region-extraction first: closes a truncated outer object
    # ('{"a": {"b": 1}') instead of prematurely returning the balanced inner object.
    add(_safe(lambda t: light_json_repair(t, extract_region=False), base))
    region_src = fenced if fenced is not None else base
    add(_safe(extract_largest_json_region, region_src))
    add(_safe(light_json_repair, base))
    add(_safe(_repair, region_src))
    return out


def _load_any(text: str) -> Any | None:
    """Recover a dict OR a list — json.loads first, then ast.literal_eval."""
    for candidate in _candidates(text):
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            parsed = None
        if isinstance(parsed, (dict, list)):
            return parsed
    for candidate in _candidates(text):
        try:
            parsed = ast.literal_eval(candidate)
        except Exception:
            continue
        if isinstance(parsed, (dict, list)):
            return parsed
    return None


def parse_object(text: str) -> dict[str, Any]:
    """Parse one JSON object from model output, repairing common breakage.

    Field-agnostic: callers needing a specific key validate it themselves. Raises
    JsonGateError when no object can be recovered.
    """
    raw = strip_bom(text or "")
    obj = _load_any(raw)
    if not isinstance(obj, dict):
        raise JsonGateError("Could not parse a JSON object from model output.", candidate=raw[:200])
    return obj


# Control verbs the loop dispatches on; anything else in 'action' is a misplaced tool name.
_CONTROL_VERBS = frozenset({"tool", "final", "delegate"})
_ENVELOPE_KEYS = frozenset(
    {"action", "tool", "name", "args", "finish_reason", "message", "target", "spec",
     "policy", "thought", "reasoning", "thinking", "observation"}
)


def normalize_action(obj: dict[str, Any]) -> dict[str, Any]:
    """Coerce the action shapes local models actually emit into the canonical envelope.

    Three observed breakages, all valid JSON yet undispatchable:
      (a) tool params flattened to the TOP LEVEL instead of nested under 'args';
      (b) the tool NAME used as the 'action' value;
      (c) 'args' delivered as a JSON STRING instead of an object.
    Canonical envelopes pass through untouched.
    """
    if not isinstance(obj, dict):
        return obj
    out = dict(obj)
    action = out.get("action")
    tool = out.get("tool") or out.get("name")

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
        if isinstance(args, str):
            try:
                decoded = json.loads(args)
            except (json.JSONDecodeError, ValueError):
                decoded = None
            if isinstance(decoded, dict):
                out["args"] = args = decoded
        if not isinstance(args, dict) or not args:
            leftover = {k: v for k, v in out.items() if k not in _ENVELOPE_KEYS}
            if leftover:
                out["args"] = leftover
                for key in leftover:
                    out.pop(key, None)
    return out


def parse_action(text: str) -> dict[str, Any]:
    """Parse one JSON action object (propose call), repairing common breakage."""
    obj = normalize_action(parse_object(text))
    if "action" not in obj:
        raise JsonGateError("Missing required 'action' field.", stage="schema", candidate=str(obj)[:200])
    return obj


def parse_children(text: str) -> list[dict[str, Any]]:
    """Parse a children LIST (decompose call). Accepts a bare array or a `{children:[...]}`
    / `{nodes:[...]}` wrapper. Raises JsonGateError when no list can be recovered."""
    obj = _load_any(strip_bom(text or ""))
    if isinstance(obj, list):
        items = obj
    elif isinstance(obj, dict):
        items = obj.get("children") or obj.get("nodes") or []
    else:
        raise JsonGateError("Could not parse a children list from model output.", candidate=(text or "")[:200])
    if not isinstance(items, list):
        raise JsonGateError("Decompose output was not a list of children.", stage="schema")
    return [item for item in items if isinstance(item, dict)]


_PROPOSE_SKELETON = (
    "PARSE ERROR (stage={stage}): your last message was not a single valid JSON action.\n"
    "Reply with EXACTLY ONE JSON object — no prose, no markdown fences, no trailing text.\n"
    "Use one of these shapes:\n"
    '  {{"action":"tool","tool":"<exact_tool_name>","args":{{...}}}}\n'
    '  {{"action":"final","message":"<your answer>","finish_reason":"done"}}\n'
    "Your reply must start with {{ and end with }}."
)

_DECOMPOSE_SKELETON = (
    "PARSE ERROR (stage={stage}): your last message was not a valid JSON list of child nodes.\n"
    "Reply with EXACTLY ONE JSON array — no prose, no markdown fences, no trailing text.\n"
    "Each element is a child node:\n"
    '  [{{"id":"<child_id>","depends_on":[],'
    '"done_when":[{{"check":"<check>","params":{{...}},"artifact":"<relative/path>"}}]}}]\n'
    "Your reply must start with [ and end with ]."
)


def build_retry_message(call_type: str = "propose", *, stage: str = "parse") -> str:
    """A corrective re-prompt that shows the model the exact shape to copy — by call type.
    A local model recovers far better from a concrete skeleton than from an abstract instruction.
    Embeds a literal skeleton only; never re-dumps the context."""
    skeleton = _DECOMPOSE_SKELETON if call_type == "decompose" else _PROPOSE_SKELETON
    return skeleton.format(stage=stage)
