# Mediator trong hex_agent — Hồ sơ case thực chiến

> Tài liệu dạy học đi kèm bài [`17_Mediator.md`](../17_Mediator.md). Ở đây ta soi
> pattern **Mediator** *ngay trong codebase hex_agent thật*: nơi nào nó xuất hiện,
> nó giải bài toán gì, rồi distill thành các bản rút gọn chạy được bằng Python
> chuẩn.

---

## Mediator hiện diện thế nào trong hex_agent?

Như bài gốc nói: Mediator đặt một object trung gian giữa N colleague để chúng không
tham chiếu trực tiếp lẫn nhau — biến `N×(N-1)/2` connection thành `N`. hex_agent dùng
đúng tư duy này ở **hai tầng cốt lõi**, theo đúng phép loại suy thalamus:

1. **Chokepoint mediator (mức capability)** — `AgentKernel.execute_tool`
   (`core/kernel.py:106-225`) là *điểm trung chuyển duy nhất* cho mọi request gọi
   tool. Các mối quan tâm cắt ngang (capability gate, billing, retry, logging) là
   middleware bọc thành chuỗi quanh một resolver chọn executor cuối qua registry. Không
   caller nào chạm executor trực tiếp. Đây là biến thể **Command-Bus + middleware**
   trong mục 2.4 của bài gốc.

2. **Orchestration mediator (mức multi-agent)** — `SupervisorContext` + TaskLoop
   (`supervisor/graph.py` + `supervisor/loop.py`) điều phối một team agent qua một
   **Blackboard** (`TaskLoopState`, `supervisor/state.py:80-111`). Agent không nói
   chuyện trực tiếp; chúng ghi artifact vào Blackboard, còn supervisor (qua
   Orchestrator → Broker → DelegationService → Judge) đọc Blackboard và route bước kế.
   Đây là biến thể **Mediator + State-Machine + Blackboard**.

Cả hai đều giảm coupling N×N về N×1 routing tập trung, và đều trả giá bằng chính cái
giá bài gốc cảnh báo: single point of failure + nguy cơ God Object (được kiềm bằng
cách tách thành nhiều "nuclei" chuyên biệt — registry/middleware ở tầng 1; O/Broker/
Delegation/Judge ở tầng 2).

Ngoài hai flagship, pattern còn lặp lại ở Event-Emitter (`control/emitter.py`), sub-
mediator cho LLM (`supervisor/llm.py`), và work-queue Orchestrator của
`drag_from_zero`. Xem [`CATALOG.md`](./CATALOG.md) để vét cạn.

---

## Các case con

| # | Case | Distill từ | Trọng tâm |
|---|---|---|---|
| 01 | [`01_kernel_middleware_mediator`](./01_kernel_middleware_mediator/) | `core/kernel.py`, `core/registry.py`, `middleware/*` | Chokepoint + middleware pipeline (Command-Bus). Fail-open vs fail-closed, NullTool fallback, đối chứng N×N. |
| 02 | [`02_supervisor_taskloop_mediator`](./02_supervisor_taskloop_mediator/) | `supervisor/graph.py`, `loop.py`, `state.py`, `orchestrator.py`, `broker.py` | Orchestration + Blackboard. Agent không gọi nhau; checkpoint & resume; thêm agent = Open/Closed. |

Mỗi case có `README.md` (6 mục: bối cảnh thật, trích code thật, bảng ánh xạ vai trò,
bản rút gọn, cái giá, câu hỏi tự kiểm) và một file `.py` self-contained.

---

## Chạy thử

```bash
python3 01_kernel_middleware_mediator/kernel_middleware_mediator.py
python3 02_supervisor_taskloop_mediator/supervisor_taskloop_mediator.py
```

Mỗi file in narration từng bước (tiếng Việt), có assert chứng minh bất biến của
pattern, có ít nhất một đối chứng "khi không dùng pattern thì hỏng/khó thế nào", và
thoát code 0. Tất cả chỉ dùng thư viện chuẩn Python — không import hex_agent, không
thư viện bên thứ ba.

---

## Bản đồ nhanh: vai trò Mediator ↔ hex_agent

| Vai trò (bài gốc) | Tầng capability (case 01) | Tầng multi-agent (case 02) |
|---|---|---|
| ConcreteMediator | `AgentKernel` | `SupervisorContext` |
| Điểm `notify`/chokepoint | `execute_tool` | `_drive` / các node |
| Colleague | middleware + executor | agent vai + O/Broker/Delegation |
| Message | `ToolRequest` | `OrchestratorDecision` + Blackboard |
| Routing/dispatch | `registry.resolve_tool` | `Orchestrator.decide` |
| State phối hợp | thứ tự middleware | `TaskLoopState` (Blackboard) |

> Như bài gốc kết luận: học pattern không phải để dán nhãn cho đúng, mà để hiểu
> **ai biết ai, ai quyết định khi nào, ai chịu trách nhiệm gì**. Hai case này cho
> thấy hex_agent trả lời ba câu đó bằng đúng một chokepoint cho mỗi tầng.
