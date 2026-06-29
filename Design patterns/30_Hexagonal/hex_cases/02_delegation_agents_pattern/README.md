# Case 02 — Delegation: DRIVING port + nhiều adapter chiến lược

> Case 01 dạy **driven** port (lõi gọi RA). Case này dạy **driving** port (thế giới ngoài gọi VÀO lõi).
> Driving port = "việc lõi **làm được**"; adapter là *cách* làm. Một lõi `DelegationManager`, hai chiến lược
> hoàn toàn khác nhau cắm vào: `ScriptedDelegationAgent` (test) và `LangGraphDelegationAgent` (production).

---

## 1. Bối cảnh trong hex_agent

Một agent muốn **giao việc con** (delegate) cho một agent khác. Việc "chạy task con" có thể được thực hiện
theo nhiều cách: trong test cần kết quả **deterministic** (không gọi LLM), trong production phải chạy qua
một **LangGraph** thật (gọi LLM, stream từng step). hex_agent đặt một **driving port** `DelegationPort` định
nghĩa *cái lõi cần một handler làm được* — `can_handle()` + `run()` — và để adapter thực thi.

- `core/ports.py:32-45` — `DelegationPort` (Protocol): `name`, `can_handle(target)`, `run(request, child_session, progress_sink)`.
- `core/ports.py:48-62` — `DelegationStorePort` (driven port để lưu progress/result).
- `adapters/agents/scripted.py:17-59` — `ScriptedDelegationAgent` (adapter deterministic cho test).
- `adapters/agents/langgraph_agent.py:21-95` — `LangGraphDelegationAgent` (adapter production, stream LangGraph).
- `delegation/manager.py:19-32` — `DelegationManager.__init__` nhận `registry` + `sessions` + `store` (đều port/interface).
- `delegation/manager.py:119-160` — `delegate()` gọi `self.registry.resolve(target)` rồi `handler.run(...)` qua port.
- `delegation/bootstrap.py:13-24` — `create_delegation_service()` là **composition root**: nơi DUY NHẤT import adapter cụ thể (`LangGraphDelegationAgent`).
- `tests/test_delegation.py:14-23` — test wire `DelegationManager` với `ScriptedDelegationAgent` + `InMemoryDelegationStore`, chứng minh lõi test được offline.

---

## 2. Trích đoạn code thật

Driving port — lõi định nghĩa "việc làm được" (`core/ports.py:32-45`):

```python
@runtime_checkable
class DelegationPort(Protocol):
    name: str
    def can_handle(self, target: str) -> bool: ...
    def run(
        self,
        request: DelegationRequest,
        child_session: "KernelSession",
        progress_sink: ProgressSink,
    ) -> DelegationResult: ...
```

Lõi orchestrator chọn handler qua port, không biết adapter cụ thể (`delegation/manager.py:120` resolve, `:160` run — **hai dòng cách xa nhau**, ở giữa có tạo child session + định nghĩa `progress_sink`):

```python
handler = self.registry.resolve(target)        # dòng 120 — trả về một DelegationPort
# ... (tạo child session, dựng progress_sink ở giữa) ...
result = handler.run(request, child, progress_sink)   # dòng 160 — gọi qua port
```

Composition root — **nơi duy nhất** import adapter (`delegation/bootstrap.py:13-24`):

```python
def create_delegation_service(kernel: AgentKernel) -> DelegationServicePort | None:
    config = dict(kernel.config.get("delegation") or {})
    if not config.get("enabled", False):
        return None
    target = str(config.get("default_target") or "agent:general")
    registry = DelegationRegistry()
    registry.register(LangGraphDelegationAgent(target))     # ← adapter prod cắm vào đây
    return DelegationManager(
        registry=registry,
        sessions=SessionFactory(kernel=kernel),
        store=InMemoryDelegationStore(),
    )
```

Test dùng adapter Scripted, lõi giống hệt (`tests/test_delegation.py:14-23`):

```python
def _manager(kernel, *, target="agent:review", artifacts=None):
    registry = DelegationRegistry()
    registry.register(ScriptedDelegationAgent(target, artifacts=artifacts))  # ← adapter test
    store = InMemoryDelegationStore()
    manager = DelegationManager(registry=registry, sessions=SessionFactory(kernel=kernel), store=store)
    return manager, store
```

---

## 3. Ánh xạ vai trò Hexagonal ↔ code thật

