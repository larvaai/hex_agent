# E10 — Build Plan (các bước trước khi code)

> Mục tiêu: đủ điều kiện để code an toàn. Theo nguyên tắc repo: **interface trước, nội dung sau**.
> Đọc kèm `PRD.md`, `stories.md`, `acceptance.md`, `flow_taskloop.mermaid`.

## 0. Readiness (đã verify trên code)

| Dep | Trạng thái | Ghi chú |
|---|---|---|
| E02 discipline | ✅ | `discipline/` (json_gate, Budget, finish_gate, condense) — tái dùng cho loop guard + AC gate |
| E04 observability | ✅ | `observability/` — thêm topic `loop.*` |
| E05 single-agent graph | ✅ | `graph/` — worker chạy trên đây qua delegation adapter |
| E06 tools + safety | ✅ | `toolbox/` + `safety/` — tool qua `execute_tool` |
| Delegation chokepoint | ✅ | `DelegationManager` + `DelegationServicePort` + `delegation/registry.py` |
| Delegation adapter | ⚠️ v1 | `adapters/agents/langgraph_agent.py`: `InMemorySaver`, **no recursion, no child persistence** |
| **E09 agent registry/roles** | ❌ **BLOCKER** | chưa tồn tại; chỉ có 1 target `agent:general`. E10 cần A/B/C có role+prompt+scope |

**Quyết định sequencing:** không build full E09 trước. Slice 1 của E10 chạy **offline với scripted
agents** (tái dùng `adapters/agents/scripted.py`) qua một **agent-registry seam tối thiểu** → chứng
minh plumbing loop/blackboard/AC-gate **không cần LLM**. E09 thật land trước Slice 2. Cách này cho E10
khởi động song song E09 ở mức contract, đúng kỷ luật "deterministic smoke offline trước".

## 1. Contracts / seams cần lock (interface trước)

### 1a. Agent registry tối thiểu (tiền-E09, đặt ở `agents/registry.py`)
```python
@dataclass(frozen=True)
class RoleSpec:
    agent_id: str                 # "planner_agent"
    role: str                     # mô tả vai trò 1 dòng
    system_prompt: str
    default_scope: frozenset[str] # capability mặc định của role (least privilege)

class AgentRegistry:              # map agent_id -> DelegationPort (qua delegation registry)
    def list_roles(self) -> tuple[RoleSpec, ...]: ...
    def get(self, agent_id: str) -> RoleSpec: ...
```
> E09 thật sẽ thay phần "role config" này; seam giữ nguyên để O đọc `available_agents`.

### 1b. Mở rộng `DelegationSpec` (`core/schemas.py`) — backward compatible
```python
@dataclass(frozen=True)
class DelegationSpec:
    objective: str
    input_context: dict = {}
    expected_output_schema: dict = {}   # MỚI
    constraints: tuple[str, ...] = ()    # MỚI
```

### 1c. Context Packet (output của Broker; map vào DelegationSpec)
```python
@dataclass(frozen=True)
class ContextPacket:
    target_agent_id: str
    objective: str
    briefing: str                 # Broker TỰ VIẾT
    source_ids: tuple[str, ...]   # provenance: artifact_id/turn_id đã dùng
    expected_output_schema: dict
    # scope KHÔNG nằm ở đây — do O/policy đặt qua DelegationPolicy
    def to_spec(self) -> DelegationSpec: ...   # briefing+source_ids -> input_context
```

### 1d. Orchestrator decision (Agent O; parse qua json_gate như E05)
```python
@dataclass(frozen=True)
class AgentAssignment:
    agent_id: str; objective: str; scope_of_work: str
    allowed_capabilities: tuple[str, ...]
@dataclass(frozen=True)
class OrchestratorDecision:
    decision: str                 # continue|need_tool|finished|blocked|failed
    selected_agents: tuple[str, ...]
    next_agent_calls: tuple[AgentAssignment, ...]
    tool_requests: tuple[dict, ...]
    acceptance_status: tuple[AcceptanceCheck, ...]
    progress_made: bool
    reason: str
    final_output: dict | None
def parse_decision(raw: str) -> OrchestratorDecision: ...  # reuse discipline.parse_action pattern
```

### 1e. Blackboard / TaskLoopState (`supervisor/state.py`, serializable như AgentState)
```python
class TaskLoopStatus(str, Enum):
    CREATED="created"; TEAM_SELECTED="team_selected"; IN_DISCUSSION="in_discussion"
    WAITING_TOOL="waiting_tool"; REVIEWING_AC="reviewing_ac"
    FINISHED="finished"; BLOCKED="blocked"; FAILED="failed"
@dataclass
class AcceptanceCheck:
    id: str; text: str; status: str = "pending"; evidence_ids: list[str] = []
@dataclass
class AgentTurn:
    round_no: int; agent_id: str; packet_id: str
    output_summary: str; artifact_ids: list[str] = []
@dataclass
class TaskLoopState:               # = "Blackboard"
    session_id: str; task_id: str; status: str
    selected_agents: list[str]; acceptance_checks: list[AcceptanceCheck]
    round_no: int = 0; max_rounds: int = 5
    turns: list[AgentTurn] = []; artifacts: dict = {}; tool_results: dict = {}
    final_output: dict | None = None
# + encode/decode_taskloop_state() đối xứng graph/state.py
```

