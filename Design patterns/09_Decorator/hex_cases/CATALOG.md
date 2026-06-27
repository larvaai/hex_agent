# CATALOG — Mọi occurrence của Decorator trong hex_agent

> Vét cạn mọi điểm xuất hiện pattern **Decorator (Structural)** trong codebase `hex_agent`.
> Mọi `path:line` đã được mở và kiểm chứng. Path là TƯƠNG ĐỐI so với root `/Users/uspro/Desktop/namnson/hex_agent/`.
> Cột "độ rõ": **cao** = thể hiện pattern trực tiếp/sạch; **trung bình** = thể hiện gián tiếp hoặc trộn lẫn nhiều concern.

## Mã nguồn (production)

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `core/middleware.py:11-22` | `ToolMiddleware` Protocol — **interface của Decorator**. Mọi middleware phải có `__call__(request, nxt) -> dict`, nhận cả request VÀ inner handler (`nxt`), cho phép decorate trước/sau và short-circuit. | cao |
| `core/kernel.py:49-73` | `_wrap()` — **logic lắp ráp Decorator**. Tạo handler bọc quanh `nxt`, chèn hành vi middleware trước/sau khi delegate. Xử lý posture fail-open vs fail-closed. | cao |
| `core/kernel.py:192-194` | Vòng lặp dựng chuỗi trong `execute_tool()`: `for mw in reversed(self._middlewares): handler = _wrap(mw, handler, ...)` — **client dựng toàn bộ chuỗi decorator** từ trong ra ngoài. | cao |
| `core/kernel.py:24-46` | `_LatchedNext` — decorator caching/một-lần quanh inner handler. Chống chạy lại tool (non-idempotent) khi advisory middleware raise sau khi đã gọi `nxt`. Là decorator pattern dạng caching. | cao |
| `core/kernel.py:152-177` | closure `core` — **ConcreteComponent** (lõi gọi `executor.execute(req)`), được bọc bởi mọi middleware. | cao |
| `middleware/__init__.py:1-7` | Export 5 ConcreteDecorator: `BudgetGuard`, `CondenseResult`, `PolicyGate`, `Retry`, `TimingLog` — họ decorator sẵn sàng để compose. | cao |
| `middleware/retry.py:23-33` | `Retry` — ConcreteDecorator bọc executor. Gọi `nxt(request)`, kiểm tra `ok`, gọi LẠI `nxt` (không gọi tool trực tiếp) tới `attempts` lần. | cao |
| `middleware/retry.py:14-20` | `_retryable()` — cổng logic: không retry `policy_block`, không retry `effect` non-idempotent. | cao |
| `middleware/budget.py:10-23` | `BudgetGuard` — decorator chặn lời gọi tool lặp vượt budget. Vượt → short-circuit trả error dict KHÔNG gọi `nxt`; ngược lại delegate. Ví dụ decorator bỏ qua được inner. | cao |
| `middleware/timing.py:10-26` | `TimingLog` — decorator đo wall-time quanh thực thi (`perf_counter`). Gọi `nxt()`, đo, gửi metrics, trả result NGUYÊN. `fail_open=True` (post-decoration). | cao |
| `middleware/condense.py:11-30` | `CondenseResult` — decorator post-process kết quả, nén data lớn. Bỏ qua `llm.*` (dòng 22-23). `fail_open=True`. | cao |
| `middleware/policy.py:9-21` | `PolicyGate` — decorator deny-list. Kiểm tra `request.name` bị chặn TRƯỚC khi gọi `nxt`; nếu chặn trả error dict, không gọi `nxt` (short-circuit). Decorator dạng guard (pre-condition). | cao |
| `core/bootstrap.py:28-53` | `_install_middleware()` — composition order outer→inner: timing → policy → retry → condense. Stack middleware theo config (kiểu Express/Flask/ASP.NET). | trung bình |

