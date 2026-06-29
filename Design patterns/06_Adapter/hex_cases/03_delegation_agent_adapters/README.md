# Case 03 — Hai Delegation Agent (Scripted + LangGraph) sau cùng một `DelegationPort`

> Đây là Adapter ở quy mô kiến trúc hexagonal: **core sở hữu port**, nhiều adapter cài đặt
> nó. Một adapter là bản thật (LangGraph streaming), một adapter là bản giả tất định
> (Scripted) cho test. Core không hề biết mình đang nói chuyện với bản nào.

---

## 1. Bối cảnh trong hex_agent

Một agent có thể **ủy thác (delegate)** một mục tiêu con cho một agent khác. Bộ điều phối
delegation trong core cần một biên ổn định để gọi agent con, mà không bị trói vào việc agent
con được hiện thực bằng LangGraph, bằng LLM, hay bằng một kịch bản ghi sẵn.

Giải pháp: core định nghĩa `DelegationPort`, và có **hai adapter**:
- `ScriptedDelegationAgent` — test double tất định: phát ra một dãy artifact ghi sẵn, chạy
  cục bộ, không cần LLM. Dùng cho test nhanh + smoke kiến trúc.
- `LangGraphDelegationAgent` — bản production: stream qua một đồ thị langgraph thật, mỗi bước
  mới của agent được dịch thành một `ArtifactEnvelope`.

File:line thật (đã mở kiểm chứng):
- `core/ports.py:32-45` — `DelegationPort` (Protocol): `name`, `can_handle(target) -> bool`,
  `run(request, child_session, progress_sink) -> DelegationResult`.
- `adapters/agents/scripted.py:17-59` — `ScriptedDelegationAgent`: bọc `self.artifacts` (list),
  lặp + gọi `progress_sink`, trả `DelegationResult`.
- `adapters/agents/langgraph_agent.py:21-95` — `LangGraphDelegationAgent`: bọc graph
  (`graph.stream(...)` ở dòng 57-80), dịch mỗi bước thành `ArtifactEnvelope(kind="agent_step")`.
- `adapters/agents/__init__.py:1-4` — xuất **cả hai** adapter (chứng tỏ chúng thay thế nhau).
- `core/schemas.py:132-252` — DTO: `DelegationSpec`, `DelegationPolicy`, `DelegationRequest`,
  `ArtifactEnvelope`, `DelegationProgress`, `DelegationResult`.

---

## 2. Trích đoạn code thật

Target interface — `core/ports.py:32-45`:

```python
@runtime_checkable
class DelegationPort(Protocol):
    name: str

    def can_handle(self, target: str) -> bool:
        ...

    def run(
        self,
        request: DelegationRequest,
        child_session: "KernelSession",
        progress_sink: ProgressSink,
    ) -> DelegationResult:
        ...
```

Adapter giả lặp list ghi sẵn — `adapters/agents/scripted.py:33-47`:

```python
for sequence, payload in enumerate(self.artifacts, start=1):
    artifact = ArtifactEnvelope(
        artifact_id=uuid.uuid4().hex,
        kind=str(payload.get("kind") or "scripted"),
        payload=dict(payload),
    )
    emitted.append(artifact)
    progress_sink(DelegationProgress(
        delegation_id=request.delegation_id, sequence=sequence,
        event_id=uuid.uuid4().hex, artifact=artifact,
    ))
```

Adapter thật stream qua graph — `adapters/agents/langgraph_agent.py:57-72`:

```python
for values in graph.stream(initial, config, stream_mode="values"):
    final_state = values
    step = budget_from_state(values).steps
    if step <= emitted_step:
        continue
    emitted_step = step
    artifact = ArtifactEnvelope(
        artifact_id=uuid.uuid4().hex, kind="agent_step",
        payload={"step": step, "action": dict(values.get("last_action") or {}),
                 "status": values.get("status", "running")},
    )
```