### 1f. Capability kind (thay đổi gần-core duy nhất; `core/registry.py`)
```python
def register_tool(self, name, executor, *, feature_name=None,
                  kind="tool", idempotent=False, risk="low"): ...
# ToolResolution thêm field descriptor; resolve trả descriptor để retry/policy đọc kind/idempotent
```

### 1g. Supervisor graph nodes (`supervisor/graph.py`, ký như graph/nodes.py)
`compose_team, o_decide, run_round, judge_acceptance, tool, finish, fail` —
`(state, *, session, agent_registry, delegation_service, broker) -> dict`. Public facade
`supervisor/loop.py::run_task_loop(...)` (giống `orchestrator/loop.py`).

## 2. File layout dự kiến
```
agents/registry.py                     # 1a (seam tiền-E09)
supervisor/{__init__,state,orchestrator,broker,graph,loop}.py
core/schemas.py    (+ 1b)   core/registry.py (+ 1f)
config/            roster + workflow template + acceptance config
tests/test_{supervisor_loop,context_broker,acceptance_gate,loop_guard,capability_kind}.py
```

## 3. AC → test map (E19)

| AC | Test | Loại |
|---|---|---|
| S10.1 team composition | `test_supervisor_loop::test_compose_minimal_team` | det |
| S10.2 bounded loop | `test_supervisor_loop::test_round_delegates_each_agent` | det |
| S10.3 scoped packet | `test_supervisor_loop::test_child_has_no_parent_transcript` | det |
| S10.4 broker agent | `test_context_broker::test_packet_has_source_ids_and_logged` | det |
| S10.5 worker=delegation | `test_supervisor_loop::test_turn_runs_via_delegate_scope_subset` | det |
| S10.6 acceptance gate | `test_acceptance_gate::test_no_finish_without_evidence` | det |
| S10.7 loop guard | `test_loop_guard::test_no_progress_fails` / `test_max_rounds` | det |
| S10.8 structured decision | `test_supervisor_loop::test_bad_json_repaired_then_fail` | det |
| S10.9 tool via chokepoint | `test_supervisor_loop::test_need_tool_crosses_execute_tool` | det |
| S10.10 checkpoint/resume | `test_supervisor_loop::test_resume_mid_loop` | det (Slice 3) |
| S10.11 reuse E05 substrate | `test_supervisor_loop::test_worker_uses_e05_graph` | struct |
| S10.12 carried discipline | `test_acceptance_gate::test_finish_gate_in_worker` | det |
| S10.13 capability kind | `test_capability_kind::test_effect_not_retried` | det |
| S10.14 broker no scope | `test_context_broker::test_broker_cannot_widen_scope` | det |

## 4. Build slices + DoD

| Slice | Nội dung | DoD (AC xanh) |
|---|---|---|
| **S0 prep** | seam stubs (1a–1g) không logic + test skeleton (skip/xfail) | import sạch; `pytest` xanh (skips) |
| **S1 offline** | scripted O + scripted agents; loop/blackboard/AC-gate/loop-guard; **no LLM/network** | S10.1,2,3,5,6,7,8,9,11,14 xanh offline; có `task_loop_result` |
| **S2 live** | O + Broker là `llm.chat`; ContextPacket từ store thật; judge LLM | task nhỏ LLM thật hội tụ; S10.4 + judge thực |
| **S3 hardening** | capability `kind`+retry-fix; checkpoint/resume mid-loop (cần adapter SQLite); `loop.*` events | S10.10,12,13 xanh |

> S3 cần nâng delegation adapter từ `InMemorySaver` → SQLite (hiện v1 disabled). Tách thành sub-task.

## 5. Quyết định đã chốt (khỏi hỏi lại)
- Broker = **agent riêng**, **tự viết** briefing, 4 guardrail (grounded/provenance/log/size-cap), **không cấp scope**.
- Trong 1 vòng: agent chạy **tuần tự, cô lập** (round-based blackboard, không live transcript).
- `judge_acceptance` = **node riêng**; `loop guard` = **gate cơ học** tách khỏi O.
- `need_tool` do **O** phát; worker không tự gọi tool trong lượt (Slice 1–2).
- Core giữ mỏng; thay đổi gần-core **chỉ** là capability `kind`.

## 6. Bất biến phải giữ khi code (từ KNOWN_RISKS + review)
Một chokepoint `execute_tool`; không global state; child cô lập + scope ⊆ parent; SQLite = truth;
Broker không nới quyền; state phải serializable (đừng nhét object vào `TaskLoopState`).
