"""Anti-pattern: SWALLOWING EXCEPTIONS (nuốt ngoại lệ) — distill từ hex_agent.

NGUỒN THẬT (đã mở file kiểm chứng):
  - discipline/json_gate.py:338-343  -> _safe(fn, text): bắt MỌI Exception, trả None,
                                        KHÔNG log một dòng nào ("swallowing any failure
                                        so the gate never leaks").
  - discipline/json_gate.py:373-378  -> try_literal_eval(candidate): bắt Exception khi
                                        ast.literal_eval thất bại, trả None lặng lẽ.
  - discipline/json_gate.py:346-370  -> _candidates(raw): xây "thang" candidate, mỗi rule
                                        bọc trong _safe().
  - discipline/json_gate.py:381-394  -> _load_object(text): lặp qua candidates, ai parse
                                        ra dict thì trả; caller KHÔNG biết rule nào hỏng /
                                        rule nào chưa từng được gọi tới.

BỆNH LÝ NÃO (Lesson 33, mục 1.3.b — Loss of insulation): demyelination trong Multiple
Sclerosis làm action potential propagate sai/chậm. Ở đây "tín hiệu" bị mất chính là
NGỮ CẢNH LỖI: vì sao một repair rule thất bại biến mất hoàn toàn.

Ý TƯỞNG ĐỐI CHỨNG: khi nuốt ngoại lệ, người debug không phân biệt được:
  (A) "rule X đã chạy và thất bại" vs (B) "rule X chưa bao giờ được gọi tới".
Cả hai đều biểu hiện y hệt: candidate không xuất hiện trong danh sách. Bản distill này
chứng minh điều đó bằng hai phiên bản pipeline: bản NUỐT (giống code thật) và bản
QUAN SÁT ĐƯỢC (có ghi lại diễn biến từng rule).

CHỈ DÙNG STDLIB. Hạ tầng nặng được lược bỏ: không có LLM, không openai; "output của model"
chỉ là vài chuỗi JSON bẩn hard-code. Logic repair được rút gọn còn 3 rule tượng trưng,
giữ đúng VAI TRÒ: rule thuần str->str, có thể ném lỗi, được bọc trong _safe().
"""
from __future__ import annotations

import json
from typing import Any, Callable, Optional


# ── 3 "repair rule" tượng trưng (str -> str), giữ đúng vai trò code thật ──────────
# Trong json_gate.py thật có ~9 rule (strip_bom, strip_markdown_fence, ...). Ở đây rút
# gọn còn 3, trong đó có rule CỐ TÌNH ném lỗi ở vài input để mô phỏng "repair có thể fail".


def strip_fence(text: str) -> str:
    """Bỏ rào markdown ```...``` quanh JSON. Thuần, không bao giờ ném."""
    t = text.strip()
    if t.startswith("```"):
        t = t.lstrip("`").lstrip("json").lstrip("JSON").strip()
        if t.endswith("```"):
            t = t[:-3].strip()
    return t


def quote_unquoted_keys(text: str) -> str:
    """Bọc khóa trần {a: 1} -> {"a": 1}. Rule này CÓ THỂ ném nếu input quá ngắn."""
    # Lỗi cố tình: trên chuỗi rỗng/quá ngắn, một rule "thật" đôi khi giả định cấu trúc.
    if len(text) < 2:
        raise ValueError("input too short to locate a key boundary")
    out = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in "{," and i + 1 < len(text):
            out.append(ch)
            i += 1
            j = i
            while j < len(text) and (text[j].isalnum() or text[j] == "_" or text[j].isspace()):
                j += 1
            seg = text[i:j]
            stripped = seg.strip()
            if stripped.isidentifier() and j < len(text) and text[j] == ":":
                out.append(seg.replace(stripped, f'"{stripped}"', 1))
                i = j
                continue
            out.append(seg)
            i = j
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def balance_braces(text: str) -> str:
    """Đóng nốt dấu ngoặc còn treo. Rule này CÓ THỂ ném khi mất cân bằng quá nặng."""
    opens = text.count("{") - text.count("}")
    if opens < 0:
        # nhiều } hơn { => không biết phải làm gì, mô phỏng một repair "vỡ".
        raise ValueError("more closing braces than opening; cannot balance")
    return text + "}" * opens


