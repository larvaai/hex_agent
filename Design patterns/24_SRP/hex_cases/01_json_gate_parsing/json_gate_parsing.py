"""
SRP case 01 — JSON Output Repair Pipeline (chỉ phục vụ Validation/JSON-gate team).

Distill TRUNG THỰC từ codebase hex_agent:
  - discipline/json_gate.py:1-494   (toàn bộ module repair)
      * strip_bom            -> json_gate.py:31-32
      * strip_markdown_fence -> json_gate.py:35-40
      * remove_trailing_commas -> json_gate.py:86-87
      * replace_python_literals (+ _replace_identifiers_outside_strings)
                             -> json_gate.py:90-126
      * quote_unquoted_keys  -> json_gate.py:129-178
      * balance_trailing_delimiters -> json_gate.py:277-302
      * light_json_repair (ladder) -> json_gate.py:305-317
      * _candidates (thang nến) -> json_gate.py:346-370
      * _load_object / parse_json_object -> json_gate.py:381-408
      * try_literal_eval     -> json_gate.py:373-378
      * parse_action / normalize_action -> json_gate.py:420-480
      * JsonGateError (kèm stage) -> json_gate.py:21-25

Ý NGHĨA SRP (Single Responsibility Principle):
  Module này chỉ có MỘT actor: đội Validation/JSON-gate. Lý do duy nhất để đổi nó là
  "model local lại đẻ ra một kiểu JSON hỏng mới". Nó KHÔNG đụng database, KHÔNG emit event,
  KHÔNG cache, KHÔNG biết business logic. Mọi hàm đều thuần str->str (pure), test không cần mock.

Bản distill này:
  - GIỮ NGUYÊN vai trò pattern: Validator + ErrorReporter + PipelineOrchestrator + Loader.
  - Chỉ dùng thư viện chuẩn (json, ast, re). KHÔNG import hex_agent, KHÔNG thư viện ngoài.
  - LƯỢC BỎ các luật ít phổ biến hơn (escape_control_chars, convert_single_quoted_values,
    extract_largest_json_region) để bài gọn — nhưng giữ đủ thang nến để chứng minh
    "raw luôn là ứng viên #1, JSON hợp lệ không bao giờ bị repair làm hỏng".
"""
from __future__ import annotations

import ast
import json
import re
from typing import Any, Callable


# ── VAI: ErrorReporter ────────────────────────────────────────────────────────
# Lỗi mang theo metadata 'stage' để biết hỏng ở chặng parse hay schema.
class JsonGateError(ValueError):
    def __init__(self, message: str, *, stage: str = "parse", candidate: str = "") -> None:
        super().__init__(message)
        self.stage = stage
        self.candidate = candidate


# ── VAI: Validator — các luật repair THUẦN str -> str ────────────────────────
# Mỗi luật là một total function: nhận text bất kỳ, trả text. Không ngoại lệ rò ra ngoài.

def strip_bom(text: str) -> str:
    return (text or "").lstrip("﻿").strip()


def strip_markdown_fence(text: str) -> str:
    """Lấy nội dung khối ```...``` đầu tiên; nếu không có thì trả nguyên text."""
    match = re.search(r"```(?:json|JSON)?\s*(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def remove_trailing_commas(text: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", text)


def _replace_identifiers_outside_strings(text: str, replacements: dict[str, str]) -> str:
    """Thay định danh (True/False/None) NHƯNG bỏ qua phần nằm trong chuỗi "..."."""
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
    return _replace_identifiers_outside_strings(
        text, {"True": "true", "False": "false", "None": "null"}
    )


def quote_unquoted_keys(text: str) -> str:
    """Bọc key trần ({key: ...} -> {"key": ...}) nằm ngoài chuỗi."""
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


def balance_trailing_delimiters(text: str) -> str:
    """Đóng các ngoặc {[ còn treo ở cuối (model bị cắt giữa chừng)."""
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


# ── VAI: PipelineOrchestrator — thang repair quyết định (deterministic) ───────
def light_json_repair(text: str) -> str:
    """Áp toàn bộ pipeline repair. Total trên text bất kỳ."""
    repaired = strip_bom(text)
    repaired = strip_markdown_fence(repaired)
    repaired = remove_trailing_commas(repaired)
    repaired = replace_python_literals(repaired)
    repaired = quote_unquoted_keys(repaired)
    repaired = balance_trailing_delimiters(repaired)
    return repaired.strip()


def _safe(fn: Callable[[str], str], text: str) -> str | None:
    """Áp một luật, nuốt mọi lỗi để gate không bao giờ rò exception."""
    try:
        return fn(text)
    except Exception:
        return None


