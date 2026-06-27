# Case 02 — SupervisorContext + TaskLoop: Multi-Agent Orchestration Mediator

> Mediator dạng **orchestrator + Blackboard**: N agent KHÔNG bao giờ gọi nhau.
> Mọi phối hợp đi qua supervisor — O (Orchestrator) đọc Blackboard và quyết agent
> kế, Broker shape context, DelegationService chạy agent, agent ghi artifact trở
> lại Blackboard, Judge đọc Blackboard. Vì toàn bộ state tuần tự hoá được nên
> checkpoint & resume là tự nhiên.

---

## 1. Bối cảnh trong hex_agent

Tầng supervisor của hex_agent điều phối một **team agent nhiều vai** để giải một
task: chọn team → mỗi vòng quyết ai làm gì → chạy agent → gom kết quả → chấm tiêu
chí nghiệm thu (acceptance). Nếu để các agent gọi thẳng nhau, ta lại có N×N coupling
và mất khả năng replay/resume.

hex_agent giải bằng đúng tinh thần thalamus của bài gốc: **một mediator điều phối,
một Blackboard chia sẻ**. Các điểm đã mở và kiểm chứng:

- `supervisor/state.py:80-111` — `TaskLoopState`: Blackboard "round-based, not a live
  shared transcript". Docstring nói rõ "each worker turn appends an AgentTurn and any
  artifacts; the next o_decide reads the Blackboard, never the workers' raw sessions".
- `supervisor/graph.py:39-80` — `SupervisorContext`: giữ `orchestrator`, `broker`,
  `delegation_service`, `checkpoint`. Đây là ConcreteMediator.
- `supervisor/graph.py:87-104` — `compose_team`: O chọn team, ghi `session_plan` lên
  Blackboard.
- `supervisor/graph.py:108-123` — `o_decide`: O đọc `_state_view(state)` rồi phát 1
  decision.
- `supervisor/graph.py:137-211` — `run_round`: với mỗi assignment, Broker `write_packet`,
  rồi `ctx.delegation_service.delegate(...)`, agent trả artifacts được ghi vào Blackboard;
  `ctx.save(state)` checkpoint sau mỗi turn.
- `supervisor/graph.py:231-256` — `judge_acceptance`: đọc `acceptance_status` + artifacts,
  chỉ honour `passed` khi evidence_ids đều có trên Blackboard.
- `supervisor/loop.py:71-105` — `run_task_loop`: facade compose_team → `_drive`.
- `supervisor/loop.py:148-201` — `_drive`: vòng `o_decide → run_round/run_tool →
  judge_acceptance → guard`.
- `supervisor/orchestrator.py:21-39` — `ScriptedOrchestrator`: O xác định cho test
  offline (docstring class: "Deterministic O for offline tests"). Bất biến "O ...
  NEVER calls a tool directly" nằm ở docstring module `orchestrator.py` (`:3-4`).
- `supervisor/broker.py:24-55` — `DeterministicBroker`: shape context, "can never set
  or widen a worker's capability scope" (S10.14).

---

## 2. Trích đoạn code thật

ConcreteMediator giữ các colleague, từ `supervisor/graph.py:39-47`:

```python
@dataclass
class SupervisorContext:
    supervisor_session: KernelSession
    delegation_service: Any            # DelegationServicePort
    orchestrator: OrchestratorPort
    broker: BrokerPort
    agent_registry: Any | None = None  # E09 AgentRegistry (for the role catalog)
    store_slice_provider: StoreSliceProvider = default_store_slice
    checkpoint: Callable[[TaskLoopState], None] | None = None  # SQLite save (S10.10)
```

Mediator phân việc — agent KHÔNG gọi nhau, từ `supervisor/graph.py:152-179`:

```python
for assignment in decision.next_agent_calls:
    if assignment.agent_id in done_this_round:
        continue
    store_slice = ctx.store_slice_provider(assignment, state)
    packet = ctx.broker.write_packet(assignment=assignment, store_slice=store_slice)
    # The Broker shapes context only; it can never redirect a turn to another agent.
    if packet.target_agent_id != assignment.agent_id:
        raise PermissionError(...)
    ...
    # Scope comes ONLY from O's assignment — never from the Broker (S10.14).
    policy = DelegationPolicy(allowed_capabilities=frozenset(assignment.allowed_capabilities))
    result = ctx.delegation_service.delegate(
        ctx.supervisor_session, assignment.agent_id, packet.to_spec(), policy
    )
```

Vòng lặp mediator, từ `supervisor/loop.py:154-191`:

```python
while not state.is_terminal:
    if state.round_no >= state.max_rounds:
        _terminate(state, ctx, TaskLoopStatus.BLOCKED, "max_rounds reached"); break
    ...
    decision = o_decide(state, ctx, budget=budget)
    ...
    elif decision.decision == "continue":
        run_round(state, ctx, decision)
        judge_acceptance(state, ctx, decision)
    ...
    state.round_no += 1
    ctx.save(state)  # checkpoint at each round boundary (S10.10)
```

Authority check (colleague ngoài team bị chặn), từ `supervisor/graph.py:144-149`:

