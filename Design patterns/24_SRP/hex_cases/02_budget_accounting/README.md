# Case 02 — Loop Budget Tracker (SRP)

> Một dataclass, một actor: đội **Run-orchestration** (`orchestrator/loop.py`). Một việc:
> **đếm và gác** ngân sách vòng lặp.

---

## 1. Bối cảnh trong hex_agent

Vòng lặp agent phải dừng đúng lúc: hết step, model kẹt đẻ rác liên tục, hoặc gọi đi gọi lại
cùng một tool với cùng args. Nếu nhét các counter này rải rác trong `orchestrator/loop.py`,
chúng sẽ trộn vào điều phối LLM/tool và rất khó test.

`discipline/budget.py` (file `1-68`, đã mở kiểm chứng) gom toàn bộ việc đó vào một
`@dataclass Budget`. Reader/writer duy nhất là loop orchestrator. Nó **không** đụng
permission, **không** đụng event, **không** đụng kernel.

Một quyết định thiết kế tinh tế nằm ngay trong docstring (`budget.py:11-18`): parse-error
được gác trên **streak liên tiếp** (`consecutive_parse_errors`), KHÔNG phải tổng trọn đời.
Model lỡ tay 1 lần JSON rồi hồi phục thì chưa fail; chỉ model kẹt N lần *liên tiếp* mới bị
chặn. `parse_errors` vẫn giữ làm telemetry trọn đời.

---

## 2. Trích đoạn code thật

`discipline/budget.py:37-54` — MutationPort + QueryPort, mỗi method một dòng:

```python
    def record_step(self) -> None:
        self.steps += 1
        self.consecutive_parse_errors = 0  # a completed step proves the model recovered

    def step_exceeded(self) -> bool:
        return self.steps > self.max_steps

    def record_parse_error(self) -> None:
        self.parse_errors += 1
        self.consecutive_parse_errors += 1

    def record_parse_success(self) -> None:
        """A well-formed action arrived. Clears the consecutive-fumble streak ..."""
        self.consecutive_parse_errors = 0

    def parse_exceeded(self) -> bool:
        return self.consecutive_parse_errors >= self.max_parse_errors
```

`discipline/budget.py:28-35` — StaticFactory (điểm tiêm cấu hình không-đổi-code):

```python
    @classmethod
    def from_env(cls) -> Budget:
        """Default run budget, tunable without a code change (the IDE/orchestrator knob)."""
        return cls(
            max_steps=int(os.getenv("AGENT_MAX_STEPS", "30")),
            max_parse_errors=int(os.getenv("AGENT_MAX_PARSE_ERRORS", "8")),
            max_same_tool_calls=int(os.getenv("AGENT_MAX_SAME_TOOL", "3")),
        )
```

---

## 3. Ánh xạ vai trò pattern <-> code thật

| Vai trò (SRP) | Thành phần code thật | path:line |
|---|---|---|
| StateHolder | `max_steps`, `max_parse_errors`, `max_same_tool_calls`, `steps`, `parse_errors`, `consecutive_parse_errors`, `_tool_calls` | `budget.py:20-26` |
| StaticFactory | `from_env` | `budget.py:28-35` |
| MutationPort | `record_step`, `record_parse_error`, `record_parse_success`, `record_tool_call` | `budget.py:37-39, 44-46, 48-51, 56-58` |
| QueryPort | `step_exceeded`, `parse_exceeded`, `same_tool_exceeded` | `budget.py:41-42, 53-54, 60-61` |

> Lưu ý: mutation và query method **đan xen** nhau trong file (vd `step_exceeded` ở `41-42`
> nằm giữa `record_step` và `record_parse_error`), nên mỗi vai dùng danh sách dải dòng rời
> thay vì một dải liền — khớp chính xác với từng method trong `budget.py`.
| Key normalizer | `tool_key` (static, `sort_keys=True`) | `budget.py:63-67` |

Mọi field đều được ≥1 method dùng tới → **cohesion cao (LCOM4 = 1)**.

---

## 4. Bản rút gọn chạy được

File: [`budget_accounting.py`](./budget_accounting.py) — chạy `python3 budget_accounting.py`.

**Mô phỏng đúng:** toàn bộ cấu trúc dataclass và API; quy tắc "streak vs lifetime";
`tool_key` chuẩn-hoá args bằng `sort_keys` để hai dict cùng nội dung ra cùng key.

**Lược bỏ:** `os.getenv` thật được thay bằng tham số `env: dict` (mặc định rỗng) trong
`from_env`. Đây vẫn là đúng vai StaticFactory/điểm-tiêm-cấu-hình, nhưng chạy độc lập, không
phụ thuộc môi trường ngoài.

Demo: (1) tiêm config qua env giả; (2) đếm step tới ngưỡng; (3) streak parse-error reset bởi
`record_parse_success` nhưng lifetime giữ nguyên; (4) chống lặp tool y hệt. Có đối chứng
"nếu nhét counter vào loop thì test phải dựng cả LLM/tool giả".

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Chi phí:** một class nhỏ tách riêng nghĩa là loop phải tự gọi `record_*`/`*_exceeded`
  đúng chỗ — thêm một chút glue.
- **Khi nào KHÔNG tách:** với prototype dùng-một-lần, đặt `steps += 1` ngay trong loop là đủ.
  Tách Budget chỉ đáng khi loop đủ phức tạp và có người muốn chỉnh ngưỡng độc lập.
- **Cảnh báo over-SRP:** đừng tách tiếp `StepCounter`, `ParseCounter`, `ToolCounter` thành 3
  class — cả ba cùng phục vụ MỘT actor (loop), tách nữa là Shotgun Surgery.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `record_step` lại reset `consecutive_parse_errors` về 0? Điều gì xảy ra với một run
   "đang tiến triển" nếu gate dùng tổng trọn đời thay vì streak (xem `budget.py:11-18`)?
2. `tool_key` dùng `json.dumps(..., sort_keys=True)`. Nếu bỏ `sort_keys`, hai lời gọi
   `{"a":1,"b":2}` và `{"b":2,"a":1}` sẽ bị đếm thế nào, và `same_tool_exceeded` hỏng ra sao?
3. Budget có 7 field và 9 method nhưng vẫn tuân thủ SRP. Hãy nêu tên actor duy nhất và giải
   thích vì sao "nhiều method" không vi phạm SRP.
