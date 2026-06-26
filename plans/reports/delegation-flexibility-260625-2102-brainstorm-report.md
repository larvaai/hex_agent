---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Brainstorm — Delegation linh hoạt: agent chỉ định agent / department

Ngày: 2026-06-25 · Quyết định: [DEC-2](../../docs/decisions.md) · Hướng chốt: **C (E21-first)**
Nguồn: scout `delegation/` + `supervisor/` + `roles/` + `docs/rebuild_from_zero/E21_realtime_control_plane/` (đã verify file:line)

## Câu hỏi

Workflow hiện tại có đủ linh hoạt để **một agent tự do chỉ định agent khác, hoặc một department nhiều agent**, thực hiện nhiệm vụ không? "Linh hoạt" theo tinh thần E21 là gì?

## Trả lời ngắn: hiện tại **chưa** — và E21 cũng không có sẵn ý tưởng "department"

### Thực trạng (đã verify)
- **Chỉ Agent-O delegate; agent thường không chỉ định được agent khác.** Recursive delegation bị tắt có chủ đích — child dựng với `delegation_service=None` ([adapters/agents/langgraph_agent.py:48](../../adapters/agents/langgraph_agent.py), docstring "intentionally disabled in v1").
- **Roster khóa cứng 1 lần/run.** `compose_team` ghi `state.selected_agents` một lần ([supervisor/graph.py:98](../../supervisor/graph.py)), không bao giờ nối thêm; `run_round` ném `PermissionError` cho agent ngoài roster ([supervisor/graph.py:143-147](../../supervisor/graph.py)).
- **1 task → 1 handler, tuần tự, không song song.** `DelegationPort` không có fan-out ([core/ports.py:32-45](../../core/ports.py)); `run_round` lặp `for` tuần tự ([supervisor/graph.py:150-208](../../supervisor/graph.py)); không có asyncio/parallel.
- **Không có "department" primitive.** `department` chỉ là metadata trên `RoleSpec` ([roles/spec.py:46](../../roles/spec.py)), bị drop khỏi `RoleView` O nhìn thấy. "Parallel department" bị LOCKED ([CHANGELOG.md:21](../../CHANGELOG.md)).
- **Production chỉ register 1 handler `agent:general`** (exact-string) ([delegation/bootstrap.py:19](../../delegation/bootstrap.py)); delegate theo role-name chưa wire (multi-agent mới chạy trong test).

### E21 nói gì về "linh hoạt"
E21 coi flexible = **con người steer loop đang chạy** (interrupt/inject/approve), **không** mô hình hóa department / parallel / agent-chỉ-định-agent. Primitive gần nhất là `AddAgentToLoop`/`RemoveAgentFromLoop` + `pending_human_commands → O` ([config/runtime_command_types.yaml:16-17](../../config/runtime_command_types.yaml)) nhưng **CONTRACT-ONLY** (chưa có consumer mutate `selected_agents`), issuer là HUMAN, single-agent.

### Nền móng tốt
Seam delegation thiết kế đúng để mở rộng: `target` là string tự do, registry hỗ trợ nhiều handler, scope động per-delegation, mỗi delegate tạo session con mới ([delegation/manager.py:63-128](../../delegation/manager.py)). Thiếu: wiring + nới policy + primitive mới.

## Scope đã hội tụ (qua discovery)

| Trục | Quyết định |
|---|---|
| Ai delegate | **Chỉ orchestrator O** — không bật recursive agent-picks-agent |
| Department | **Alias gom nhiều role, chạy tuần tự** — không parallel, không sub-loop lồng |
| Roster | **Catalog + thêm tại checkpoint** — O thêm agent/role lúc chạy tại safe checkpoint |
| Department × roster | **Department được tự kéo agent chưa-compose vào team** (ngầm trigger roster-growth) |

## 3 hướng đã cân nhắc

| Hướng | Logic nằm đâu | Complexity | Rủi ro | Align E21 |
|---|---|---|---|---|
| **A** — supervisor-only, field ad-hoc | `supervisor/graph.py` + `contracts.py` | Low–Med | Med (mutate invariant + tạo đường code thứ hai) | Thấp |
| **B** — coordinator handler ở delegation seam | `delegation/registry.py` + adapter mới | Med–High | **Cao — bị loại** | Không |
| **C** — cưỡi E21 RuntimeCommand/checkpoint | `control/` + `supervisor/_drive` | High | Med (nhiều phần mới nhưng có contract đỡ) | **Cao nhất** |

**B bị loại:** coordinator fan-out con = đúng *nested sub-loop / agent-picks-agents* đã loại bỏ; authority gate chỉ thấy `dept:x` → mất kiểm soát scope + audit per-member ([supervisor/graph.py:142-147](../../supervisor/graph.py)).

