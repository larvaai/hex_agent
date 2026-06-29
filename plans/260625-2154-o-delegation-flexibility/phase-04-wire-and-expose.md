---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 04 — Wire vào loop + expose tới O (live)

Context: [plan.md](plan.md) · Touchpoints: `supervisor/loop.py`, `supervisor/graph.py`, `supervisor/llm.py`, `roles/spec.py`, `roles/registry.py`. Phase biến tính năng thành LIVE.
> Đã siết theo red-team ([report](../reports/delegation-flexibility-260625-2102-brainstorm-report.md) round 2): ordering atomic + repeat-guard + state-view slim.

## Mục tiêu
Nối command-apply (Phase 2) + department-expand (Phase 3) vào `_drive`/`run_round`, lộ department + `pending_commands` cho O, cập nhật prompt.

## CRITICAL — thứ tự trong `_drive` (chốt chặt, có test thứ tự)
Sửa thân vòng lặp `_drive` ([supervisor/loop.py:153-197](../../supervisor/loop.py)) thành đúng trình tự sau cho mỗi round:
```
decision = o_decide(state, ctx, budget=budget)            # (loop.py:161)
... (None -> FAILED, signature/repeat tính SAU, xem dưới)
enqueue_commands(state, decision)                          # đẩy decision.commands vào pending_commands
<dispatch theo decision.decision: run_round/run_tool/judge> # run_round cũng enqueue AddAgentToLoop cho dept to_admit
applied = apply_pending_commands(state, ctx, registry=ctx.command_registry, catalog=<catalog set>)
state.round_no += 1
ctx.save(state)                                            # MỘT checkpoint atomic: round_no + roster + applied_keys + pending đã clear
progressed = (len(state.artifacts) > before_artifacts
              or state.acceptance_snapshot() != before_acceptance
              or applied > 0)                              # applied PHẢI đọc tại đây
if not progressed: _terminate(... BLOCKED "no progress")
```
**Bất biến ordering (red-team FM2/FM6):** `apply_pending_commands` PHẢI nằm TRƯỚC một `ctx.save` DUY NHẤT (gộp với `round_no += 1`) — KHÔNG hai save tách rời (tránh cửa sổ crash-giữa-hai-save → double-apply). `applied` PHẢI là biến đọc ở dòng tính `progressed`.

