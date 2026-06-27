# CATALOG — Mọi occurrence của Entity / Value Object / Domain Event trong hex_agent

Bảng vét cạn các nơi pattern xuất hiện. Path tương đối so với root `/Users/uspro/Desktop/namnson/hex_agent`.
Số dòng đã mở file kiểm chứng. Cột "loại" cho biết building block; cột "độ rõ" theo plan discover.

| path:line | Loại building block | Mô tả | Độ rõ |
|---|---|---|---|
| `control/events.py:32-50` | Value Object | `Actor` — frozen VO "ai/cái gì gây ra event"; validate `type ∈ ACTOR_TYPES` + `id` non-empty ở `__post_init__`. **[Case 01]** | high |
| `control/events.py:53-82` | Value Object | `TraceContext` — frozen VO lineage tracing; `child()`/`new_root()` side-effect-free; validate `trace_id`/`span_id`. **[Case 01]** | high |
| `control/events.py:85-110` | Value Object | `RedactionInfo` — frozen VO mức hiển thị; `redacted_fields: tuple` (immutable thực sự); validate `level`. **[Case 01]** | high |
| `control/events.py:113-190` | Domain Event | `RuntimeEvent` — envelope event canonical; frozen; `event_id`/`created_at` auto; `schema_version`; `as_dict`/`from_dict`; validate ở `__post_init__`. **[Case 01]** | high |
| `control/commands.py:33-58` | Value Object | `IssuedBy` — frozen VO attribution (human/agent/system); validate "human cần user_id, agent cần agent_id". | high |
| `control/commands.py:61-106` | Value Object / Command | `RuntimeCommand` — frozen; `command_id`/`created_at`/`schema_version`; payload bất biến. Là **Command** (imperative), tách biệt với Domain Event — đúng phân biệt Lesson 36. | high |
| `control/commands.py:109-153` | Value Object | `CommandAck` — frozen VO biên nhận đồng bộ; status `received`/`rejected`; validate "rejected phải có lý do". | high |
| `control/checkpoint.py:27-93` | Entity-like (frozen) | `RuntimeCheckpoint` — frozen aggregate có `checkpoint_id`; lifecycle `waiting→resolved`; tiến hoá qua `with_status()` trả instance mới; timestamp `created_at`/`resolved_at`. | high |
| `control/permission.py:21-75` | Value Object | `Permission` — frozen VO capability profile; `patched()` trả VO mới không mutate (side-effect-free); validate `effective_from`. | high |
| `core/schemas.py:11-25` | Value Object | `TaskEnvelope` — frozen VO contract task; `task_id` auto; `as_dict`/`from_dict`. | high |
| `core/schemas.py:28-33` | Value Object | `ToolRequest` — frozen VO; `request_id` auto. | high |
| `core/schemas.py:36-56` | Value Object | `ToolCallContext` — frozen VO "session lineage + scope"; `event_fields()` side-effect-free. | high |
| `core/schemas.py:63-111` | Value Object | `CapabilityResult` — frozen VO envelope mọi tool call trả về; `from_raw()`/`as_dict()` side-effect-free. | high |
| `core/schemas.py:114+` | Value Object | `FeatureDescriptor` và các VO contract tiếp theo (DelegationSpec, DelegationPolicy, DelegationRequest, ArtifactEnvelope, DelegationProgress, DelegationResult) — đều frozen, validate qua `__post_init__`/`from_dict`. | high |
| `core/session.py:15-46` | Value Object | `SessionIdentity` — frozen VO lineage (session_id, parent_session_id, depth); `as_dict`/`from_dict`. | high |
| `core/session.py:49-102` | Entity | `KernelSession` — `@dataclass` (mutable) Entity; lifecycle `created→active→closed` qua `_closed`; sở hữu `SessionIdentity` (VO) + `StateStore`. | high |
| `core/registry.py:10-18` | Value Object | `ToolDescriptor` — frozen VO metadata capability (kind/idempotent/risk). | medium |
| `core/registry.py:43+` (class `CapabilityRegistry`, `freeze()` ở `60`) | Entity | Registry mutable quản lý đăng ký tool; `freeze()` enforce immutability sau khi kernel active. | medium |
| `decompose_agent/node.py:50-99` | Value Object | `DoneWhen` — frozen VO một tiêu chí `{check, params, artifact}`; validate + path-jail; `from_dict` chống verdict-forgery. **[Case 02]** | high |
| `decompose_agent/node.py:102-176` | Entity | `Node` — Entity có `id`; lifecycle `pending→active→done`; frozen + tiến hoá qua `dataclasses.replace()`; sở hữu `tuple[DoneWhen]`. **[Case 02]** | high |
| `decompose_agent/gates.py:30-34` | Value Object | `CheckResult` — frozen VO kết quả một check. | high |
| `decompose_agent/gates.py:36-42` | Value Object | `CriterionVerdict` — frozen VO verdict của một criterion. | high |
| `decompose_agent/gates.py:44-53` | Value Object | `Verdict` — frozen VO aggregate; `run_checks()` là constructor duy nhất; không bao giờ bị caller mutate. | high |
| `decompose_agent/accept.py:56-62` | Value Object | `Accept` — frozen VO union "decomposition hợp lệ"; `ok` luôn True. | medium |
| `decompose_agent/accept.py:65-83` | Value Object | `Reject` — frozen VO union "decomposition bị từ chối"; chứa lý do machine-readable; `ok` luôn False; `code` derive side-effect-free. | medium |
| `decompose_agent/worker.py:69-86` | Value Object | `FourCell` — frozen VO đóng gói ngữ cảnh (identity, breadcrumb, node, journal_tail); `cells()`/`render()` side-effect-free. | medium |
| `supervisor/state.py:28-49` | Entity | `AcceptanceCheck` — `@dataclass` (mutable) Entity có `id`; lifecycle `pending→passed/failed`; thuộc `TaskLoopState`. | high |
| `supervisor/state.py:52-77` | Value Object-like | `AgentTurn` — bản ghi một lượt (round_no, agent_id, packet_id); `as_dict`/`from_dict`. | high |
| `supervisor/state.py:80-111` | Entity | `TaskLoopState` — `@dataclass` (mutable) Entity có id; lifecycle qua `status`; method quản lý state; sở hữu list `AcceptanceCheck`/`AgentTurn`. | high |
| `drag_from_zero/dragzero/events.py:12-34` | Domain Event (taxonomy) | `EventType` — Enum tên event past-tense: `ROOT_TASK_CREATED`, `TASK_STARTED`, `PLAN_PRODUCED`, `TOOL_CALLED`, `TASK_COMPLETED`,... | high |
| `drag_from_zero/dragzero/events.py:37-43` | Domain Event | `Event` — frozen VO/Domain Event với `seq`, `task_id`, `agent_id`, `payload`. | high |
| `drag_from_zero/dragzero/events.py:46-92` | (ledger) | `EventLog` — append-only ledger bất biến của các `Event`; `append()` stamp `seq` qua `replace()`; `replay()` rebuild từ disk. | high |

