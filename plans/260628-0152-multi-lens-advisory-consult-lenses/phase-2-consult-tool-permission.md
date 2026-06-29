---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 2 — consult_lenses dispatch + capability permission (agent gọi thêm lens)

**Mục tiêu:** agent gọi `consult_lenses` mid-ReAct → lens lines về làm observation. Quyền qua capability gate sẵn có. Lens không consult được. Empty-by-default.

## Touchpoints
- `drag_from_zero/dragzero/orchestrator.py` — `Orchestrator.__init__` thêm `lenses=None`; nhánh `consult_lenses` trong `_run_tool` ([orchestrator.py:164](../../drag_from_zero/dragzero/orchestrator.py)). KHÔNG sửa `_react_until_terminal`/`start`/`run`/`_solve_gated`.
- `drag_from_zero/tests/test_lens.py` — thêm test orchestrator-level.

## Thiết kế

### `Orchestrator.__init__` (+1 param, empty-by-default)
```
def __init__(self, roster, ..., lenses: Optional[LensRegistry] = None):
    self.lenses = lenses          # None → consult disabled, byte-identical
```

### Nhánh `_run_tool` ([orchestrator.py:199](../../drag_from_zero/dragzero/orchestrator.py))
```
def _run_tool(self, tool_call, rec=None) -> ToolResult:
    if tool_call.tool == "consult_lenses":
        if self.lenses is None:
            return ToolResult(False, "", "consult_lenses not configured")
        stages = self._resolve_consult(tool_call.args)   # args: {combo:name} | {lenses:[ids]}; unknown id drop
        if not stages:
            return ToolResult(False, "", "no lenses resolved")
        base_ctx = self._consult_ctx(rec, tool_call.args)  # F6: situation, không chỉ task thô (xem dưới)
        lines = run_lenses(stages, base_ctx, rec.agent.llm, self.log, agent_id=rec.agent.id, source="adhoc")
        return ToolResult(True, "\n".join(lines))
    ... (đường tool cũ nguyên vẹn) ...
```
- **[red-team F6] base_ctx cho consult ad-hoc KHÔNG chỉ là `task`.** Mid-loop agent đã có observations; lens phải thấy "tình huống hiện tại", không phải task thô. `_consult_ctx(rec, args)` trả `{"task": rec.task.description, "on": args.get("on"), "context": <clip observations gần nhất>}`. Agent nêu thứ muốn soi qua `args["on"]` (optional). Mandate (combo lúc vào task, phase 3) thì `base_ctx={"task":...}` là đủ vì agent chưa làm gì.
- **[red-team F1] L2 KHÔNG dựa vào capability gate.** Enforcement chính = **structural**: `run_lenses` không cầm ToolRegistry; `_run_tool` chỉ có 1 caller (orchestrator.py:272) reachable từ `_react_until_terminal` → lens vật lý không tới được tool dispatch. Capability gate (orchestrator.py:268) chạy TRƯỚC `_run_tool` nhưng **CHỈ chặn khi một `Capability` được set** (`rec.capability is not None`); mặc định `capability=None` → consult cho phép. Gate là lớp opt-in PHỤ, KHÔNG default-deny.
- `_run_tool` hiện chữ ký `(tool_call)` (orchestrator.py:199); thêm `rec` để lens-runner có `rec.agent.llm` + observations. Call site **duy nhất** orchestrator.py:272 trong `_react_until_terminal` — truyền `rec`. (1 dòng đổi; grep xác nhận 1 caller.)
- Lens lines về observations qua đường TOOL_RESULT sẵn có (orchestrator.py:238-242) → agent.step kế thấy.

## Tests Before (đỏ trước) — `tests/test_lens.py`
1. `test_agent_consult_observation` — FakeLLM agent: step 0 emit `{action: tool consult_lenses, args:{lenses:[risk,evidence]}}`, step 1 SOLO. Orchestrator(lenses=reg). Sau run: observations của step 1 chứa 2 dòng lens; log có TOOL_CALLED(consult_lenses) + TOOL_RESULT + 2×LENS_QUERIED/RETURNED.
2. `test_consult_gated_when_capability_set` (LUẬT 2, opt-in) — agent capability=`Capability(tools=frozenset())` (không có consult_lenses) → TOOL_DENIED, KHÔNG LENS_QUERIED. *(Chỉ chứng minh lớp opt-in; mặc định capability=None thì consult cho phép — đó là posture local đúng, KHÔNG test default-deny.)*
3. `test_lens_cannot_dispatch_tool` (LUẬT 2 structural — [red-team F5]) — chạy 1 combo mà 1 lens responder trả dạng tool-action → assert **0 TOOL_CALLED** xuất hiện giữa LENS_QUERIED và LENS_RETURNED (lens không tới được tool dispatch). KHÔNG assert `_one_line` stringify (sai invariant). Structural anchor: `_run_tool` 1 caller (orchestrator.py:272).
4. `test_consult_empty_by_default` (LUẬT 3) — Orchestrator(lenses=None) + agent gọi consult_lenses → TOOL_RESULT ok=False "not configured"; `tools.names()` không đổi; không LENS event.

## Implement After
Thêm param `lenses` + nhánh `_run_tool` + `_resolve_consult`. Truyền `rec` vào `_run_tool`.

## Tests After / Regression Gate (LUẬT 3)
- `python -m pytest drag_from_zero/tests/test_lens.py -q` → xanh.
- `python -m pytest drag_from_zero -q` → **suite cũ xanh nguyên** (`test_slice4_tools`, `test_capability`, `test_invariants`). Gate chứng minh đường tool/ReAct cũ không đổi.

## Done-when phase
4 test xanh; agent gọi consult được, capability chặn được (luật 2 đỏ-rồi-xanh), lens không dispatch tool, lenses=None byte-identical; suite cũ nguyên.
