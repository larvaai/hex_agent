# Case 01 — Swallowing Exceptions trong pipeline repair JSON

> **Anti-pattern**: Swallowing Exceptions (nuốt ngoại lệ).
> **Bệnh lý não (Lesson 33, mục 1.3.b)**: *Loss of insulation* — demyelination trong
> Multiple Sclerosis làm action potential propagate sai/chậm. Ở code: ngữ cảnh lỗi
> (signal) bị mất vì thiếu lớp ghi nhận (insulation).

---

## 1. Bối cảnh trong hex_agent

`hex_agent` để LLM cục bộ/open-source điều khiển một vòng lặp agent. Local model thường
trả JSON **bẩn**: rào markdown, prose thừa, dấu phẩy treo, literal Python (`True`/`None`),
khóa không bọc nháy, ký tự điều khiển trong chuỗi. File `discipline/json_gate.py` là
"cổng JSON": nó thử raw trước, rồi một *thang* candidate repair tăng dần độ mạnh, cuối
cùng là fallback `ast.literal_eval`.

Vấn đề thật nằm ở **lớp bọc lỗi** của thang đó. Hàm `_safe()` (dòng 338-343) bắt **toàn
bộ** `Exception` rồi trả `None` *không log một dòng nào* — chính docstring của nó thừa
nhận mục tiêu là "swallowing any failure so the gate never leaks". `try_literal_eval()`
(dòng 373-378) nuốt y hệt. Hậu quả: caller `_load_object()` (dòng 381-394) lặp qua các
candidate mà **không bao giờ biết** một repair rule đã *chạy rồi thất bại* hay *chưa bao
giờ được gọi tới*. Khi output của model kẹt trong vòng retry parse, thông điệp như
"extract_balanced_region timed out" hay "json.loads: unterminated string" trở nên vô hình.

File đã mở kiểm chứng: `/Users/uspro/Desktop/namnson/hex_agent/discipline/json_gate.py`,
dòng 338-343 và 373-378.

---

## 2. Trích đoạn code thật

```python
# discipline/json_gate.py:338-343
def _safe(fn: Callable[[str], str], text: str) -> str | None:
    """Apply a repair rule, swallowing any failure so the gate never leaks."""
    try:
        return fn(text)
    except Exception:
        return None
```

```python
# discipline/json_gate.py:373-378
def try_literal_eval(candidate: str) -> dict[str, Any] | None:
    try:
        parsed = ast.literal_eval(candidate)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None
```

```python
# discipline/json_gate.py:381-394 — caller mù: chỉ thấy None tổng thể
def _load_object(text: str) -> dict[str, Any] | None:
    for candidate in _candidates(text):
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    for candidate in _candidates(text):
        obj = try_literal_eval(candidate)   # <- mọi lỗi đã bị nuốt ở tầng dưới
        if obj is not None:
            return obj
    return None
```

---

## 3. Bảng ánh xạ vai trò pattern ↔ code thật

| Vai trò trong anti-pattern | Code thật (`json_gate.py`) | Bản distill (`swallowed_exceptions_json_repair.py`) |
|----------------------------|----------------------------|-----------------------------------------------------|
| Repair rule thuần `str -> str` (có thể ném) | Các hàm repair **cấp cao** được bọc trong `_safe()` (`strip_markdown_fence`, `extract_largest_json_region`, `light_json_repair`, `_repair`); riêng `light_json_repair` lại là một **chuỗi 9 bước** bên trong (gồm `quote_unquoted_keys`, `balance_trailing_delimiters`, ...) | `strip_fence`, `quote_unquoted_keys`, `balance_braces` (3 rule tượng trưng) |
| **Lớp nuốt ngoại lệ** | `_safe()` (338-343), `try_literal_eval()` (373-378) | `_safe_swallow()`, `try_literal_eval_swallow()` |
| Thang candidate + caller mù | `_candidates()` (346-370) + `_load_object()` (381-394) | `load_object_swallow()` |
| (Đối chứng) lớp ghi nhận / "myelin" | *không có trong code thật* | `RepairTrace` + `_safe_traced()` + `load_object_traced()` |

---

## 4. Bản rút gọn chạy được