## Quyết định: hướng C đầy đủ (E21-first)

Cả department lẫn roster-growth đi qua control plane E21:
1. **Roster-growth = consumer `AddAgentToLoop`.** Build `pending_commands` vào `_state_view` ([supervisor/graph.py:124-131](../../supervisor/graph.py) — đang thiếu) + bước `apply_pending_commands` tại safe checkpoint cuối round trong `_drive` ([supervisor/loop.py:147](../../supervisor/loop.py)). Tái dùng `parse_command` + `apply_at` ([control/command_registry.py:53](../../control/command_registry.py)) + `idempotency_key` ([control/commands.py](../../control/commands.py)). O phát command với `IssuedBy(type="agent", agent_id="orchestrator")`.
2. **Department = alias tự kéo member.** Target một department ngầm phát `AddAgentToLoop` cho các member chưa có trong `selected_agents`, rồi expand thành **1 `delegate()` mỗi member** trước authority gate — giữ artifact/turn per member, không đụng seam, tôn trọng recursive-disabled. Membership canonical lấy từ `RoleSpec.department` đã có trên disk ([roles/spec.py:46](../../roles/spec.py)).
3. **Seam delegation + bootstrap `agent:general` giữ nguyên** — agent mới resolve qua handler cũ; **không unfreeze registry**.

Lý do chọn C thay vì A: **một đường duy nhất** cho cả O lẫn human-UI mutate team → DRY; idempotency + audit miễn phí từ contract đã ship; **advance E21** từ contract-only sang runtime consumer đầu tiên.

## Guardrails (bắt buộc trong plan)
- **Depth không đổi** — roster-growth thêm agent cùng cấp loop O, không tăng depth.
- **Scope chỉ narrow** — mỗi member assignment mang scope riêng O cấp; department expansion không mở rộng scope ([delegation/policy.py:25-27](../../delegation/policy.py); [core/session.py:162-164](../../core/session.py)).
- **Safe checkpoint = cuối round** — apply command sau `judge_acceptance`, trước `o_decide` round kế; không apply giữa lúc đang delegate (tránh phá resume).
- **Idempotent** theo `idempotency_key`; department expansion là pure function.
- **Catalog-bound** — chỉ thêm agent/department có trong catalog (tái dùng validator [supervisor/graph.py:93-97](../../supervisor/graph.py)).
- **Authority gate vẫn là nguồn chân lý** sau expansion + sau apply command.
- **Persist** — `pending_commands` + roster mới phải persist cùng `selected_agents` trong checkpoint để resume nhất quán.

## Touchpoints dự kiến
`supervisor/contracts.py` (schema O phát command / target_kind department), `supervisor/graph.py` (`_state_view` + expansion + authority gate), `supervisor/loop.py` (`_drive` apply-at-checkpoint), `supervisor/state.py` (`pending_commands` trong `TaskLoopState` + codec), `control/commands.py` + `control/command_registry.py` (consumer/apply_at; **O-issued bỏ qua gate permission** — O được tin), `roles/spec.py` + `roles/registry.py` (expose department/group). Seam `delegation/*` **không đổi**.

## Câu hỏi còn mở

**Đã giải (chốt qua discovery 2026-06-25):**
1. ✅ **O phát RuntimeCommand kiểu nào** → O emit field `commands: [...]` trong `OrchestratorDecision`; **loop là chỗ DUY NHẤT dịch sang `RuntimeCommand` + chạm control plane**. O thuần "quyết định".
2. ✅ **Permission cho O** → **O KHÔNG cần permission**. O là actor *được tin*; bỏ gate `workflow.modify_agents` cho command O-issued (human-issued sau này vẫn có thể gate riêng). Triết lý: dạy O, đồng hành tới khi nó khôn lên, **chấp nhận O fail** — nhưng là "fail có rào": guardrail cấu trúc (catalog-bound, scope chỉ narrow, authority gate, depth không đổi) vẫn chặn fail vô hạn.

**Còn mở (đưa vào plan):**
3. **Resume semantics** — đánh dấu command đã-consume thế nào để không apply lại sau crash giữa round N và N+1.
4. **Department membership** — group theo `RoleSpec.department` (DRY, đã có disk) đủ chưa, hay cần YAML alias→roles tường minh cho department con/biến thể.

## Bước kế
Hướng đã chốt + DEC-2 đã ghi + 2 câu mở chính đã giải. Sẵn sàng `/hs:plan --tdd` (chạm logic core supervisor + control plane). Còn lại để plan khóa: resume/idempotency (#3) + nguồn department membership (#4).
