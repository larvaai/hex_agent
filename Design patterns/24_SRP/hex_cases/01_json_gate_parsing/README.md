# Case 01 — JSON Output Repair Pipeline (SRP)

> Một module, một actor: đội **Validation/JSON-gate**. Lý do duy nhất để đổi nó là
> "model local lại đẻ ra một kiểu JSON hỏng mới".

---

## 1. Bối cảnh trong hex_agent

Agent loop chạy với LLM local/open. Những model này thường KHÔNG trả JSON sạch:
chúng bọc trong markdown fence, kèm prose dẫn dắt, để trailing comma, dùng literal
Python (`True`/`False`/`None`), key trần không bọc nháy, hay bị cắt giữa chừng làm
treo ngoặc. Nếu gọi thẳng `json.loads`, loop sẽ liên tục báo parse-error và đốt sạch
ngân sách.

`discipline/json_gate.py` (file `1-494`, đã mở kiểm chứng) là một module **chỉ làm
một việc**: nhận text bất kỳ từ model, áp một **thang nến (candidate ladder)** các luật
repair thuần `str -> str`, rồi cố `json.loads` từng ứng viên — RAW trước, mạnh tay sau.
Module này không đụng database, không emit event, không cache, không biết business logic.

Điểm mấu chốt SRP: vì raw luôn là ứng viên #1 nên **JSON hợp lệ không bao giờ bị một luật
repair làm méo** (`json_gate.py:1-12` ghi rõ doctrine "deterministic-first").

---

## 2. Trích đoạn code thật

`discipline/json_gate.py:305-317` — PipelineOrchestrator (thang repair quyết định):

```python
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
```

`discipline/json_gate.py:21-25` — ErrorReporter mang metadata `stage`:

```python
class JsonGateError(ValueError):
    def __init__(self, message: str, *, stage: str = "parse", candidate: str = "") -> None:
        super().__init__(message)
        self.stage = stage
        self.candidate = candidate
```

---

## 3. Ánh xạ vai trò pattern <-> code thật

| Vai trò (SRP) | Thành phần code thật | path:line |
|---|---|---|
| Validator (các luật repair thuần) | `strip_bom`, `strip_markdown_fence`, `remove_trailing_commas`, `replace_python_literals`, `quote_unquoted_keys`, `balance_trailing_delimiters` | `json_gate.py:31-302` |
| ErrorReporter | `JsonGateError` (kèm `stage`/`candidate`) | `json_gate.py:21-25` |
| PipelineOrchestrator | `light_json_repair` (áp ladder theo thứ tự) | `json_gate.py:305-317` |
| Candidate ladder manager | `_candidates` (raw đầu, aggressive cuối, khử trùng) | `json_gate.py:346-370` |
| Loader (điểm vào công khai) | `parse_json_object`, `parse_action`, `try_literal_eval` | `json_gate.py:373-480` |

Tất cả các vai đều phục vụ **đúng một actor**: đội Validation/JSON-gate.

---

## 4. Bản rút gọn chạy được

File: [`json_gate_parsing.py`](./json_gate_parsing.py) — chạy `python3 json_gate_parsing.py`.

**Mô phỏng đúng:** thang nến (`_candidates`: raw -> bóc fence -> full pipeline),
các luật repair thuần `str -> str`, `JsonGateError` mang `stage`, và bộ loader
`parse_json_object` với fallback `ast.literal_eval` cho dict single-quote.

**Lược bỏ (để bài gọn, có ghi trong docstring):**
- `extract_largest_json_region` — bóc vùng `{...}` lớn nhất khỏi text nhiễu nặng.
- `escape_control_chars_in_strings`, `convert_single_quoted_values` — hai luật ít gặp hơn.
- `normalize_action` / `parse_action` — chuẩn hoá envelope action (đây là tầng schema, không
  phải tầng parse).

Demo cho 10 kiểu hỏng thực tế, mỗi kiểu kèm tên luật đã cứu nó; có assert bất biến
"RAW là ứng viên #1 nên JSON hợp lệ không bị phá" và đối chứng `json.loads` trần chết 8/10 ca.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Chi phí:** module 494 dòng, ~24 hàm top-level (26 nếu tính cả 2 def lồng). Với một service chỉ nhận JSON từ API nội bộ
  **luôn hợp lệ**, cả thang repair này là thừa — chỉ cần `json.loads`. SRP không bắt bạn
  tách khi không có actor "model lỗi" nào tồn tại.
- **Cẩn trọng:** repair quá mạnh tay có thể "sửa" một input thực ra nên bị từ chối. Doctrine
  raw-first chính là để giảm rủi ro này; đừng đảo thứ tự ladder.
- **Đừng** trộn validate schema (key `action` có hay không) vào tầng parse — đó là actor
  khác (xem `stage="schema"` trong `parse_action`, `json_gate.py:475-480`).

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao raw text PHẢI là ứng viên #1 trong `_candidates`? Điều gì hỏng nếu ta áp
   `light_json_repair` trước khi thử raw?
2. `_replace_identifiers_outside_strings` cần biết "đang ở trong chuỗi hay không". Nếu bỏ
   việc theo dõi `in_string`, một payload `{"note": "set True"}` sẽ bị biến đổi sai ra sao?
3. `JsonGateError.stage` có hai giá trị `"parse"` và `"schema"`. Hai giá trị này ứng với hai
   "trách nhiệm con" nào, và vì sao chúng vẫn thuộc cùng MỘT actor?