Hai bên có nội tạng khác hẳn (list vs graph streaming) nhưng đều thỏa cùng một `DelegationPort`
và đều trả `DelegationResult`.

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Adapter (GoF)        | Thành phần trong hex_agent                                              |
|------------------------------|------------------------------------------------------------------------|
| **Target** (protocol do core sở hữu) | `DelegationPort` — `core/ports.py:32-45`                       |
| **DTO**                      | `DelegationRequest/Result/Progress`, `ArtifactEnvelope` — `core/schemas.py:132-252` |
| **Concrete Adapter #1** (giả) | `ScriptedDelegationAgent` — `adapters/agents/scripted.py:17-59` (composition: `artifacts`) |
| **Concrete Adapter #2** (thật) | `LangGraphDelegationAgent` — `adapters/agents/langgraph_agent.py:21-95` (composition: graph) |
| **Adaptee #1**               | một `list[dict]` ghi sẵn                                                |
| **Adaptee #2**               | đồ thị `langgraph` (`graph.stream`)                                     |
| **Client**                   | bộ điều phối delegation trong core                                      |

---

## 4. Bản rút gọn chạy được

File: [`delegation_agent_adapters.py`](./delegation_agent_adapters.py) — `python3 delegation_agent_adapters.py`.

Mô phỏng:
- `DelegationPort` (Protocol, `runtime_checkable`) + bộ DTO rút gọn (`DelegationRequest`,
  `ArtifactEnvelope`, `DelegationProgress`, `DelegationResult`, `KernelSession`).
- `ScriptedDelegationAgent` — giữ nguyên vai trò gốc, bọc list artifact.
- `GraphDelegationAgent` — bọc `_FakeGraph` (generator stdlib yield "state" theo từng bước),
  giữ đúng hình dạng stream-rồi-dịch-thành-artifact của bản LangGraph thật.
- `DelegationOrchestrator` (client) — chọn agent bằng `can_handle`, gọi `run` với một
  `progress_sink` thu log; không biết agent là loại nào.
- Demo + **assert**: cả hai adapter là `DelegationPort`; chạy cùng một request qua từng adapter
  cho ra cùng `outcome="success"`, cùng số artifact, cùng số progress event, cùng kiểu
  `DelegationResult` → chứng minh substitutability.

Lược bỏ:
- `langgraph` thật, `InMemorySaver`, `build_agent_graph`, prompt, `Budget`, LLM →
  thay bằng `_FakeGraph` chạy vài bước tất định.
- `uuid.uuid4().hex` → bộ đếm tất định để output ổn định, dễ đọc.
- Recursive delegation, persistence (vốn đã tắt trong v1 của bản thật).

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Phải đồng bộ hợp đồng giữa các adapter**: nếu `LangGraphDelegationAgent` âm thầm đổi cách
  điền `summary`/`outcome`, test dựa trên `ScriptedDelegationAgent` sẽ không bắt được khác
  biệt đó — fake quá xa bản thật là cái bẫy. Cần test hợp đồng (contract test) cho cả hai.
- **Chỉ có một loại agent duy nhất, mãi mãi?** Thì port + hai adapter là thừa; cứ gọi thẳng.
- Adapter chỉ nên **dịch và phát progress**, không nên nhét logic điều phối (chọn agent nào,
  retry delegation) vào trong — đó là việc của client/orchestrator.

---

## 6. Câu hỏi tự kiểm tra

1. `core` có import `langgraph` không? Nhờ đâu mà việc thay `LangGraphDelegationAgent` bằng
   `ScriptedDelegationAgent` trong test không đụng tới một dòng code nào của core?
2. Cả hai adapter đều gọi `progress_sink(...)` cho mỗi bước. Việc client truyền vào
   `progress_sink` (thay vì adapter tự ghi log) thể hiện nguyên lý thiết kế nào?
3. Nếu thêm một adapter thứ ba (vd `HttpRemoteAgent` gọi agent qua REST), bạn cần thay đổi gì
   ở `core/ports.py` và ở client? So với việc client phải `if/else` theo loại agent.