| Vai Hexagonal | Thành phần code thật (hex_agent) | Trong bản distill |
|---|---|---|
| **Driving Port** (lõi sở hữu; adapter implement) | `DelegationPort` — `core/ports.py:32-45` | `DelegationPort` |
| **Driving Adapter** (deterministic, test) | `ScriptedDelegationAgent` — `adapters/agents/scripted.py:17-59` | `ScriptedDelegationAgent` |
| **Driving Adapter** (production) | `LangGraphDelegationAgent` — `adapters/agents/langgraph_agent.py:21-95` | `LangGraphDelegationAgent` + `_FakeGraph` |
| **Core Orchestrator** (inject adapters qua registry) | `DelegationManager` — `delegation/manager.py:19-192` | `DelegationManager` |
| **Driven Port + Adapter** (lưu trữ) | `DelegationStorePort` / `InMemoryDelegationStore` — `core/ports.py:48-62`, `delegation/store.py:9-56` | `DelegationStorePort` / `InMemoryDelegationStore` |
| **Registry** (add adapter không sửa lõi) | `DelegationRegistry` — `delegation/registry.py` | `DelegationRegistry` |
| **Composition Root** (nơi duy nhất biết adapter) | `create_delegation_service()` — `delegation/bootstrap.py:13-24` | `create_delegation_service()` |

---

## 4. Bản rút gọn chạy được

File: [`delegation_agents_pattern.py`](./delegation_agents_pattern.py) — chạy `python3 delegation_agents_pattern.py`.

**Mô phỏng gì:**
- `DelegationPort` (driving): `name` + `can_handle()` + `run()`, giữ nguyên chữ ký vai trò.
- Hai adapter cùng port: `ScriptedDelegationAgent` (artifact đóng hộp) và `LangGraphDelegationAgent`
  (chạy `_FakeGraph` sinh nhiều step, emit progress per step — giữ đúng *hình dạng* của adapter prod).
- `DelegationManager` nhận `registry` + `store` qua `__init__`, `delegate()` resolve handler → `run` → persist progress → finish.
- `DelegationRegistry` cho phép đăng ký nhiều adapter theo `can_handle`.
- `create_delegation_service(mode=...)` là composition root chọn adapter.
- Demo chứng minh: đổi `scripted` ↔ `langgraph` dùng **cùng** class `DelegationManager`; thêm adapter target
  mới (`agent:review`, `agent:build`) **không sửa** lõi; target lạ → `outcome="failed"` sạch.

**Lược bỏ gì:**
- LangGraph + LLM thật → `_FakeGraph` sinh step bằng stdlib (giữ vai trò: nhiều bước, progress per step).
- `KernelSession` / `SessionFactory` thật → `FakeSession` chỉ có `session_id`.
- policy engine, event publish, redaction → giữ phần lõi `resolve → run → persist → finish`.

Có một **phản ví dụ** `HardWiredSupervisor`: lõi `new LangGraphDelegationAgent()` thẳng → không qua port/registry
→ muốn test offline bằng Scripted phải sửa lõi. Đây là *God Controller / hard-wired dependency* mà driving port giải phóng.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Chỉ có một cách chạy task**: nếu mãi mãi chỉ có một handler (không bao giờ cần test-double khác production),
  driving port + registry là thừa. Ở hex_agent nó đáng vì có **ít nhất hai** chiến lược (scripted vs LangGraph)
  và test cần bản deterministic.
- **Port quá to**: `DelegationPort` chỉ 2 method nghiệp vụ (`can_handle`, `run`) — đúng ISP. Nếu nhồi 20 method
  vào một port thì adapter test sẽ phải implement cả đống thứ vô nghĩa.
- **Lẫn lộn driving với driven**: dễ nhầm. Mẹo phân biệt: ai *khởi xướng* lời gọi? Với `DelegationPort`, lõi
  `DelegationManager` gọi VÀO `handler.run()` — nhưng `handler` là thứ *bên ngoài* (adapter) thực thi *thay cho* lõi
  một việc lõi tự công bố là làm được → đây là **driving** (inbound: thế giới ngoài thực hiện hành vi của lõi).
  Ngược lại `DelegationStorePort` là **driven** (lõi gọi ra để lưu).
- Chi phí thật: cần **contract test** ép mỗi adapter tuân port (Liskov), nếu không `run()` của adapter này trả
  `DelegationResult` lệch hợp đồng với adapter kia.

---

## 6. Câu hỏi tự kiểm tra

1. `DelegationPort` (driving) và `VectorStorePort` ở Case 01 (driven) **khác nhau ở hướng** thế nào?
   Ai khởi xướng lời gọi trong từng trường hợp, và ai "uốn theo" ai?
2. `DelegationRegistry` dùng `can_handle(target)` để chọn adapter thay vì một dict `target -> adapter`.
   Lợi/hại của cách này khi cần thêm một adapter "bắt mọi target chưa khớp" (fallback)?
3. Trong demo, target `agent:unknown` cho `outcome="failed"` chứ không làm sập chương trình. Lõi
   `DelegationManager.delegate` đã làm gì để biến một `LookupError` từ registry thành một `DelegationResult`?
   Vì sao đó là hành vi "đúng tinh thần Hexagonal" thay vì để exception leo lên driving adapter?
