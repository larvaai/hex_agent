# Case 03 — DelegationPort: LangGraphDelegationAgent & ScriptedDelegationAgent thay thế cho nhau

> LSP ở tầng kiến trúc agent: một agent production chạy LangGraph và một agent test phát artifact
> hardcode cùng trả CÙNG MỘT envelope `DelegationResult`. `TaskLoop` gom artifact y hệt, và quan trọng:
> **task fail KHÔNG raise — báo qua `outcome='failed'`**, nên caller không cần `try/except` đặc thù.

---

## 1. Bối cảnh trong hex_agent

Supervisor (E10) ủy thác công việc cho agent con qua port `DelegationPort` (`core/ports.py:32-45`).
Có hai impl chính:

- **`LangGraphDelegationAgent`** (`adapters/agents/langgraph_agent.py:21-95`): production — dựng graph,
  `graph.stream(...)`, mỗi step phát một `ArtifactEnvelope` + gọi `progress_sink`, cuối cùng map
  `status` → `outcome`.
- **`ScriptedDelegationAgent`** (`adapters/agents/scripted.py:17-59`): test/smoke — phát một hàng đợi
  artifact định sẵn, `outcome='success'` tất định.

Điểm contract cốt lõi: `run()` **luôn trả `DelegationResult`**, `outcome ∈ {"success", "failed"}`
(nhị phân), và **task thất bại bình thường KHÔNG ném exception** — nó set `outcome='failed'`
(`langgraph_agent.py:82-95`). Nhờ vậy `TaskLoop` chỉ đọc envelope; không phải biết agent là loại gì.
Test `tests/test_supervisor_loop.py:144-147` xác nhận `isinstance(LangGraphDelegationAgent(...), DelegationPort)`.

---

## 2. Trích đoạn code thật

Abstraction (`core/ports.py:32-45`):

```python
@runtime_checkable
class DelegationPort(Protocol):
    name: str
    def can_handle(self, target: str) -> bool: ...
    def run(self, request: DelegationRequest, child_session: "KernelSession",
            progress_sink: ProgressSink) -> DelegationResult: ...
```

Production map status → outcome, KHÔNG raise khi failed (`adapters/agents/langgraph_agent.py:82-95`):

```python
status = str(final_state.get("status") or "failed")
return DelegationResult(
    delegation_id=request.delegation_id,
    parent_task_id=request.parent_task_id,
    outcome="success" if status == "completed" else "failed",
    artifacts=tuple(artifacts),
    summary={...},
    error=final_state.get("error") if status != "completed" else None,
)
```

Test xác nhận substitutability (`tests/test_supervisor_loop.py:144-147`):

```python
def test_worker_uses_e05_delegation_substrate():
    # Worker turns delegate through a DelegationPort; the E05 graph adapter IS one,
    assert isinstance(LangGraphDelegationAgent("agent:general"), DelegationPort)
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò LSP | Thành phần trong hex_agent | File:line |
|---|---|---|
| Abstraction `T` (contract) | `DelegationPort` Protocol | `core/ports.py:32-45` |
| Caller (depend on `T`) | `TaskLoop` (supervisor) gọi `run()` | `tests/test_supervisor_loop.py:39-49, 144-147` |
| Subtype `S₁` (production) | `LangGraphDelegationAgent` | `adapters/agents/langgraph_agent.py:21-95` |
| Subtype `S₂` (test/scripted) | `ScriptedDelegationAgent` | `adapters/agents/scripted.py:17-59` |
| Postcondition (envelope hợp lệ) | `DelegationResult` luôn có outcome/artifacts/summary | `langgraph_agent.py:83-95`, `scripted.py:48-59` |
| Exception contract (fail → outcome, không raise) | `outcome='failed'` thay vì throw | `langgraph_agent.py:82-86` |
| Invariant (`outcome` nhị phân) | `outcome ∈ {"success","failed"}` | `langgraph_agent.py:86`, `scripted.py:51` |
| Bằng chứng tuân thủ cấu trúc | `isinstance(..., DelegationPort)` | `tests/test_supervisor_loop.py:147` |

---

## 4. Bản rút gọn chạy được

File: [`delegation_port_lsp.py`](./delegation_port_lsp.py) — `python3 delegation_port_lsp.py` (exit 0).

**Mô phỏng đúng:** Protocol `DelegationPort` (`name`/`can_handle`/`run`); `LangGraphDelegationAgent`
qua một `_FakeGraph.stream()` stdlib GIỮ NGUYÊN luồng stream-step → emit artifact → gọi
`progress_sink` → map status thành outcome; `ScriptedDelegationAgent` phát hàng đợi artifact;
một `DelegationRegistry` resolve theo `can_handle`; một `TaskLoop` đọc envelope mà không `isinstance`.

**Lược bỏ:** LangGraph thật (`build_agent_graph`, `InMemorySaver`, `AgentState`), `KernelSession` thật
(thay bằng `ChildSession` chỉ giữ `session_id`), `Budget`/policy.

**Đối chứng:** `CrashingAgent.run()` *raise* `RuntimeError` (mở rộng exception type ngoài hợp đồng)
→ vì `TaskLoop` không `try/except RuntimeError`, supervisor crash giữa vòng lặp → minh họa: hợp đồng
nói "fail báo qua `outcome`", subtype raise lạ = vi phạm LSP.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Chi phí**: contract "fail → `outcome='failed'`, không raise" buộc agent production phải *bắt* mọi
  lỗi nội bộ và quy về envelope — dễ nuốt nhầm lỗi lập trình (bug) thành "task failed". Cần phân biệt
  lỗi nghiệp vụ (báo qua outcome) với lỗi hệ thống (vẫn nên propagate).
- **Cạm bẫy**: `progress_sink` được gọi 0+ lần là một phần contract; nếu một agent gọi sink với
  `sequence` không tuần tự, caller dựa vào thứ tự sẽ hỏng dù `isinstance` vẫn pass.
- Nếu chỉ có duy nhất một loại agent và không có biến thể test, port chỉ thêm indirection.

## 6. Câu hỏi tự kiểm tra

1. Tại sao `LangGraphDelegationAgent` chọn báo thất bại qua `outcome='failed'` thay vì `raise`?
   Caller `TaskLoop` sẽ phải viết khác đi như thế nào nếu nó raise?
2. `ScriptedDelegationAgent` luôn trả `outcome='success'`. Như vậy nó có *làm yếu* hay *làm mạnh*
   hợp đồng so với base không? (Gợi ý: nó vẫn nằm trong tập `{success, failed}`.)
3. `isinstance(agent, DelegationPort)` pass cho `CrashingAgent` không? Điều đó nói gì về giới hạn của
   `@runtime_checkable` trong việc đảm bảo LSP?
