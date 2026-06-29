# E10 — Multi-agent TaskLoop & Scoped-Context Orchestration (PRD, v2)

Phase: P3 · Features: F15, F16

> **v2 — reframe.** Bản draft cũ mô tả một *company pipeline tĩnh* (research→BA→…→final).
> Bản này đổi sang **TaskLoop động**: một orchestrator (Agent O) tự chọn team, chạy vòng hội
> thoại có giới hạn, và chỉ `Finished` khi đủ acceptance criteria + evidence. Pipeline cố định
> cũ trở thành **một workflow template** mà O có thể chạy, không còn là chế độ duy nhất.
> Đã verify đối chiếu seam thật: `core/kernel.py`, `core/session.py`, `delegation/manager.py`,
> `core/schemas.py`. Xem `docs/RUNTIME_FLOW.md`.

## Problem
Một task nhỏ nhiều khi cần 2–3 agent đối thoại (đề xuất → phản biện → sửa) rồi mới gọi tool,
và phải dừng đúng lúc khi đạt acceptance criteria. Hiện tại chỉ có single-agent loop (E05) +
delegation **tuần tự** (`DelegationManager`); chưa có ai (1) chọn team động, (2) chạy nhiều
vòng có kỷ luật, (3) gác `Finished` bằng evidence, (4) cấp **context đúng scope** cho từng agent
thay vì broadcast cả hội thoại.

## Goal
Một **supervisor graph** mới (LangGraph, anh em với E05), điều khiển bởi **Agent O**:
- O **compose team** tối thiểu từ agent registry của department (E09/E11).
- O chạy **bounded dialogue loop**: mỗi vòng delegate cho các agent đã chọn, gom output vào
  một **Blackboard** serializable.
- Mỗi agent chỉ nhận một **Context Packet** do **Context Broker** lọc từ Blackboard (nguồn sự
  thật), **không** nhận transcript đầy đủ.
- O là **judge**: kiểm từng AC theo evidence, ra quyết định JSON `continue | need_tool |
  finished | blocked | failed`. `Finished` chỉ khi mọi AC `passed` có evidence.
- Loop guard chống vô hạn (max_rounds + bắt buộc có tiến triển mỗi vòng).

## Core invariants — KHÔNG được đổi (chốt từ review kiến trúc)
1. **`core/kernel.py` giữ mỏng.** Chokepoint duy nhất vẫn là `execute_tool`. **Không** thêm
   `run_agent/run_session/route_event/create_context_packet` vào core. Các trách nhiệm đó thuộc
   tầng supervisor + delegation.
2. **Một đường thực thi.** LLM vẫn là capability `llm.chat` qua `execute_tool`. **Không** mở
   `ModelPort.generate()` vòng qua chokepoint.
3. **LangGraph = control, EventBus = observability.** TaskLoop là một graph, **không** phải event
   loop tự chế trong core.
4. **Không có global shared state.** Không broadcast Blackboard/transcript cho mọi agent. Mỗi
   agent chỉ thấy Context Packet trong scope của nó (đã được enforce sẵn: `create_child` không
   kế thừa `messages` của parent; scope con ⊆ scope cha).

## Kiến trúc (4 tầng — chỉ tầng 4 là mới)
```
Tầng 4  supervisor/ (MỚI)   Agent O + TaskLoop graph + Blackboard + Context Broker
           │  mỗi lượt agent = delegate(...)
Tầng 3  delegation/         "run_agent" CÓ SẴN: 1 worker = 1 child session, scope hẹp
Tầng 2  graph/ + discipline/ E05 node + Budget/finish_gate (tái dùng, mở rộng max_rounds)
Tầng 1  core/               execute_tool (chokepoint duy nhất, mỏng)
```
TaskLoop graph (nodes):
```
compose_team → o_decide ─(continue)─► per selected agent: broker → delegate → collect ─┐
                  │                                                                      │
                  ├─(need_tool)─► tool ─────────────────────────────────────────────────┤
                  │                                                                       ▼
                  │                                                            judge_acceptance → o_decide …
                  ├─(finished)─► finish
                  └─(blocked|failed|max_rounds)─► fail
```
`broker` (agent) dựng Context Packet cho từng worker NGAY trước `delegate`; mỗi worker turn = một
child session cô lập chỉ thấy packet của nó.

