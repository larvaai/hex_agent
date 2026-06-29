# CATALOG — Mọi occurrence của Chain of Responsibility trong hex_agent

Bảng vét cạn các vị trí pattern xuất hiện. Mọi `path:line` đã được mở file kiểm chứng. Path tương đối so với root `/Users/uspro/Desktop/namnson/hex_agent/`.

Cột **độ rõ**: mức độ thể hiện pattern một cách rõ ràng/giáo khoa (cao / trung bình).

---

## A. Lõi pattern (interface + chain builder + client)

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `core/middleware.py:11-22` | `ToolMiddleware` Protocol: `__call__(request, nxt) -> dict`. Interface Handler của CoR; cấu trúc, không ABC. Docstring mô tả 3 quyền: act before/after, short-circuit (return không gọi `nxt`), modify result. | cao |
| `core/kernel.py:49-73` | `_wrap(middleware, nxt, on_skip)`: bind 1 middleware quanh handler kế tiếp (bước "set_next"). Nhánh fail-closed (58-62) vs fail-open (64-73). Dùng `_LatchedNext` (gọi ở dòng 65) cho fail-open. **(Case 03 cho nhánh fail-open)** | cao |
| `core/kernel.py:24-46` | `_LatchedNext`: proxy one-shot quanh inner handler — chạy `nxt` tối đa một lần; lần sau replay outcome cũ. Phòng fail-open middleware raise SAU khi đã gọi `nxt` làm tool chạy hai lần (FM-HIGH). **(Case 03)** | trung bình |
| `core/kernel.py:106-225` | `AgentKernel.execute_tool`: Client của CoR. Tạo request, dựng chuỗi (192-194), gọi chuỗi (196), đóng dấu lineage kể cả khi short-circuit (210-213). | cao |
| `core/kernel.py:152-177` | `core(req)`: handler cuối / fallback của chuỗi — gọi executor thật và bọc thành `CapabilityResult`. | cao |
| `core/kernel.py:192-194` | Dựng chuỗi từ trong ra ngoài: `handler = core; for mw in reversed(self._middlewares): handler = _wrap(...)`. Thứ tự đăng ký = outer → inner. | cao |
| `core/kernel.py:100-104` | `AgentKernel.use(middleware)`: đăng ký 1 ToolMiddleware; raise nếu chuỗi đã frozen (chống mutate chuỗi sau khi session bắt đầu). | cao |
| `core/bootstrap.py:28-53` | `_install_middleware`: wire built-in middleware theo thứ tự khai báo (timing → policy → retry → condense). BudgetGuard cố tình KHÔNG wire ở đây (counter per-run sẽ rò qua các run). | cao |

## B. ConcreteHandler (các middleware)

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `middleware/policy.py:9-22` | `PolicyGate`: gate deny-list. Nếu tool trong deny-set → return envelope chặn (short-circuit), ngược lại `nxt(request)`. Handler "gate" thuần, không modulate. **(Case 02)** | cao |
| `middleware/retry.py:23-33` | `Retry`: gọi `nxt()` trong vòng lặp tới khi `ok=True` hoặc hết số lần. Forward kèm re-invoke (khác CoR one-shot điển hình nhưng vẫn tuân interface). Không retry policy-block hay effect không idempotent. | cao |
| `middleware/condense.py:11-30` | `CondenseResult`: gọi `nxt()`, quan sát result envelope, rút gọn field `data`, forward result. Hậu xử lý + callback `on_condense` tùy chọn. Đánh dấu `fail_open = True` (advisory). **(Case 03)** | cao |
| `middleware/budget.py:10-23` | `BudgetGuard`: kiểm tra budget trước khi forward; short-circuit nếu vượt budget, ngược lại `nxt()`. Vai trò gating giống `PolicyGate`. | cao |
| `middleware/timing.py:10-26` | `TimingLog`: bọc cuộc gọi `nxt()` bằng đo thời gian, publish metric qua sink callback. `fail_open = True` (advisory, non-blocking). | cao |

## C. Tests cố định hành vi pattern

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `tests/test_middleware.py:1-187` | Bộ test toàn diện cho chuỗi middleware: thứ tự outer→inner (35-50), short-circuit policy (15-23), condense (53-71), budget (74-80), retry (83-99), tư thế fail-open/fail-closed (111-157), latching (160-187). | cao |
| `tests/test_middleware.py:15-23` | `test_policy_blocks_before_core`: chứng minh short-circuit — tool không chạy khi bị chặn; `metadata.policy_block=True`; callback `on_block` ghi nhận; kernel vẫn đóng trace-id. **(Case 02)** | cao |
| `tests/test_middleware.py:53-71` | `test_condense_shrinks_tool_but_skips_llm`: result tool bị rút gọn; tool `llm.*` KHÔNG bị rút gọn (modulate có điều kiện). **(Case 03)** | cao |
| `tests/test_middleware.py:111-187` | Tư thế lỗi + latching: fail-open advisory (111-125), fail-closed blocking (128-137), chỉ skip advisory hỏng (140-157), advisory raise sau `nxt` không double-execute nhờ `_LatchedNext` (160-187). **(Case 03)** | cao |
| `tests_audit/test_core_edges_rigor.py:46-127` | Kiểm chứng cấu trúc Protocol: `RecordingMiddleware` (52) là subtype tối giản; test thoả Protocol (68), short-circuit không gọi `nxt` (82-102), bất biến thứ tự outer→inner (105-126). | cao |

---

## Tóm tắt độ phủ case

- **Case 01 — `01_middleware_system`** distill: `core/middleware.py:11-22`, `core/kernel.py:49-73, 100-104, 152-177, 192-194`, `core/bootstrap.py:28-53`, và các test cấu trúc `tests_audit/test_core_edges_rigor.py:46-127`.
- **Case 02 — `02_policy_gate_handler`** distill: `middleware/policy.py:9-22`, `tests/test_middleware.py:15-23`, `core/bootstrap.py:38-42`, `core/kernel.py:152-177`.
- **Case 03 — `03_condense_fail_open`** distill: `middleware/condense.py:11-30`, `discipline/condense.py:13-24`, `core/kernel.py:24-46` (`_LatchedNext`), `core/kernel.py:58-73` (nhánh fail-open/fail-closed của `_wrap`), `core/kernel.py:179-190` (`on_skip` → event `middleware.skipped`), và các test `tests/test_middleware.py:53-71, 111-187`.

Các occurrence trong nhóm B còn lại (`retry`, `budget`, `timing`) không lên thành case riêng nhưng được đối chiếu trong README case 01 (mục "đã lược bỏ" và "cái giá") và case 03 (`Retry` được phân biệt rõ ở mục "cái giá": fail-closed, gọi `nxt` nhiều lần có chủ đích, KHÔNG latch).
