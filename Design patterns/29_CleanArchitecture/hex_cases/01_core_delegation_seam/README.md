# Case 01 — Core Ports + Adapter Implementation (Delegation seam)

> **Pattern**: Clean Architecture — *core owns the Protocol, adapter implements it*.
> Use case `DelegationManager` chỉ phụ thuộc `Protocol`; nó không bao giờ biết adapter cụ thể.
> Đổi adapter tại composition root → hành vi đổi, logic use case y nguyên.

---

## 1. Bối cảnh trong hex_agent

hex_agent cho phép một agent **giao việc** (delegate) cho một agent con. Câu hỏi kiến trúc: "agent con" có thể là một adapter scripted (deterministic, cho test offline) hoặc một adapter chạy LangGraph + LLM thật. Làm sao `DelegationManager` (luồng nghiệp vụ giao việc) không phải biết engine nào đang chạy?

Lời giải của hex_agent đúng theo Clean Architecture: **core sở hữu một `Protocol` (output port)**, adapter ở vòng ngoài implement nó, và composition root là nơi DUY NHẤT nối hai vòng lại.

- `DelegationPort` (output port) được khai báo trong **`core/ports.py:32-45`** — `runtime_checkable Protocol`, kèm docstring "Concrete behavior lives behind this port."
- `ScriptedDelegationAgent` implement port đó trong **`adapters/agents/scripted.py:17-59`**, chỉ import từ `core.ports` / `core.schemas` / `core.session`. Core không bao giờ import ngược lại.
- `DelegationManager` (use case) ở **`delegation/manager.py:19-192`** nhận `registry` (chứa `DelegationPort`) và `store` (`DelegationStorePort`) qua `__init__` — dependency injection thuần.
- Composition root **`delegation/bootstrap.py:13-24`** là nơi import cả core lẫn adapter, wire `LangGraphDelegationAgent` vào use case.
- Test **`tests/test_delegation.py:14-40`** chứng minh: factory `_manager()` wire `ScriptedDelegationAgent` + fake store, test use case mà không cần framework nào.

---

## 2. Trích đoạn code thật

Output port owned by core (`core/ports.py:32-45`):

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

Composition root — nơi duy nhất thấy cả core lẫn adapter (`delegation/bootstrap.py:13-24`):

```python
def create_delegation_service(kernel: AgentKernel) -> DelegationServicePort | None:
    config = dict(kernel.config.get("delegation") or {})
    if not config.get("enabled", False):
        return None
    target = str(config.get("default_target") or "agent:general")
    registry = DelegationRegistry()
    registry.register(LangGraphDelegationAgent(target))   # wire adapter cụ thể vào port
    return DelegationManager(
        registry=registry,
        sessions=SessionFactory(kernel=kernel),
        store=InMemoryDelegationStore(),
    )
```

Use case chỉ thấy Protocol — nó `resolve` rồi `run`, không hề biết class nào (`delegation/manager.py:119-160`, lược):

```python
handler = self.registry.resolve(target)           # trả về DelegationPort (Protocol)
child = self.sessions.create_child(...)
...
result = handler.run(request, child, progress_sink)  # runtime call ra adapter
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò trong Clean Architecture | Thành phần trong hex_agent | File:line |
|---|---|---|
| **Entities (vòng 1)** — contract bất biến | `DelegationSpec`, `DelegationRequest`, `DelegationResult` (frozen dataclass) | `core/schemas.py:132-198, 201-253` |
| **Output port** (owned by inner) | `DelegationPort`, `DelegationStorePort` (Protocol) | `core/ports.py:32-45, 48-63` |
| **Use case (vòng 2)** | `DelegationManager` orchestrate port calls | `delegation/manager.py:19-192` |
| **Registry (vòng 2)** | `DelegationRegistry` resolve target → `DelegationPort` | `delegation/registry.py:9-40` |
| **Adapter (vòng 3)** — implement port | `ScriptedDelegationAgent`, `LangGraphDelegationAgent`, `InMemoryDelegationStore` | `adapters/agents/scripted.py:17-59`, `delegation/store.py:9-56` |
| **Composition root (vòng 4)** | `create_delegation_service` wire adapter vào use case | `delegation/bootstrap.py:13-24` |
| **Dependency direction** | adapter → core (inward), không bao giờ core → adapter | toàn bộ |

---

## 4. Bản rút gọn chạy được

File: [`core_delegation_seam.py`](core_delegation_seam.py)

Nó **mô phỏng**:
- Entities (`frozen dataclass`), output ports (`Protocol`), use case (`DelegationManager`), registry, store adapter, và composition root `create_delegation_service`.
- Hai adapter cùng implement `DelegationPort`: `ScriptedDelegationAgent` và `EchoDelegationAgent` (đứng thay `LangGraphDelegationAgent`). Demo đổi adapter ở composition root mà use case không đổi.
- Một `SpyAgent` mock để cho thấy unit-test use case chỉ cần một port giả.
- Một đối chứng `TightlyCoupledManager`: use case tự khởi tạo adapter cụ thể bên trong → vi phạm dependency rule.

Nó **lược bỏ** (so với bản thật):
- `KernelSession` / child session / `SessionFactory` (case 03 lo phần entity/session). `run()` ở đây bỏ tham số `child_session` để giữ trọng tâm vào seam port↔adapter.
- Policy engine, event bus, thread-lock, idempotency theo `event_id`, ghép artifact phức tạp. Giữ đúng "store source-of-truth first" và bất biến "result phải khớp request".
- LangGraph/LLM thật → thay bằng `EchoDelegationAgent` stdlib.

Chạy:

```bash
python3 core_delegation_seam.py
```

Các `assert` chứng minh: (a) đổi adapter cho kết quả khác nhưng use case y nguyên; (b) use case chỉ phụ thuộc `Protocol` (mock không kế thừa vẫn `isinstance(..., DelegationPort)` nhờ `runtime_checkable`); (c) bất biến "result khớp request id"; (d) đối chứng coupled không nhận adapter qua tham số.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Indirection thêm một lớp**: mỗi call qua port là một bậc gián tiếp. Với một script 50 dòng giao việc cho đúng một engine cố định mãi mãi, `TightlyCoupledManager` (hard-code adapter) ngắn hơn và đủ dùng.
- **Phải nuôi Protocol cho khớp**: khi đổi signature `run()`, mọi adapter phải đổi theo. Nếu chỉ có một adapter và sẽ không bao giờ có thêm, port chỉ là chi phí.
- **Registry + freeze + resolve** là máy móc chỉ đáng giá khi *thực sự* có nhiều target/handler. Một use case một-handler có thể inject thẳng port, bỏ registry.
- Heuristic của bài học gốc: pattern này đáng giá tỉ lệ thuận với *lifetime + churn* của vùng adapter. hex_agent có cả scripted (test) lẫn LangGraph (prod) nên rất đáng; một prototype dùng-một-lần thì không.

---

## 6. Câu hỏi tự kiểm tra

1. Trong `delegation/manager.py`, `DelegationManager` có chỗ nào `import` `ScriptedDelegationAgent` hay `LangGraphDelegationAgent` không? Vì sao câu trả lời "không" lại chính là dependency rule?
2. Vì sao `DelegationPort` được khai báo ở `core/ports.py` chứ không ở `adapters/`? Nếu đặt nhầm vào `adapters/`, dependency rule bị vi phạm thế nào?
3. `runtime_checkable` cho phép `isinstance(obj, DelegationPort)` thành công với một class **không** kế thừa `DelegationPort`. Điều này hỗ trợ việc viết test (mock port) ra sao?