## Tests (chứng thực semantic Decorator)

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `tests/test_middleware.py:35-50` | `test_ordering_outer_to_inner` — truy vết call stack, chứng minh thứ tự `A:in → B:in → B:out → A:out`. Bằng chứng chuỗi decorator kinh điển. | cao |
| `tests/test_middleware.py:15-23` | `test_policy_blocks_before_core` — `PolicyGate` short-circuit không gọi `nxt`, trả error dict. Chứng minh decorator chặn được trước khi delegate. | cao |
| `tests/test_middleware.py:74-80` | `test_budget_guard_blocks_repeated_tool` — `BudgetGuard` chặn lần thứ 3 (sau 2 lần giống nhau). State (counter) + logic guard của decorator. | cao |
| `tests/test_middleware.py:53-71` | `test_condense_shrinks_tool_but_skips_llm` — `CondenseResult` post-process, bỏ qua `llm.*`. Decorate có chọn lọc theo tên tool. | cao |
| `tests/test_middleware.py:83-99` | `test_retry_recovers_flaky_tool` — `Retry` bọc tool chập chờn (fail lần 1, ok lần 2), phục hồi trong suốt; tool thật chạy đúng 2 lần. | cao |
| `tests/test_middleware.py:111-125` | `test_advisory_middleware_failure_is_fail_open` — advisory raise sau `nxt`, tool vẫn ok nhờ latched `nxt` replay kết quả. Semantic fail-open. | cao |
| `tests_audit/test_middleware_exact_semantics.py:12-29` | `test_bootstrap_middleware_order_...` — xác thực thứ tự cấu hình `[TimingLog, PolicyGate, Retry, CondenseResult]`. Bootstrap wire decorator outer→inner đúng. | cao |
| `tests_audit/test_middleware_exact_semantics.py:32-44` | `test_timing_emits_one_exact_measurement_...` — xác thực side-effect sink của `TimingLog` và nó trả envelope NGUYÊN (`returned is envelope`). | cao |
| `tests_audit/test_middleware_exact_semantics.py:57-72` | `test_budget_guard_blocks_only_after_exact_limit_...` — `BudgetGuard` chỉ chặn lần 3 (max=2), gọi hook 1 lần, cho qua 2 lần đầu. | cao |
| `tests_audit/test_middleware_exact_semantics.py:75-85` | `test_policy_gate_never_calls_inner_...` — `PolicyGate` short-circuit, KHÔNG gọi inner (`pytest.fail` nếu inner chạy). Pure guard decorator. | cao |
| `tests_audit/test_middleware_exact_semantics.py:88-99` | `test_condense_skips_llm_and_notifies_only_when_value_actually_changes` — `CondenseResult` bỏ qua `llm.*`, chỉ notify khi giá trị thực sự đổi. | cao |
| `tests_audit/test_middleware_exact_semantics.py:102-123` | `test_retry_call_count_matrix` — ma trận số lần gọi `nxt` của `Retry` cho 5 kịch bản. | cao |
| `tests_audit/test_core_edges_rigor.py:52-67` | `RecordingMiddleware` — structural subtype tối thiểu của `ToolMiddleware` (chỉ `__call__(request, nxt)`), dùng để test contract Protocol. | cao |
| `tests_audit/test_core_edges_rigor.py:68-80` | `test_tool_middleware_protocol_is_satisfiable_and_runs_pre_post` — class chỉ có `__call__` là structural `ToolMiddleware`; kernel drive nó quanh `execute_tool`. | cao |
| `tests_audit/test_core_edges_rigor.py:82-103` | `test_tool_middleware_can_short_circuit_without_calling_next` — Protocol cho phép short-circuit: middleware return mà không gọi inner tool. | cao |
| `tests_audit/test_core_edges_rigor.py:105-132` | `test_tool_middleware_registration_order_is_outer_to_inner` — 2 middleware: thứ tự đăng ký = outer → inner; outer bọc inner. | trung bình |
