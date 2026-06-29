# CATALOG — mọi occurrence của Aggregate (DDD) trong hex_agent

> Bảng vét cạn từ bước discover, đã **mở lại từng file để xác nhận số dòng** (root:
> `/Users/uspro/Desktop/namnson/hex_agent/`). Cột "độ rõ" = mức độ một occurrence là Aggregate
> *thật* (high) hay chỉ *dùng chung nguyên lý* invariant/value-object (medium/low).

Phân loại nhanh:
- **AR thật** = mutable, có lifecycle, mutation qua method gác invariant, (thường) publish event.
- **Lite aggregate** = nhỏ, một meter/đối tượng, đổi state qua method nhưng gần value object.
- **VO + invariant-at-construction** = immutable (`frozen=True`), validate ở `__post_init__` —
  chung *nguyên lý* Lesson 35 nhưng KHÔNG phải AR.
- **Internal / projection / data bag** = không enforce invariant domain.

| path:line | Mô tả (vai trò Aggregate) | Độ rõ |
|---|---|---|
| `supervisor/state.py:80-111` | **AR thật.** `TaskLoopState` — gom `AcceptanceCheck` + `AgentTurn` + `artifacts`. `add_artifact()` (96-97) cổng ghi; `acceptance_by_id()` (99-100) query lọc internal; `all_accepted()` (102-103) invariant; `is_terminal` (105-107) chặn mutation; `acceptance_snapshot()` (109-111) như domain event. → **Case 01**. | high |
| `supervisor/state.py:28-49` | **Internal entity.** `AcceptanceCheck` — chỉ AR quản lý; bất biến cục bộ `is_satisfied` (35-37): passed VÀ có evidence. | high |
| `supervisor/state.py:52-77` | **Internal entity.** `AgentTurn` — ghi nhận 1 lượt worker/round; ngoài không tạo trực tiếp. | high |
| `supervisor/state.py:114-145` | **Biên giới persistence (Outbox-like).** `encode_taskloop_state` (114-128) / `decode_taskloop_state` (131-145) giữ consistency khi checkpoint SQLite/S3. | high |
| `core/session.py:49-101` | **AR thật.** `KernelSession` — mutable, vòng đời 1 task. `_closed` (57) state riêng; `is_active` (59-61) invariant; `execute_tool` (75-85) gác; `complete_task`/`fail_task` (87-101) đổi state atomic + publish event. → **Case 02**. | high |
| `core/session.py:15-46` | **Value Object.** `SessionIdentity` `frozen=True` — danh tính bất biến cho tra cứu xuyên session (run_id/task_id/parent_session_id/depth). | high |
| `core/session.py:104-203` | **Factory.** `SessionFactory` — nơi DUY NHẤT tạo session. `_effective_root_scope` (110-117) validate scope ⊆ khả dụng; `create_root` (119-146) + publish `task.accepted` (145); `create_child` (148-186) enforce scope con ⊆ cha (163-164); `restore` (188-203) phục dựng từ checkpoint. | high |
| `core/state.py:8-28` | **Internal / data bag.** `StateStore` — `get/set/snapshot/restore`, không enforce invariant domain; là storage cho `KernelSession` (AR thật). | low |
| `decompose_agent/tree.py:21-127` | **AR thật (cấu trúc).** `Tree` quản lý cụm `Node` bất biến. Mutation qua `set_status()` (31-32, `dataclasses.replace`), `rebuild_children()` (34-41), cursor `next_node()` (43-51). `load_tree` (99-127) enforce toàn vẹn tham chiếu (110-115) + bất chu trình (117-121). Không khoá state-machine transition nhưng đảm bảo cấu trúc đúng. | high |
| `decompose_agent/node.py:99-173` | **VO + invariant-at-construction.** `Node` `frozen=True`; `__post_init__` (119-138) validate id/kind/status/depends_on/done_when. Bất biến ⇒ không phải AR; transition đi qua `Tree.set_status`. | medium |
| `decompose_agent/node.py:50-97` | **VO + integrity boundary.** `DoneWhen` `frozen=True`; `__post_init__` (58-69) + `from_dict` (71-91) chặn key dạng-verdict (`FORBIDDEN_VERDICT_KEYS`, dòng 20). Nguyên lý "invalid state impossible" áp lên immutable. | medium |
| `decompose_agent/budget.py:15-77` | **Lite aggregate (×3).** `RootBudget` (15-31), `ParseBudget` (34-59), `AttemptBudget` (62-77). Mỗi meter có method đổi state (`record_*`) + query gác (`*_exceeded`/`exhausted`); không gán field trực tiếp. Nhỏ, gần value object. | medium |
| `discipline/budget.py:9-67` | **Lite aggregate.** `Budget` — gộp 3 meter (step/parse/same-tool). `record_step` (37-39), `step_exceeded` (41-42), `record_parse_error/success` (44-51), `parse_exceeded` (53-54), `record_tool_call`/`same_tool_exceeded` (56-61). Mọi transition qua method. | low |
| `control/events.py:113-151` | **VO + invariant-at-construction.** `RuntimeEvent` `frozen=True`; `__post_init__` (134-151) buộc event_id/event_type/session_id non-empty, actor là `Actor`, trace là `TraceContext`, redaction là `RedactionInfo`, seq ≥ 0. Immutable ⇒ không phải AR. | medium |
| `control/commands.py:61-106` | **VO + invariant-at-construction.** `RuntimeCommand` `frozen=True`; `__post_init__` (72-81) validate field bắt buộc + issued_by là `IssuedBy`. | medium |
| `control/commands.py:33-58` | **VO + invariant.** `IssuedBy` `frozen=True`; `__post_init__` (39-47): type ∈ ISSUER_TYPES, human ⇒ cần user_id, agent ⇒ cần agent_id. | medium |
| `control/commands.py:109-134` | **VO + invariant.** `CommandAck` `frozen=True`; `__post_init__` (126-134): status ∈ ACCEPT_STATUSES, rejected ⇒ cần rejection_reason. | medium |
| `control/snapshot.py:88-134` | **Projection (read-model).** `TaskLoopSnapshot` `frozen=True` — read-model UI render; `__post_init__` (103-105) chỉ check session_id. Projection, KHÔNG phải aggregate. | medium |
| `control/snapshot.py:36-85` | **VO trong projection.** `AgentView` `frozen=True`; `__post_init__` (54-60): agent_id non-empty, status ∈ AGENT_STATUSES. | medium |
| `supervisor/contracts.py:21-155` | **VO + factory-parser.** `SessionPlan` (27-35), `OrchestratorDecision` (47-55, decision ∈ `VALID_DECISIONS` dòng 17), `AgentAssignment` (39-45), `ContextPacket` (59-73) — đều `frozen=True`. Parser `parse_session_plan` (83+) như factory có validate. Không lifecycle ⇒ không AR. | medium |