## Data contracts — TÁI DÙNG, không phát minh lại
ChatGPT đề xuất nhiều object mới cho core; gần như tất cả **đã có**. Map như sau:

| Khái niệm (ChatGPT) | Dùng cái đã có | Thay đổi cần |
|---|---|---|
| `ContextPacket` | `DelegationSpec`(objective+input_context) + `DelegationPolicy`(allowed_capabilities) | **mở rộng** `DelegationSpec`: thêm `expected_output_schema: dict`, `constraints: list[str]` |
| `AgentOutput` | `DelegationResult` (outcome, artifacts, summary) | — |
| `ArtifactRef` | `ArtifactEnvelope` | — |
| `KernelEvent` | events của `EventBus` (delegation.*, tool.*) | thêm vài topic loop.* |
| Event/Artifact **Store** | `DelegationStorePort` + `observability` log | — (tùy chọn E14 cho memory bền) |
| `ContextRequest` | input nội bộ của Context Broker | type mới **trong supervisor**, không vào core |
| `run_agent(...)` | `DelegationServicePort.delegate(...)` | — |

**Type mới (chỉ ở supervisor, serializable như `AgentState`):**
- `Blackboard` / `TaskLoopState`: `task_id, status, round_no, max_rounds, selected_agents[],
  turns[], artifacts{}, tool_results{}, acceptance_checks[]`.
- `AcceptanceCheck`: `id, text, status ∈ {pending|passed|failed|missing_evidence}, evidence_ids[]`.
- `TaskLoopStatus`: `created|team_selected|in_discussion|waiting_tool|reviewing_ac|finished|blocked|failed`.

## Agent O — contract quyết định (JSON, qua `json_gate` như E05)
```json
{
  "decision": "continue | need_tool | finished | blocked | failed",
  "selected_agents": ["planner_agent", "critic_agent"],
  "next_agent_calls": [
    {"agent_id": "critic_agent",
     "objective": "Phản biện bản đề xuất subtask của planner",
     "scope_of_work": "Chỉ xét đủ-nhỏ + có-AC; không sửa core",
     "allowed_capabilities": ["fs_read"]}
  ],
  "tool_requests": [],
  "acceptance_status": [{"id": "AC-2", "status": "missing_evidence", "evidence": []}],
  "progress_made": true,
  "reason": "AC-2 chưa đủ bằng chứng",
  "final_output": null
}
```
O chỉ giao **assignment** (objective + scope_of_work + scope quyền); **Context Broker** mới dựng
`context_packet` thực tế từ store. O **không execute gì**: `next_agent_calls` → broker → `delegate()`;
`tool_requests` → `execute_tool`.

## Context Broker — một AGENT riêng, chạy trước mỗi worker turn
Broker là agent (LLM), không phải bộ lọc tĩnh. Mỗi lượt: đọc *assignment* của agent kế tiếp
(objective + scope of work do O giao) → suy luận cái gì liên quan → **tự viết** briefing/context
vừa đủ cho agent đó. 4 guardrail bắt buộc để "tự viết" không thành "bịa tự do":
- **Grounded**: supervisor nạp cho Broker *lát cắt Blackboard/store liên quan* (candidate artifacts/
  turns) làm input; Broker viết briefing **từ input đó**, không từ trí nhớ. (Store vẫn là nguồn sự thật.)
- **Provenance bắt buộc**: packet đính `source_ids` (artifact_id/turn_id) mà briefing dựa vào →
  evidence truy được, AC gate (S10.6) dùng lại.
- **Packet log thành artifact** trên Blackboard → audit được "agent B đã thấy gì" khi B sai.
- **Size cap**: packet có token budget cứng để ép "vừa đủ"; phần dài có thể `discipline.condense`
  nhưng phải đánh dấu là summary.
