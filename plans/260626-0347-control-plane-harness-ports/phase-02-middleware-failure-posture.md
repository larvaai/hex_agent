---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 02 — Middleware failure posture (fail-open advisory / fail-closed blocking)

**Epic:** E06 · **Rủi ro:** MEDIUM (đụng `core/kernel.py` — file dễ vỡ nhất, §1.1/§7) · **TDD:** bắt buộc

## Overview

Port phân biệt telemetry-fail-OPEN / compliance-fail-CLOSED của harness
(`harness/hooks/hook_runtime.py:329-417`). Hiện `core/kernel.py:139-147` fail-close **mọi**
middleware exception → một advisory middleware (telemetry/condense) sập sẽ **chặn oan** tool call
hợp lệ. Bộ middleware hiện tại đã tự bọc side-effect (`middleware/timing.py:18-23`) nên đây là
**guardrail nhìn-về-trước** cho middleware tương lai. Default = fail-closed (an toàn); advisory opt-in.

## Requirements

1. `core/middleware.py`: thêm quy ước thuộc tính `fail_open: bool` (mặc định coi như `False`
   nếu middleware không khai báo) vào docstring Protocol — KHÔNG ép buộc (Protocol structural).
2. `core/kernel.py`: trong vòng lắp chain (`:136-138`) + `_wrap` (`:24-30`), bọc **từng** middleware:
   - middleware ném exception **và** `getattr(mw, "fail_open", False) is True` → **nuốt** (log qua event `middleware.skipped` nếu rẻ), trả về kết quả của `nxt(request)` (bỏ qua middleware đó, chain chạy tiếp).
   - ngược lại → giữ nguyên hành vi cũ: exception nổi tới boundary `:141-147` → `ok=False, kernel_error=True`.
   - Giữ nguyên try/except boundary `:139-147` (§1.1 — KHÔNG bỏ).
   - **⚠ FM-HIGH (double-execution) — BẮT BUỘC**: `nxt` truyền cho middleware fail-open phải là **latched/memoized** (one-shot). Một advisory như `CondenseResult` gọi `nxt` rồi mới ném ở khâu hậu xử lý; nếu fallback re-gọi `nxt` thô → **chạy executor lần hai** (double side-effect cho tool không idempotent). Cơ chế: bọc `nxt` bằng proxy nhớ kết quả lần gọi đầu; gọi lần sau trả cache, KHÔNG chạy lại inner. Chỉ áp memo cho nhánh fail-open (fail-closed giữ `nxt` thường).
3. Đánh dấu advisory: `TimingLog.fail_open = True` (`middleware/timing.py`), `CondenseResult.fail_open = True` (`middleware/condense.py`). `PolicyGate`/`Retry` giữ default (fail-closed).

## Related code files

| File | Vai trò | Anchor |
|---|---|---|
| `core/kernel.py` | `_wrap`, chain assembly, boundary try/except | `:24-30`, `:136-147` |
| `core/middleware.py` | `ToolMiddleware` Protocol | `:11-15` |
| `middleware/timing.py` | advisory → `fail_open=True` | `:10-24` |
| `middleware/condense.py` | advisory → `fail_open=True` | `:11+` |
| `middleware/policy.py` | blocking → giữ default | `:9-21` |
| `core/bootstrap.py` | nơi wire middleware (không đổi thứ tự) | `:28-47` |

## Bất biến PHẢI giữ (code-standards)

- §1.1 chokepoint `execute_tool` + try/except boundary nguyên vẹn (`docs/code-standards.md:9`).
- §1.7 budget **không** thành middleware (`:127`).
- §1.9 `PolicyGate` default-OFF, `SafeToolPort` always-on (`:165`).
- Thứ tự event `tool.requested` → chain → `tool.completed|failed` (`:24`).

## Implementation steps (TDD)

**Tests Before** — mở rộng `tests/test_middleware.py` + `tests_audit/test_middleware_exact_semantics.py` (đỏ trước):
1. Advisory middleware (`fail_open=True`) ném `RuntimeError` ở thân → `execute_tool` trả `ok=True`, kết quả tool thật, middleware đó bị bỏ qua.
2. Blocking middleware (default) ném → `ok=False`, `metadata.kernel_error=True` (hành vi cũ).
3. Chain 3 middleware [advisory-raise, blocking-ok, core]: advisory bị skip, blocking vẫn chạy, core chạy → ok.
4. `PolicyGate(deny={"x"})` chặn `x` vẫn trả `ok=False` (không đổi).
5. Ordering outer→inner giữ nguyên (`test_middleware_exact_semantics`).
6. **No double-exec**: advisory middleware gọi `nxt` rồi ném ở hậu xử lý + executor đếm số lần chạy → executor chạy **đúng 1 lần**, trả result của lần đó (chứng latched `nxt`).

**Implement**: sửa `_wrap`/chain trong `core/kernel.py` đủ để xanh; thêm `fail_open=True` cho 2 advisory.

**Tests After**:
```bash
python -m pytest tests/test_kernel.py tests/test_trace_ids.py tests/test_middleware.py -q
python -m pytest tests_audit/test_middleware_exact_semantics.py tests_audit/test_kernel_registry_adversarial.py -q
python -m pytest -q            # full
python run_smoke.py           # CORE_AGENT_SMOKE_OK
```

**Regression gate**: full suite xanh **hai lần** liên tiếp trước khi commit (file dễ vỡ).

## Success criteria

- [ ] 5 case test trên xanh; 0 test cũ đỏ.
- [ ] `core/kernel.py` boundary try/except (§1.1) còn nguyên; thứ tự event không đổi.
- [ ] `TimingLog`/`CondenseResult` có `fail_open=True`; `PolicyGate`/`Retry` không.
- [ ] `CHANGELOG.md` thêm `feat(E06): explicit middleware failure posture (fail-open advisory)`.

## Risk

Cao nhất trong plan. Mọi LLM+tool đi qua đây. Giảm thiểu: thay đổi khu trú trong `_wrap`/chain assembly (≤15 dòng), default an toàn (fail-closed), suite đầy đủ + smoke hai lần. Rollback = revert đúng 1 hàm.