File: [`swallowed_exceptions_json_repair.py`](./swallowed_exceptions_json_repair.py)
(`python3 swallowed_exceptions_json_repair.py`, chỉ stdlib).

**Mô phỏng gì**: giữ đúng *kiến trúc thang candidate* và *lớp bọc `_safe`*. Có hai
pipeline song song trên cùng input:
- `load_object_swallow()` — sao y bản nuốt ngoại lệ của code thật.
- `load_object_traced()` — cùng thuật toán recovery, nhưng `RepairTrace` ghi lại từng rule
  (ok / failed + lý do). Đây là "lớp insulation" mà code thật còn thiếu.

Đối chứng cốt lõi: với input rỗng (local LLM treo socket), bản nuốt chỉ trả `None` —
người debug *không phân biệt được* "rule đã thử và hỏng" với "rule chưa từng chạy". Bản
trace in ra ngay: `quote_unquoted_keys: failed (ValueError: input too short...)`.

**Lược bỏ gì**: không có LLM/openai/network; "output model" là chuỗi hard-code. Chuỗi 9
rule thật rút còn 3 rule tượng trưng (giữ đúng vai trò: thuần, có thể ném, được bọc trong
`_safe`). `ast.literal_eval` thay bằng `json.loads` cho gọn (vẫn cùng vai trò fallback).

Các `assert` chứng minh: (1) hai pipeline cho **cùng** kết quả recovery (distill trung
thực, không đổi hành vi); (2) chỉ bản trace mới phân biệt được `failed` vs `attempted`;
(3) JSON hợp lệ vẫn parse nguyên vẹn, không rule nào hỏng.

---

## 5. Cái giá / khi nào KHÔNG nên sửa

**Cái giá của việc nuốt ngoại lệ**:
- **Mù debug khi sự cố**: lỗi production "agent kẹt retry parse" mất hết manh mối — đúng
  lúc cần thông tin nhất thì thông tin đã bốc hơi.
- **Che giấu lỗi không lường trước**: `except Exception` bắt cả những lỗi *không* phải
  "JSON hỏng bình thường" (vd: `RecursionError`, `MemoryError`, bug lập trình trong rule).
  Chúng bị nuốt thành `None` như thể chỉ là input bẩn.
- **Ngăn cải tiến**: không ai biết rule nào hay hỏng nhất → không biết nên gia cố rule nào.

**Khi nào việc này *chấp nhận được* (không phải lúc nào cũng phải sửa)**:
- Khi *bản chất* là "thử nhiều cách, cái nào trúng thì lấy" và mỗi lần fail là **chuyện
  thường, vô hại** — đúng tinh thần "the gate never leaks": cổng JSON *không được* ném ra
  ngoài giữa chừng. Quyết định kiến trúc "không leak" là hợp lý.
- Cách *cân bằng đúng* không phải bỏ `_safe`, mà là **giữ không-leak + thêm quan sát**:
  log ở mức `debug`/`trace` (rule nào, lỗi gì), hoặc tích luỹ vào một bản ghi như
  `RepairTrace` rồi đính kèm `candidate` vào `JsonGateError` khi *toàn bộ* candidate đều
  hỏng. Lưu ý: `JsonGateError` đã có sẵn field `stage` và `candidate` — hạ tầng để giữ
  ngữ cảnh đã có, chỉ là tầng `_safe` chưa tận dụng.
- Đừng bắt `Exception` rộng nếu có thể bắt hẹp (`json.JSONDecodeError`, `ValueError`):
  để lỗi lập trình thật vẫn nổ lên.

---

## 6. Câu hỏi tự kiểm tra

1. Với output rỗng từ model, hàm `_safe()` thật trả về gì, và caller `_load_object()` có
   cách nào biết *rule nào* đã thất bại không? (Gợi ý: chạy file `.py`, so cột (A) và (B).)
2. Anti-pattern này map vào bệnh lý não nào trong Lesson 33, và "tín hiệu bị mất" tương
   ứng với khái niệm code nào?
3. `JsonGateError` đã có sẵn `stage` và `candidate`. Bạn sẽ sửa `_safe`/`_load_object`
   thế nào để giữ nguyên tính "never leak" mà vẫn không mù debug? (Nêu 2 cách: log mức
   debug vs tích luỹ trace.)
