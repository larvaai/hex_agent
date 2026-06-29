---
phase: 1
title: "Backend Contracts — TaskLoopSnapshot + CommandAck"
status: pending
plan: 260626-0212-e21-control-plane-ui-fake-backend
created: 2026-06-26
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 1 — Backend Contracts

## Overview

Tạo **2 shape còn thiếu** để cả 5 shape UI tiêu thụ đều là dataclass thật trong
`control/` (đóng R1). Không phụ thuộc phase nào; là nền cho Phase 2 (gen TS) và Phase 3
(fake serialize từ đây). **Không** wire vào supervisor live (drop-in sau).

- `TaskLoopSnapshot` (read-model Graph/Inspector vẽ lên) — AC **S21.9**.
- `CommandAck` (response của `POST /api/commands`) — AC **S21.15** ([acceptance.md:62](../../../docs/spec/active/E21-realtime-control-plane/acceptance.md)).

Vì sao dataclass (không pydantic): khớp repo — mọi contract `control/` là `@dataclass(frozen=True)`
với `__post_init__` validate + `as_dict`/`from_dict` ([control/events.py:1-12](../../../control/events.py)).
"Invalid không thể tồn tại" là pattern đã có; theo đúng nó (DRY).

## Files

**Create:**
- `control/snapshot.py` — `TaskLoopSnapshot` + `AgentView` + `build_snapshot(events, *, session_id) -> TaskLoopSnapshot`.
- `tests/test_control_snapshot.py` — test S21.9.

**Modify:**
- `control/commands.py` — thêm `@dataclass(frozen=True) CommandAck` cạnh `RuntimeCommand` ([commands.py:52](../../../control/commands.py)); thêm `as_dict`/`from_dict`.
- `tests/test_control_contracts.py` — thêm CommandAck roundtrip + reject-ack.
- `tests_audit/test_contract_roundtrips.py` — thêm snapshot + ack vào bộ roundtrip ([tests_audit/test_contract_roundtrips.py](../../../tests_audit/test_contract_roundtrips.py)).

### `TaskLoopSnapshot` v1 field-set (D3 — derive từ spec B2 + state.py + contracts.py)
```
TaskLoopSnapshot:
  session_id: str
  status: str                      # TaskLoopStatus value (state.py:14-23)
  round_no: int
  orchestrator: {last_decision: str, reason: str}   # OrchestratorDecision.decision/reason (contracts.py:55-61)
  agents: list[AgentView]
  pending_agent_calls: list[{agent_id, objective, target_kind}]  # AgentAssignment (contracts.py:45-51)
  tool_calls: list[{tool, status, risk_level|None}]
  checkpoints: list[dict]          # RuntimeCheckpoint.as_dict() (checkpoint.py:70) — modal đọc waiting
  acceptance_status: list[{id, text, status}]        # AcceptanceCheck (state.py:29-49)
  last_updated_at: str

AgentView:                         # đủ cho Graph node + Inspector (S21.18/S21.20)
  agent_id: str
  role: str
  status: str                      # pending|waiting|running|done|failed  (spec B2 enum, 01_BACKEND:20)
  round_no: int
  allowed_tools: list[str] = []    # OPTIONAL — chỉ điền khi có event mang permission (F6)
  last_output_summary: str = ""    # AgentTurn.output_summary (state.py:57) — đã redact
  context_packet: dict = {}        # ui_payload-redacted; {} khi chưa có (F6)
  permission: dict | None = None   # Permission.as_dict() (permission.py:52); None khi chưa bind (F6)
```
> **F6 (red-team):** `Permission` KHÔNG có `agent_id` ([permission.py:19-27](../../../control/permission.py))
> và chưa event nào bind permission→agent ở backend thật → 3 field trên **optional**,
> chỉ điền khi fixture phát event mang permission (vd `permission.changed`). Inspector
> render "—" khi None thay vì đoán. Binding live = drop-in sau (BACKLOG).

**Quy tắc fold — build_snapshot fold trên `loop.*` event supervisor PHÁT SẴN (red-team F1/F11):**
> Verify: `grep` supervisor chỉ phát `loop.team_composed/decision/turn/tool/parse_error`
> ([supervisor/graph.py:102,120,207](../../../supervisor/graph.py)) — **0 `agent.*`**.
> Fold trên `agent.*` (chưa ai phát) = snapshot rỗng lúc nối thật. Nên fold `loop.*`:

| Event (real, [runtime_event_types.yaml:72-79](../../../config/runtime_event_types.yaml)) | Cập nhật snapshot |
|---|---|
| `loop.team_composed` | `selected_agents` → mỗi agent `status=pending` (baseline) |
| `loop.decision` | `orchestrator.last_decision`+`reason`; `next_agent_calls` → agent đó `status=running`; `pending_agent_calls` |
| `loop.turn` | agent của turn → `status=done` + `last_output_summary` (AgentTurn, state.py:53-58) |
| `loop.tool` | thêm vào `tool_calls` (tool/status/risk) |
| `loop.parse_error` | (không đổi status; ghi nhận) |
| `loop.finished/blocked/failed` | `TaskLoopState.status` |
| `checkpoint.reached` (waiting) | thêm vào `checkpoints`; agent liên quan `status=waiting` |