REPAIR_RULES: list[Callable[[str], str]] = [strip_fence, quote_unquoted_keys, balance_braces]


# ════════════════════════════════════════════════════════════════════════════════
# PHIÊN BẢN "XẤU" — nuốt ngoại lệ, giống hệt discipline/json_gate.py:338-343
# ════════════════════════════════════════════════════════════════════════════════


def _safe_swallow(fn: Callable[[str], str], text: str) -> Optional[str]:
    """Distill discipline/json_gate.py:338-343.

    try: return fn(text)
    except Exception: return None      <-- KHÔNG log, ngữ cảnh lỗi bốc hơi.
    """
    try:
        return fn(text)
    except Exception:
        return None


def try_literal_eval_swallow(candidate: str) -> Optional[dict[str, Any]]:
    """Distill discipline/json_gate.py:373-378 — nuốt lỗi của literal_eval."""
    try:
        # Trong code thật là ast.literal_eval; ở đây json.loads cho đơn giản (stdlib).
        parsed = json.loads(candidate)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def load_object_swallow(raw: str) -> Optional[dict[str, Any]]:
    """Distill _candidates()+_load_object(): lặp candidate, nuốt mọi lỗi, im lặng."""
    candidates: list[str] = []
    base = raw.strip()
    candidates.append(base)
    for rule in REPAIR_RULES:
        result = _safe_swallow(rule, base)  # <-- lỗi rule biến mất ở đây
        if result is not None and result not in candidates:
            candidates.append(result)
    for cand in candidates:
        obj = try_literal_eval_swallow(cand)
        if obj is not None:
            return obj
    return None  # caller chỉ biết "thất bại", KHÔNG biết vì sao / ở đâu.


# ════════════════════════════════════════════════════════════════════════════════
# PHIÊN BẢN "TỐT" — quan sát được: cùng hành vi recovery, nhưng GHI LẠI ngữ cảnh lỗi
# ════════════════════════════════════════════════════════════════════════════════


class RepairTrace:
    """Bản ghi diễn biến: rule nào chạy, hỏng vì sao, hay bị bỏ qua. Đây chính là
    'lớp myelin' đã thiếu trong bản nuốt ngoại lệ — tín hiệu lỗi được giữ lại."""

    def __init__(self) -> None:
        self.entries: list[dict[str, str]] = []

    def record(self, rule: str, status: str, detail: str = "") -> None:
        self.entries.append({"rule": rule, "status": status, "detail": detail})

    def attempted(self, rule: str) -> bool:
        return any(e["rule"] == rule for e in self.entries)

    def failed(self, rule: str) -> bool:
        return any(e["rule"] == rule and e["status"] == "failed" for e in self.entries)

    def render(self) -> str:
        return "\n".join(
            f"    - {e['rule']}: {e['status']}" + (f" ({e['detail']})" if e["detail"] else "")
            for e in self.entries
        )


def _safe_traced(fn: Callable[[str], str], text: str, trace: RepairTrace) -> Optional[str]:
    """Cùng vai trò _safe nhưng KHÔNG nuốt câm: ghi lại rule + lý do thất bại."""
    try:
        out = fn(text)
        trace.record(fn.__name__, "ok")
        return out
    except Exception as exc:
        # Lớp insulation: giữ lại loại lỗi + thông điệp, thay vì để nó bốc hơi.
        trace.record(fn.__name__, "failed", f"{type(exc).__name__}: {exc}")
        return None


