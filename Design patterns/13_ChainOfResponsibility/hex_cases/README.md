# Chain of Responsibility trong hex_agent — Hex Cases

> **Một câu chốt:** *Một request đi qua một chuỗi handler; mỗi handler có quyền **handle** (kết thúc), **forward** (chuyển tiếp), hoặc **modulate + forward** — sender KHÔNG biết handler nào sẽ xử lý.*

Thư mục này distill cách hex_agent hiện thực **Chain of Responsibility (Behavioral)** thành các case học được, mỗi case có một bản code self-contained chạy bằng `python3` chỉ với thư viện chuẩn.

---

## Pattern xuất hiện ở đâu trong hex_agent?

hex_agent hiện thực CoR qua **hệ middleware** bao quanh một chokepoint duy nhất: `AgentKernel.execute_tool`. Mỗi middleware nhận `(request, nxt)` — với `nxt` là handler kế tiếp trong chuỗi. Một middleware có thể:

- **xử lý trước/sau** rồi gọi `nxt` (telemetry, timing),
- **short-circuit** bằng cách return mà KHÔNG gọi `nxt` (policy gate, budget guard),
- **modulate** result rồi forward (condense), hoặc
- **gọi lại `nxt` nhiều lần** (retry).

Chuỗi được **dựng động lúc kernel khởi tạo**, thứ tự giữ theo lúc đăng ký (outer → inner). Cách này decouple sender khỏi receiver, hỗ trợ early-termination, late-binding và hai tư thế lỗi fail-open / fail-closed.

### Bản đồ vai trò CoR ↔ hex_agent

| Vai trò CoR | hex_agent |
|---|---|
| `Handler` (interface) | `ToolMiddleware` Protocol — `core/middleware.py:11-22` |
| `ConcreteHandler` | `PolicyGate`, `Retry`, `CondenseResult`, `TimingLog`, `BudgetGuard` |
| `next` (handler kế tiếp) | tham số `nxt: ToolHandler` |
| `set_next` (chain builder) | `_wrap(...)` — `core/kernel.py:49-73` |
| dựng chuỗi | `for mw in reversed(self._middlewares)` — `core/kernel.py:192-194` |
| `Client` | `AgentKernel.execute_tool` — `core/kernel.py:106-225` |
| handler cuối / fallback | `core(req)` (executor thật) — `core/kernel.py:152-177` |

---

## Các case con

| # | Case | Trọng tâm | File code |
|---|---|---|---|
| 01 | [`01_middleware_system`](./01_middleware_system/) | Xương sống CoR: dựng chuỗi động, thứ tự outer→inner, short-circuit, modulate-and-forward | [`middleware_system.py`](./01_middleware_system/middleware_system.py) |
| 02 | [`02_policy_gate_handler`](./02_policy_gate_handler/) | Handler early-exit "gate" thuần: quyết định handle vs forward, chặn trước khi tới core | [`policy_gate_handler.py`](./02_policy_gate_handler/policy_gate_handler.py) |
| 03 | [`03_condense_fail_open`](./03_condense_fail_open/) | Handler modulate-and-forward (`CondenseResult`) + hai tư thế lỗi fail-open/fail-closed + `_LatchedNext` one-shot | [`condense_fail_open.py`](./03_condense_fail_open/condense_fail_open.py) |

Mỗi thư mục case có `README.md` (6 mục: bối cảnh thật → trích code thật → ánh xạ vai trò → bản rút gọn → cái giá → câu hỏi tự kiểm) và một file `.py` chạy được (`python3 <file>.py`, exit 0).

> Danh sách **đầy đủ** mọi occurrence của pattern trong codebase (kể cả những chỗ không lên thành case riêng) nằm ở [`CATALOG.md`](./CATALOG.md).

---

## Chạy thử

```bash
python3 01_middleware_system/middleware_system.py
python3 02_policy_gate_handler/policy_gate_handler.py
python3 03_condense_fail_open/condense_fail_open.py
```

Cả hai in narration tiếng Việt từng bước, có `assert` chứng minh bất biến của pattern (thứ tự outer→inner, short-circuit không chạm core), và có đối chứng "khi KHÔNG dùng pattern thì hỏng/khó thế nào".

---

## Liên hệ với bài học gốc

Xem `../13_ChainOfResponsibility.md` để có nền lý thuyết (đường truyền cảm giác đau làm ẩn dụ, 5 chiều, anti-pattern mega switch-case, các failure case). Các case ở đây là phần "soi vào codebase thật": chỉ ra đúng file:line nơi pattern sống trong hex_agent và rút gọn lại để chạy được độc lập.
