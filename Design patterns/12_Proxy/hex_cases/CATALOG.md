# CATALOG — Mọi occurrence của Proxy trong hex_agent

Bảng vét cạn các nơi pattern **Proxy** xuất hiện trong codebase `hex_agent`. Mọi `path:line` đã được mở file kiểm chứng. Path tương đối so với root `/Users/uspro/Desktop/namnson/hex_agent/`.

| path:line | Mô tả vai trò Proxy | Độ rõ |
|---|---|---|
| `core/middleware.py:11-22` | **Proxy interface.** `ToolMiddleware` protocol định nghĩa chữ ký Proxy `__call__(request, nxt)`: act trước/sau, short-circuit (không gọi `nxt`), hoặc sửa envelope. Thuộc tính tùy chọn `fail_open` quyết định blocking vs advisory. | cao |
| `core/middleware.py:8` | **Subject interface.** `ToolHandler = Callable[[ToolRequest], dict]` — interface chung mà RealSubject lẫn mọi Proxy đều phơi ra. | cao |
| `core/kernel.py:24-46` | **One-shot proxy.** `_LatchedNext` bọc inner handler, chạy tối đa 1 lần, replay kết quả/exception — chống fail-open middleware double-run tool không idempotent. | cao |
| `core/kernel.py:49-73` | **Cơ chế chaining.** `_wrap` bind một middleware quanh `nxt`; nhánh fail-closed (dòng 58-62) raise lan ra, nhánh fail-open (dòng 64-71) skip khi raise với guard `_LatchedNext`. | cao |
| `core/kernel.py:152-177` | **RealSubject.** `core(req)` resolve tool qua registry và `executor.execute(req)`, đóng gói `CapabilityResult`. Đây là object thật mà mọi proxy bọc quanh. | cao |
| `core/kernel.py:192-194` | **Chain assembly.** `for mw in reversed(self._middlewares): handler = _wrap(mw, handler)` — lắp chuỗi proxy theo thứ tự ngược (đăng ký outer->inner). | cao |
| `core/kernel.py:100-104` | **Đăng ký proxy.** `AgentKernel.use(middleware)` thêm một middleware vào pipeline; "Registration order = outer -> inner". | cao |
| `middleware/policy.py:9-21` | **Protection Proxy.** `PolicyGate`: lưu deny-set, `__call__` chặn (short-circuit) hoặc delegate `nxt`. Cùng interface, pre-check, conditional delegation. | cao |
| `middleware/budget.py:10-23` | **Rate-limiting Proxy.** `BudgetGuard`: lưu Budget, record tool call, check vượt ngưỡng -> block hoặc delegate. | cao |
| `middleware/retry.py:23-33` | **Smart Reference Proxy.** `Retry`: gọi `nxt`, kiểm tra kết quả, có thể gọi `nxt` lại nếu retryable. Retry trong suốt với client. | cao |
| `middleware/retry.py:14-20` | **Pre-check của smart-reference.** `_retryable`: không retry policy block, không retry effect không idempotent (chống double-apply). | cao |
| `middleware/timing.py:10-26` | **Smart Reference Proxy (advisory).** `TimingLog` (`fail_open=True` dòng 11): bọc `nxt` để đo thời gian, report sink; lỗi sink không làm hỏng call. | cao |
| `middleware/condense.py:11-30` | **Smart Reference Proxy (transform).** `CondenseResult` (`fail_open=True` dòng 12): gọi `nxt`, bỏ qua `llm.*`, áp condense lên `data`, trả envelope đã chỉnh. Advisory/fail-open. | cao |
| `safety/policy.py:105-124` | **Protection Proxy (một-class).** `SafeToolPort`: `_inner` (real subject) + `_policy`; `execute()` check policy rồi block hoặc `self._inner.execute(request)`. Khuôn mẫu GoF rõ nhất. | cao |
| `safety/policy.py:77-102` | **Pre-check logic.** `ToolPolicy.check` — cổng an toàn cross-cutting duy nhất; phân nhánh terminal / git mutation / repair-mode whole-file write. | cao |
| `safety/policy.py:53-71` | **Phân loại argv.** `classify_terminal` — pre-check chi tiết cho `terminal_run`: shell exe, shell token, destructive, git mutation, path escape. | cao |
| `safety/policy.py:41-46` | **Quyết định gate.** `PolicyDecision(allowed, reason, code, risk)` — kết quả của pre-check mà Proxy dùng để block/allow. | trung bình |
| `core/bootstrap.py:28-53` | **Composition / ordering.** `_install_middleware` cài proxy theo thứ tự outer->inner: timing, policy, retry, condense. Order là load-bearing. | cao |
| `tests_audit/test_middleware_safety_graph_rigor.py:52-63` | **Test pass-through.** `test_policy_gate_passes_through_when_not_denied...` — pin hành vi delegate khi tool không bị deny. | cao |
| `tests_audit/test_middleware_safety_graph_rigor.py:66-73` | **Test block path.** `test_policy_gate_block_without_on_block_hook...` — pin short-circuit khi bị deny, không gọi inner. | cao |
| `tests_audit/test_middleware_safety_graph_rigor.py:88-125` | **Test smart-reference (Retry).** Các test retry: clamp attempts, retry idempotent effect nhưng không retry non-idempotent, missing/None metadata. | cao |
| `tests_audit/test_middleware_safety_graph_rigor.py:133-142` | **Test rate-limit block.** `test_budget_guard_blocks_without_hook...` — pin block khi vượt ngưỡng, key theo (name,args). | cao |