---

## Ghi chú về số dòng

- Các flagship (`control/events.py`, `decompose_agent/node.py`) đã được mở và xác nhận từng dòng cho Case 01/02.
- `decompose_agent/node.py` từng được thêm `CMD_CHECKS`/`expect_code` SAU lần viết docs đầu tiên, làm mọi tham chiếu lệch 2-6 dòng; bảng + Case 02 + docstring file `.py` đã được re-sync khớp file thật hiện tại: `assert_safe_relpath` `33-47`, `DoneWhen` `50-99`, `Node` `102-176`, `FORBIDDEN_VERDICT_KEYS` `20`, `VALID_STATUSES/KINDS/REDUCE_OPS` `28-30`.
- Trong plan discover có vài số dòng lệch nhẹ (vd `Actor` được nêu `32-83`, thực tế block `Actor` là `32-50`; `RuntimeEvent.__post_init__` được nêu `113-151`, thực tế class kéo dài `113-190`). Bảng trên đã sửa cho khớp file thật.
- `decompose_agent/accept.py`: `Accept` thực tế ở `56-62`, `Reject` ở `65-83` (plan ghi gộp `32-59` — đã sửa cho khớp file thật).
- `decompose_agent/gates.py`: `CheckResult` `30-34`, `CriterionVerdict` `36-42`, `Verdict` `44-53`. Theo quy ước, các khoảng này trỏ tới dòng decorator `@dataclass` (vd `CheckResult` `@dataclass` ở `31`, `class` ở `32`); tương tự `core/registry.py:10-18` `ToolDescriptor` trỏ decorator `10`, `class` `11`.