## Requirements
1. **Enqueue O commands** (red-team: dedup theo `idempotency_key`, không dict-equality): sau `o_decide`, gọi `enqueue_commands(state, decision)` (Phase 2).
2. **Department expansion trong run_round** ([graph.py:135](../../supervisor/graph.py)) TRƯỚC authority gate: `expanded, to_admit, rejected = expand_departments(decision, members_of=ctx.agent_registry.members_of, selected=set(state.selected_agents))`; chạy authority gate + delegate trên `expanded`. Với mỗi member trong `to_admit` → `enqueue_commands` một `AddAgentToLoop` + emit `loop.department_expanded {alias, members, admitted}`. Mỗi `rejected` → emit `command.rejected` (department rỗng/không tồn tại — KHÔNG raise, FM4). `agent_registry is None` mà có department → emit `command.rejected` "department cần agent_registry" (degrade, không chết round).
3. **Apply tại safe checkpoint** = đúng trình tự CRITICAL ở trên (một save atomic). `applied = apply_pending_commands(...)` với `catalog = {r["agent_id"] for r in ctx.role_catalog()}`.
4. **Progress-counts**: `progressed = ... or applied > 0` (red-team FM1) — round chỉ grow roster KHÔNG bị BLOCKED oan.
5. **Repeat-guard không giết department-chờ-member** (red-team FM1/contradiction #1): sửa `_decision_signature` ([loop.py:41-44](../../supervisor/loop.py)) để BAO GỒM `commands` (command_type+agent_id) + `next_agent_calls[].target_kind`. (Hai round department-chờ-member khác nhau về admitted-set sẽ khác signature; nếu thật sự không tiến triển thì no-progress guard mới là cái terminate đúng.) Bổ sung: reset `repeat_count=0` khi `applied > 0`.
6. **Command registry instance**: `SupervisorContext` thêm field `command_registry: Any | None = None`; lazy `load_command_registry()` ([control/command_registry.py:92](../../control/command_registry.py)) một lần, cache (không đọc YAML mỗi round).
7. **Expose tới O — state-view SLIM** (red-team FM5): `_state_view` ([graph.py:124-131](../../supervisor/graph.py)) thêm `"pending_commands": [{"command_type": c["command_type"], "agent_id": c["payload"].get("agent_id")} for c in state.pending_commands]` (KHÔNG nguyên `as_dict()` — bỏ command_id/created_at khỏi prompt) + `"departments": ctx.departments_view()`.
8. **role_catalog + RoleView.department**: `RoleView` ([roles/spec.py:31-39](../../roles/spec.py)) thêm `department: str = ""` (default → không phá constructor cũ trong test); `role_view()` ([registry.py:69-76](../../roles/registry.py)) set `department=spec.department`; `role_catalog()` ([graph.py:50-53](../../supervisor/graph.py)) thêm `"department"`.
9. **Dạy O (prompt)**: cập nhật `DECIDE_SYSTEM` ([supervisor/llm.py:31-42](../../supervisor/llm.py)) tài liệu field `commands:[{command_type:"AddAgentToLoop", payload:{agent_id}}]` + `next_agent_calls[].target_kind:"department"` + lưu ý "member mới của department chạy ở round kế".
10. **Cảnh báo max_rounds** (red-team FM2): khi còn `pending_commands` mà `state.round_no >= state.max_rounds - 1` → emit `loop.roster_growth_starved {pending, rounds_left}` (để chẩn đoán BLOCKED do hết round). Document chi phí round của roster-growth.

## Files
- EDIT `supervisor/loop.py` (ordering CRITICAL + `_decision_signature` + repeat reset)
- EDIT `supervisor/graph.py` (`run_round` expand + emit; `SupervisorContext` `command_registry`/`departments_view`/`role_catalog`/`_state_view`)
- EDIT `supervisor/llm.py` (prompt)
- EDIT `roles/spec.py` + `roles/registry.py` (`RoleView.department`)
- ADD `tests/test_supervisor_roster_growth.py`

## TDD (ScriptedOrchestrator kịch bản hoá O)

### Tests Before
- `AddAgentToLoop` role ∈ catalog → cuối round ∈ `selected_agents`; round kế target → qua authority gate, có turn.
- Department member đã-selected → turn ngay round này.
- **Department TOÀN member chưa-compose** (red-team FM1) → round này 0 turn nhưng `applied>0` → loop KHÔNG terminate "no progress"; round kế member chạy được. KHẲNG ĐỊNH tới khi có turn của member.
- **Hai round department-chờ-member liên tiếp KHÔNG trigger repeat-BLOCKED** (red-team contradiction #1).
- **Ordering**: round roster-only → `progressed` True (test thứ tự, không chỉ kết quả).
- `_state_view["pending_commands"]` chỉ có `{command_type, agent_id}` (không command_id/created_at).
- `role_catalog()` mỗi row có `department`; `RoleView.department` set đúng.

### Implement
Theo trình tự CRITICAL; mọi event qua `ctx.emit`; apply đúng một save atomic.

### Tests After / Regression
`pytest tests/test_supervisor_roster_growth.py tests/test_supervisor_*.py tests/test_roles.py -q` xanh; `python run_smoke.py` → `CORE_AGENT_SMOKE_OK`.

## Risks + rollback
- Risk: đặt apply sai chỗ → double-apply / BLOCKED oan. → Bất biến ordering + test thứ tự (không chỉ kết quả). Rollback: gỡ 4 wiring (enqueue/expand/apply/signature) → hành vi cũ.
- Risk: department lớn × `max_rounds` mặc định starve (FM2). → emit cảnh báo + document; không tự nâng max_rounds.