def _candidates(raw: str) -> list[str]:
    """Danh sách ứng viên có thứ tự, khử trùng lặp — RAW đầu tiên, mạnh tay nhất cuối."""
    out: list[str] = []
    seen: set[str] = set()

    def add(value: str | None) -> None:
        if value is None or value in seen:
            return
        seen.add(value)
        out.append(value)

    base = strip_bom(raw)
    add(base)                                   # #1: RAW — JSON hợp lệ được giữ nguyên
    add(_safe(strip_markdown_fence, base))      # #2: bóc markdown fence
    add(_safe(light_json_repair, base))         # #3: full pipeline (mạnh tay)
    return out


# ── VAI: Loader — điểm vào công khai ──────────────────────────────────────────
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
    for candidate in _candidates(text):   # fallback: dict single-quote mà json không nuốt được
        obj = try_literal_eval(candidate)
        if obj is not None:
            return obj
    return None


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse một JSON object từ output model, tự repair các kiểu hỏng phổ biến."""
    raw = strip_bom(text or "")
    obj = _load_object(raw)
    if obj is None:
        raise JsonGateError("Không parse được JSON object từ output model.", candidate=raw[:200])
    return obj


# ============================================================================
# DEMO
# ============================================================================

def demo() -> None:
    print("=" * 72)
    print("SRP case 01 — JSON Output Repair Pipeline (discipline/json_gate.py)")
    print("Actor DUY NHẤT: đội Validation/JSON-gate. Một module, một lý do để đổi.")
    print("=" * 72)

    # 10 kiểu hỏng model local thực sự hay đẻ ra; mỗi dòng comment ghi luật nào cứu.
    cases: list[tuple[str, str]] = [
        ('{"action": "final"}',                       "RAW hợp lệ — không repair gì"),
        ('  {"action": "final"}  ',                   "thừa khoảng trắng -> strip_bom"),
        ('```json\n{"action":"tool"}\n```',           "markdown fence -> strip_markdown_fence"),
        ('{"action":"tool", "args":{"x":1},}',        "trailing comma -> remove_trailing_commas"),
        ('{"ok": True, "skip": False, "v": None}',    "literal Python -> replace_python_literals"),
        ('{action: "final", tool: "fs_write"}',       "key trần -> quote_unquoted_keys"),
        ('{"a": {"b": 1}',                             "thiếu } cuối -> balance_trailing_delimiters"),
        ('{"a": 1, "b": [2, 3',                        "thiếu ] và } cuối -> balance_trailing_delimiters"),
        ('Sure! Here you go:\n```\n{"action":"final"}\n```', "prose + fence -> bóc fence rồi parse"),
        ("{'action': 'final'}",                        "single-quote -> ast.literal_eval fallback"),
    ]

    print("\n--- Mỗi kiểu hỏng + luật repair đã cứu nó ---")
    for raw, note in cases:
        obj = parse_json_object(raw)
        assert isinstance(obj, dict), f"phải ra dict cho: {raw!r}"
        preview = repr(raw if len(raw) <= 38 else raw[:35] + "...")
        print(f"  OK  {preview:<42} -> {note}")

    # Bất biến #1: RAW là ứng viên #1, nên JSON hợp lệ KHÔNG BAO GIỜ bị repair làm méo.
    valid = '{"action": "final", "message": "xong", "n": 7}'
    assert parse_json_object(valid) == {"action": "final", "message": "xong", "n": 7}
    # Chuỗi chứa từ "True" bên trong KHÔNG bị đổi thành "true":
    keep = '{"note": "set debug=True in config"}'
    assert parse_json_object(keep) == {"note": "set debug=True in config"}
    print("\n[BẤT BIẾN] RAW là ứng viên #1 -> JSON hợp lệ không bị repair phá. PASS")
    print("[BẤT BIẾN] 'True' bên trong chuỗi không bị đổi thành 'true'. PASS")

    # Bất biến #2: ErrorReporter mang stage. Rác hoàn toàn -> JsonGateError(stage='parse').
    try:
        parse_json_object("đây không phải json gì cả !!!")
        raise AssertionError("đáng lẽ phải ném JsonGateError")
    except JsonGateError as err:
        assert err.stage == "parse"
        print(f"[ErrorReporter] rác -> JsonGateError(stage={err.stage!r}). PASS")

    # ---- ĐỐI CHỨNG: KHÔNG có pipeline repair (gọi thẳng json.loads) thì hỏng thế nào ----
    print("\n--- ĐỐI CHỨNG: không có module repair, gọi thẳng json.loads ---")
    naive_fail = 0
    for raw, note in cases:
        try:
            json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            naive_fail += 1
    print(f"  json.loads trần CHẾT {naive_fail}/{len(cases)} ca; pipeline SRP cứu hết.")
    assert naive_fail >= 6, "đối chứng phải cho thấy json.loads trần thua nhiều ca"

    print("\nKẾT: gom mọi luật repair vào 1 module 1-actor giúp đổi chiến lược repair")
    print("chỉ đụng đúng file này; không lan sang storage/network/business logic.")


if __name__ == "__main__":
    demo()