- Status derive: pending (selected) → running (trong decision.next_agent_calls mới nhất) →
  done (đã có turn). Khớp kịch bản S21.9 "A done, B running, C pending".
- Snapshot chỉ đọc `ui_payload` (đã redact) → **không** chứa raw secret (assert S21.9).
- **F14:** `control/snapshot.py` vào MAP.md (docstring §5); `tools/*` KHÔNG (deny-list [gen_map.py:8]) — không claim MAP phủ tools.

### `CommandAck` (D1)
```
CommandAck:
  command_id: str
  status: str                      # "received" | "rejected"   (ACCEPT_STATUSES frozenset)
  seq: int | None = None           # seq của event command.received (correlate vào stream)
  rejection_reason: str | None = None
  created_at: str = field(default_factory=_utc_now)
  __post_init__: command_id non-empty; status ∈ {received,rejected};
                 status=="rejected" ⇒ rejection_reason non-empty (đối xứng IssuedBy guard, commands.py:35)
```

## TDD

### Tests Before (RED — chạy phải đỏ vì shape chưa tồn tại)
- [ ] `test_command_ack_roundtrip`: `CommandAck(...).as_dict()` → `from_dict` giữ nguyên field; ack `received` không cần reason, ack `rejected` không reason ⇒ `ControlContractError`. **Khoá:** shape ACK đúng AC S21.15.
- [ ] `test_build_snapshot_status_graph` (S21.9): chuỗi **`loop.*`** event (`loop.team_composed`[A,B,C] → `loop.turn`[A] → `loop.decision`[next=B]), `build_snapshot` cho A=done, B=running, C=pending + `orchestrator.last_decision` + `pending_agent_calls`. **Khoá:** Graph vẽ đúng từ event backend THẬT phát (F1).
- [ ] `test_build_snapshot_no_raw_secret` (S21.9): event có `payload.api_key` nhưng đã qua `Redactor().apply()` → snapshot **không** chứa giá trị secret, chỉ `[REDACTED]`.
- [ ] Run → FAIL (NameError/ImportError: chưa có `control.snapshot` / `CommandAck`).

### Implement
1. `control/commands.py`: thêm `ACCEPT_STATUSES = frozenset({"received","rejected"})`, `CommandAck` dataclass theo D1, `as_dict`/`from_dict`. Docstring giữ phong cách module ([commands.py:1-7](../../../control/commands.py)).
2. `control/snapshot.py`: docstring `"""TaskLoopSnapshot read-model … Epic E21 (S21.9)."""`; `AgentView` + `TaskLoopSnapshot` (frozen dataclass, `as_dict`/`from_dict`); `build_snapshot(events, *, session_id)` fold theo bảng trên. Chấp nhận `events` là `Iterable[dict | RuntimeEvent]` (fake truyền dict từ jsonl).
3. Min code để 3 test xanh — không thêm field ngoài v1 set (YAGNI).

### Tests After (xanh)
- [ ] 3 test trên xanh.
- [ ] `tests_audit/test_contract_roundtrips.py` mở rộng phủ `CommandAck` + `TaskLoopSnapshot` (no-weakened-assertion, giống các contract khác).

### Regression Gate
`python -m pytest tests/ tests_audit/ -q && python run_smoke.py`  → phải PASS + `CORE_AGENT_SMOKE_OK`.
(Manifest/`verify_install` N/A — không chạm `harness/`.)

## Success
- [ ] `python -c "from control.snapshot import TaskLoopSnapshot, build_snapshot; from control.commands import CommandAck"` không lỗi.
- [ ] `build_snapshot` trên fixture event-stream cho graph A=done/B=running/C=pending (test xanh, không phải narration).
- [ ] Snapshot + ACK roundtrip lossless; ACK rejected bắt buộc reason.
- [ ] `MAP.md` regenerate có dòng cho `control/snapshot.py` (docstring dòng đầu đúng format, code-standards §5).

## Risks
- **Field-set sai/thiếu cho Inspector** (tb): `AgentView` đã gồm role/allowed_tools/last_output/permission đủ S21.20 — nếu thiếu, Inspector (Phase 6) phải đoán. Mitigation: map thẳng từ AC S21.20 [acceptance.md:80](../../../docs/spec/active/E21-realtime-control-plane/acceptance.md).
- **build_snapshot ký hiệu khác backend live sau** (thấp): chỉ nhận event-stream (B2 "derived") → khi supervisor emit thật, cùng event_type → cùng fold. Không phụ thuộc `TaskLoopState` in-memory.