- **Scope KHÔNG do Broker cấp** (bất biến cứng): `DelegationPolicy.allowed_capabilities` của B do
  O/policy đặt (least privilege). Broker chỉ nắn *context thông tin*, không bao giờ nới quyền —
  đồng nhất với invariant "model output không cấp capability" của kernel.

> Đánh đổi: +1 LLM call mỗi worker turn (Broker chạy trước mỗi lượt). Loop guard phải tính cả
> Broker call vào budget. Bù lại prompt của worker nhỏ và tập trung hơn.

## Scope — In
- `supervisor/` package: TaskLoop graph + nodes (`compose_team, o_decide, run_round, judge_acceptance,
  tool, finish, fail`) + `Blackboard` serializable + checkpoint/resume như E05.
- Agent O prompt+contract (structured JSON, repair qua json_gate).
- Context Broker = **agent riêng** chạy trước mỗi worker turn: tự viết briefing từ lát cắt store
  được cấp; packet đính `source_ids`, được log thành artifact, có size cap; **không** cấp scope.
- Worker turn = `delegate()` (child session cô lập, scope hẹp, kết quả = `ArtifactEnvelope`).
- Acceptance gate: deterministic check trên evidence + tùy chọn LLM judge; mirror `finish_gate`.
- Loop guard: mở rộng `discipline.Budget` thêm `max_rounds` + "no-progress" + `max_same_decision_repeats`.
- Mở rộng `DelegationSpec` (`expected_output_schema`, `constraints`) — backward compatible.
- **Thay đổi gần core duy nhất**: capability `kind` (`model|read|effect`) + `idempotent` trong registry
  descriptor (vá luôn rủi ro retry trong `KNOWN_RISKS.md`; nền cho ToolView của MCP proposal).

## Scope — Out (từ chối tường minh)
- **Không** thêm method orchestration vào `core/kernel.py`; **không** đường thực thi LLM thứ hai;
  **không** global broadcast state. (Xem Core invariants.)
- Router chọn loại task / chọn department (E12); định nghĩa department/agent registry (E11/E09).
- Memory bền / ledger (E14); review gate người (E16); self-eval governance (E15).
- Live shared transcript (debate đồng thời) — để sau như tối ưu cục bộ, không phải nền tảng.

## Quyết định kiến trúc: round-based blackboard (không live transcript)
Trong một vòng, A/B/C chạy như **delegation cô lập**, O môi giới context **giữa các vòng**
(A vòng 1 → Broker → B vòng 2 thấy briefing của A). Lý do: checkpointable, observable,
scope-controlled, tái dùng nguyên delegation, không đẻ mô hình concurrency/state thứ hai.

## Dependencies
E05 (single-agent node/loop), E09 (roles & lenses → agent registry), E02 (json_gate/budget/
finish_gate), E06 (tools+safety), E04 (observability cho loop events). Thay đổi `kind` chạm E01/E06.

## Success metrics / Exit
- Một design/coding task nhỏ chạy LLM thật: O chọn team tối thiểu → loop hội tụ → `Finished` chỉ
  khi mọi AC `passed` có evidence; có artifact `task_loop_result`.
- **Không** agent nào nhận transcript đầy đủ — verify mỗi child session chỉ có Context Packet.
- Loop không bao giờ vô hạn: vòng không tiến triển → `blocked/failed`; max_rounds tôn trọng.
- Resume giữa loop hoạt động (SQLite là truth).

## Open questions
- AC `check_type` deterministic vs LLM-judge: tỷ lệ nào nên bắt buộc deterministic?
- Broker call có budget riêng thế nào (token/turn), và khi nào được phép condense vs giữ verbatim?
- Broker chọn "lát cắt store liên quan" để nạp cho mình bằng gì: heuristic (tag/recency) trước, hay
  sớm thêm semantic retrieval (E08)?
- Có cần `max_agents_per_round` cứng, hay để O tự giới hạn theo budget?

> Resolved: Context Broker là **một agent riêng**, **tự viết** briefing (không chỉ chọn-ref) —
> kèm 4 guardrail grounded/provenance/log/size-cap và scope-không-do-broker-cấp.