```python
selected = set(state.selected_agents)
for assignment in decision.next_agent_calls:
    if assignment.agent_id not in selected:
        raise PermissionError(
            f"Assignment targets agent '{assignment.agent_id}' that was not selected by composition."
        )
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Mediator | Thành phần trong hex_agent | File:line |
|---|---|---|
| **ConcreteMediator** | `SupervisorContext` (giữ orchestrator/broker/delegation/checkpoint) | `supervisor/graph.py:39-80` |
| **Blackboard (state chia sẻ)** | `TaskLoopState` (selected_agents, turns, artifacts, acceptance_checks) | `supervisor/state.py:80-111` |
| **Routing logic** | `Orchestrator` (`compose_team`, `decide`) — đọc state_view, quyết next | `supervisor/orchestrator.py:15-39`, `graph.py:108-123` |
| **Context shaper** | `Broker.write_packet` — briefing grounded, không đổi scope | `supervisor/broker.py:24-55` |
| **Executor (chạy 1 colleague)** | `DelegationService.delegate` | `supervisor/graph.py:177-179` |
| **Colleague (agent vai)** | agent trong `selected_agents` — sản sinh turn/artifact, không biết nhau | `supervisor/graph.py:152-209` |
| **Judge (đọc Blackboard)** | `judge_acceptance` | `supervisor/graph.py:231-256` |
| **Driver / facade** | `run_task_loop` + `_drive` | `supervisor/loop.py:71-201` |
| **Checkpoint / resume** | `encode_taskloop_state` / `decode_taskloop_state`, `resume_task_loop` | `supervisor/state.py:114-145`, `loop.py:108-145` |

Đây là Mediator + State-Machine + Blackboard (biến thể trong mục 2.4 bài gốc):
mediator giữ trạng thái phối hợp (round, acceptance), transitions = response logic.

---

## 4. Bản rút gọn chạy được

File: [`supervisor_taskloop_mediator.py`](./supervisor_taskloop_mediator.py) — chỉ
dùng thư viện chuẩn, chạy `python3 supervisor_taskloop_mediator.py` (exit 0).

Nó **mô phỏng**:
- `TaskLoopState` Blackboard + `encode_state`/`decode_state` (tuần tự hoá để
  checkpoint/resume).
- `SupervisorContext` ConcreteMediator + `compose_team`/`o_decide`/`run_round`/
  `judge_acceptance` + `_drive`/`run_task_loop`/`resume_task_loop`.
- `ScriptedOrchestrator` (O xác định), `DeterministicBroker` (shape-only),
  `DelegationService` (chạy agent là hàm thuần).
- Bất biến chính: agent chỉ thấy `packet`, ghi artifact vào Blackboard, KHÔNG gọi
  agent khác; authority check chặn agent ngoài team; Broker không đổi đích turn.

Nó **lược bỏ** (so với bản thật): LLM (`supervisor/llm.py`), SQLite checkpoint thật,
json-gate/repair + re-prompt, `Budget`/parse-error budget, event-envelope qua
`EventEmitter`, nhiều status (need_tool/waiting_tool/...), evidence-type gate
(`evidence_type_of`), và logic skip-turn-on-resume tinh vi.

Demo in ra: chạy 2-agent gather→summarize tới `finished`; bằng chứng summarize
grounded qua Broker chứ không gọi gather; authority check chặn agent ngoài team;
**checkpoint & resume** (lưu snapshot non-terminal sau gather rồi tiếp tục tới
finished); và **OPEN/CLOSED** — thêm agent thứ ba `critic` mà code agent cũ không đổi
một dòng (chỉ Orchestrator đổi quyết định).

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Mediator dễ phình thành God Object**: nếu Orchestrator gánh quá nhiều logic
  if/elif theo từng agent, ta cô đặc phức tạp. hex_agent chống lại bằng cách tách
  O (routing), Broker (context), Delegation (run), Judge (accept) thành các colleague
  riêng — đúng tinh thần "chia thalamus thành nhiều nuclei" (bài gốc 1.5).
- **Single point of failure**: supervisor chết = cả team đứng. Bù lại bằng Blackboard
  tuần tự hoá + checkpoint/resume.
- **Overhead vòng lặp + round-based**: không phải live transcript; agent giao tiếp gián
  tiếp qua artifact theo vòng, có độ trễ. Với 2-3 agent tương tác đơn giản, gọi thẳng
  rẻ hơn.
- **Khó nếu tương tác đối xứng kiểu broadcast**: khi chỉ cần "A xảy ra → ai quan tâm tự
  xử", Observer/Event Bus hợp hơn (bài gốc 1.4 + bảng so sánh 2.5).
- **Scale ngang (distributed)**: in-process mediator không thay được message broker.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `run_round` ép scope đến từ `assignment` của O chứ không từ Broker, và bất
   biến S10.14 ("Broker không có field scope") bảo vệ điều gì?
2. Vì sao `judge_acceptance` chỉ honour `passed` khi mọi `evidence_id` đã nằm trên
   Blackboard? Điều này nói gì về việc "ai giữ business state" theo cảnh báo anti-pattern
   của bài gốc?
3. Thêm agent thứ ba chỉ cần đổi quyết định của Orchestrator. Tính chất nào của
   Mediator (so với để agent gọi thẳng nhau) làm cho điều này thành Open/Closed?
