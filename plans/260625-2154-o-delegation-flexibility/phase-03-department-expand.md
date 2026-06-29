---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 03 — Department expansion (pure)

Context: [plan.md](plan.md) · Touchpoints: `roles/registry.py`, `supervisor/graph.py` (helper expand). Chưa wire vào `_drive` (Phase 4).

## Mục tiêu
Cho phép một `AgentAssignment` với `target_kind=="department"` được expand thành các member role của department, **một assignment agent-level mỗi member**, trước authority gate. Member chưa-selected → sinh ý định `AddAgentToLoop` (chạy round kế).

## Requirements
1. `AgentRegistry.members_of(department: str) -> tuple[str, ...]` ([roles/registry.py](../../roles/registry.py)) — trả `spec.name` của mọi role có `spec.department == department` (sorted, deterministic). Department không tồn tại → `()`.
2. (Tuỳ chọn, để O "thấy") `AgentRegistry.departments() -> dict[str, tuple[str,...]]` group theo `RoleSpec.department`.
3. Helper thuần `expand_departments(decision, *, members_of, selected: set[str]) -> tuple[list[AgentAssignment], list[str], list[tuple[str, str]]]` (trả `(expanded, to_admit, rejected)`; đặt trong `supervisor/graph.py` — gần run_round):
   - Với mỗi `assignment` trong `decision.next_agent_calls`:
     - `target_kind=="agent"` → giữ nguyên.
     - `target_kind=="department"` → `members = members_of(assignment.agent_id)`. **Disambiguation (red-team FM4):** nếu `members == ()` thì department không tồn tại / rỗng → KHÔNG raise trần. Helper trả một tín hiệu lỗi mềm (vd thêm vào danh sách `rejected: list[(dept, reason)]`) để caller (Phase 4) emit `command.rejected` với message rõ ("department '<x>' rỗng hoặc không tồn tại; nếu định target một agent hãy dùng target_kind='agent'") — KHÔNG để cả round chết bằng `ValueError`. Department-name nên tách namespace với agent-name (document). Với mỗi member:
       - member ∈ `selected` → thêm `AgentAssignment(agent_id=member, objective, scope_of_work, allowed_capabilities, target_kind="agent")` (chạy round này).
       - member ∉ `selected` → thêm member vào danh sách "to_admit" (sinh `AddAgentToLoop`) — KHÔNG thêm vào assignments round này.
   - Trả `(expanded_agent_assignments, to_admit_agent_ids, rejected)` — `rejected` = department không giải được, để caller emit `command.rejected` (không raise).
   - **Scope không widen**: mỗi member assignment dùng đúng `allowed_capabilities` của assignment department gốc (O cấp); không tự thêm tool.
4. Pure: không emit, không mutate state — caller (Phase 4) emit `loop.department_expanded` + enqueue `AddAgentToLoop` cho `to_admit`.

## Files
- EDIT `roles/registry.py` (thêm `members_of` + `departments`)
- EDIT `supervisor/graph.py` (thêm `expand_departments` helper)
- ADD `tests/test_supervisor_department_expand.py`
- (có thể EDIT `tests/conftest.py` để register vài role cùng department cho fixture)

## TDD

### Tests Before
- `members_of("engineering")` → đúng tập role có department=="engineering" (sorted); department lạ → `()`.
- `expand_departments` với assignment department có 2 member đã-selected → 2 assignment agent-level, `to_admit==[]`.
- Member 1 selected + 1 chưa → 1 assignment (member selected) + `to_admit==[member_chưa]`.
- Assignment `target_kind=="agent"` → giữ nguyên, không expand.
- Department rỗng/không tồn tại → vào `rejected` (KHÔNG raise); caller emit `command.rejected`.
- Tên là agent (không phải department) mà O lỡ set `target_kind=="department"` → `members_of()==()` → `rejected` với message gợi ý dùng `target_kind="agent"`.
- Scope: member assignment.allowed_capabilities == của assignment gốc (không widen, không thêm tool).

### Implement
Group-by trên `self._roles.values()` theo `.department`. Helper pure, nhận `members_of` callable + `selected` set (dễ test, không cần ctx).

### Tests After
`pytest tests/test_supervisor_department_expand.py -q` xanh.

### Regression Gate
`pytest tests/test_supervisor_*.py tests/test_roles.py -q` xanh (helper chưa wire).

## Risks + rollback
- Risk: hai role khác nhau cùng `name` trong nhiều department → `name` đã unique toàn registry ([registry.py:33-35](../../roles/registry.py)) nên an toàn.
- Risk: department lớn → nhiều delegate tuần tự/round. Chấp nhận (v1 tuần tự, không cap). Rollback: bỏ `expand_departments` (run_round cũ không gọi).