def load_object_traced(raw: str, trace: RepairTrace) -> Optional[dict[str, Any]]:
    """Cùng thuật toán recovery như bản nuốt, nhưng diễn biến được quan sát được."""
    candidates: list[str] = []
    base = raw.strip()
    candidates.append(base)
    for rule in REPAIR_RULES:
        result = _safe_traced(rule, base, trace)
        if result is not None and result not in candidates:
            candidates.append(result)
    for cand in candidates:
        try:
            parsed = json.loads(cand)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


# ── narration helpers ────────────────────────────────────────────────────────────


def demo() -> None:
    print("=" * 76)
    print("CASE 01 — SWALLOWING EXCEPTIONS trong pipeline repair JSON (json_gate.py)")
    print("=" * 76)

    # Input bẩn: chuỗi RỖNG. Cả 3 rule đều ĐƯỢC CHẠY trên base "" (tuần tự, độc lập):
    # quote_unquoted_keys() NÉM ('input too short'), còn strip_fence() và balance_braces()
    # chạy ok (output 'balance_braces: ok'). Điểm mấu chốt cần minh hoạ: rule NÉM lỗi thì
    # bản nuốt chỉ thấy None, còn bản trace ghi rõ rule nào đã thử và thất bại vì sao.
    dirty = ""  # model trả về rỗng — một thất bại rất thật khi local LLM treo socket.

    print("\n[INPUT] Output 'model' trả về (rỗng — local LLM treo socket):", repr(dirty))

    print("\n--- (A) Bản NUỐT ngoại lệ (giống json_gate.py:338-343) ---")
    result_bad = load_object_swallow(dirty)
    print("    Kết quả:", result_bad)
    print("    Người debug thấy gì? CHỈ MỖI 'None'. Không biết:")
    print("      * quote_unquoted_keys đã chạy và NÉM 'input too short'? hay")
    print("      * nó chưa bao giờ được gọi tới?")
    print("    => Mù debug. Đây là 'loss of insulation' — ngữ cảnh lỗi bốc hơi.")

    print("\n--- (B) Bản QUAN SÁT ĐƯỢC (giữ lại trace) ---")
    trace = RepairTrace()
    result_good = load_object_traced(dirty, trace)
    print("    Kết quả:", result_good, "(cùng kết quả recovery như bản (A))")
    print("    Nhưng diễn biến giờ NHÌN THẤY được:")
    print(trace.render())
    print("    => Biết NGAY: quote_unquoted_keys đã được thử và thất bại vì input rỗng.")

    # ── Chứng minh đúng đắn bằng assert ──────────────────────────────────────────
    # 1. Hai pipeline cho cùng KẾT QUẢ recovery (distill trung thực: không đổi hành vi).
    assert result_bad == result_good, "Bản trace phải giữ nguyên hành vi recovery"

    # 2. Bất biến của anti-pattern: bản nuốt KHÔNG để lại bất kỳ ngữ cảnh nào để hỏi.
    #    Bản trace thì PHÂN BIỆT ĐƯỢC 'failed' với 'never attempted'.
    assert trace.attempted("quote_unquoted_keys"), "trace phải biết rule đã được thử"
    assert trace.failed("quote_unquoted_keys"), "trace phải biết rule đã thất bại"

    # 3. Đối chứng: với input rỗng, JSON hợp lệ thì không cần repair nào ném lỗi.
    trace_ok = RepairTrace()
    good_obj = load_object_traced('{"action": "final"}', trace_ok)
    print("\n[KIỂM CHỨNG] JSON hợp lệ '{\"action\": \"final\"}' ->", good_obj)
    assert good_obj == {"action": "final"}, "JSON hợp lệ phải parse nguyên vẹn"
    assert not trace_ok.failed("balance_braces"), "JSON hợp lệ không gây fail rule nào"

    print("\n[OK] Mọi assert qua. Bài học: bắt Exception thì PHẢI để lại dấu vết.")
    print("     'except: return None' không log = demyelination của codebase.")
    print("=" * 76)


if __name__ == "__main__":
    demo()
