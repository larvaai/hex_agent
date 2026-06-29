# Case 02 — KernelSession + SessionIdentity: Aggregate cho ngữ cảnh thực thi một task

> Distill từ `core/session.py` (+ `core/state.py`) trong `hex_agent`. Liên hệ: `35_Aggregate.md`.

---

## 1. Bối cảnh trong hex_agent

`AgentKernel` là phần *frozen, dùng chung* (LLM client, registry tool, event bus). Nhưng mỗi
task lại có **state và vòng đời riêng**, và nhiều task có thể chạy đồng thời (root delegate
xuống child). Nếu để chung một chỗ thì state của task này lẫn task kia, và không ai biết khi
nào một task "đã đóng".

`KernelSession` (`core/session.py:49-101`) là *consistency boundary* cho **đúng một task**:
nó sở hữu `StateStore` riêng, có cờ `_closed`, và một invariant sống còn — `is_active`
(`session.py:59-61`): session chỉ "sống" khi **chưa đóng** VÀ `current_task` vẫn là một
`TaskEnvelope`. Mọi lệnh `execute_tool` đều phải qua cổng này; gọi sau khi đóng thì bị từ chối
(`session.py:75-85`) — chống use-after-completion.

`SessionIdentity` (`session.py:15-46`) là **value object** `frozen=True`: danh tính bất biến
để tra cứu xuyên session (run_id, task_id, parent_session_id, depth).

`SessionFactory` (`session.py:104-203`) là **nơi duy nhất** dựng session — comment dòng 105
nói thẳng: *"AgentKernel never creates sessions"*. Factory enforce hai bất biến quan trọng:
(a) scope yêu cầu ⊆ scope khả dụng khi tạo root (`session.py:110-117`); (b) scope con ⊆ scope
cha khi delegate (`session.py:163-164`) — chống leo thang quyền.

File đã mở kiểm chứng: `/Users/uspro/Desktop/namnson/hex_agent/core/session.py` (204 dòng) và
`/Users/uspro/Desktop/namnson/hex_agent/core/state.py` (28 dòng).

---

## 2. Trích đoạn code thật

`core/session.py:59-98` — invariant vòng đời + command đổi state atomic + publish event:

```python
    @property
    def is_active(self) -> bool:
        return not self._closed and isinstance(self.state.get("current_task"), TaskEnvelope)

    def execute_tool(self, tool_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.is_active:
            return {
                "ok": False,
                ...
                "error": "Session is not active.",
                "metadata": {**self.call_context().event_fields(), "session_closed": True},
            }
        return self.kernel.execute_tool(tool_name, args, context=self.call_context())

    def complete_task(self, result: Any = None, *, status: str = "completed") -> dict[str, Any]:
        if not self.is_active:
            raise RuntimeError("Session task lifecycle is already closed.")
        outcome = {"task_id": self.identity.task_id, "status": status, "result": result}
        self.state.set("last_result", outcome)
        self.state.set("current_task", None)
        self._closed = True
        self.kernel.events.publish(
            "task.completed" if status == "completed" else "task.failed",
            {**self.call_context().event_fields(), "status": status},
        )
        return outcome
```

Và invariant scope con ⊆ scope cha trong factory, `core/session.py:162-164`:

```python
        scope = parent.allowed_capabilities if requested_scope is None else requested_scope
        if not scope <= parent.allowed_capabilities:
            raise PermissionError("Child capability scope must be a subset of the parent scope.")
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò trong Aggregate (Lesson 35) | Thành phần code thật |
|---|---|
| **Aggregate Root (AR)** | `KernelSession` (`session.py:49-101`) — mutable, vòng đời 1 task |
| **Value Object (immutable identity)** | `SessionIdentity` `frozen=True` (`session.py:15-46`) |
| **Internal Entity / data bag** | `StateStore` (`core/state.py:8-28`) — chỉ AR chạm tới |
| **Invariant** | `is_active` (`session.py:59-61`); `_closed` (57) chặn use-after-completion |
| **Command method** | `execute_tool` (75-85), `complete_task` (87-98), `fail_task` (100-101) |
| **Domain Event** | `kernel.events.publish("task.completed"/"task.failed"/"task.accepted")` (94-96, 145, 185) |
| **Factory** | `SessionFactory` (`session.py:104-203`) — nơi duy nhất construct AR |
| **Invariant ở Factory** | scope ⊆ khả dụng (110-117); scope con ⊆ cha (163-164) |
| **Reference by ID** | `parent_session_id`, `delegation_id` (ID, không phải object cha) |

---

## 4. Bản rút gọn chạy được

File: [`kernel_session_aggregate.py`](./kernel_session_aggregate.py) — chạy:
`python3 kernel_session_aggregate.py` (exit 0, không traceback).

**Mô phỏng gì:** demo 10 bước — factory dựng root → chứng minh `SessionIdentity` bất biến →
`execute_tool` trong/ngoài scope → factory enforce scope con ⊆ cha → factory chặn capability
không khả dụng → `complete_task` đổi state atomic + publish `task.completed` + khoá session →
use-after-completion bị từ chối → double-complete bị ném → mỗi session có `StateStore` riêng.
Mỗi bước có `assert` chứng minh invariant.

**Lược bỏ / fake:** thay `AgentKernel` nặng (LLM, registry thật, event bus thật) bằng
`FakeKernel` (registry tĩnh + `FakeEventBus` in-memory). Thay `TaskEnvelope` / `ToolCallContext`
nhiều field bằng `Task` gọn và một dict context. Bỏ nhánh `restore()` từ checkpoint (giữ
`create_root`/`create_child` là đủ minh hoạ factory). Giữ NGUYÊN: danh tính frozen, cờ
`_closed`/`is_active`, publish event, và hai invariant scope.

**Đối chứng:** `naive_make_session()` (bước 10) — dựng session bằng tay, bỏ qua factory: không
ai validate scope, không ai set `current_task`, không ai publish `task.accepted` → aggregate ra
đời ở trạng thái **không hợp lệ** (`is_active=False` ngay từ đầu). Minh hoạ anti-pattern
"Missing factory" trong bài gốc.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Factory + immutability = thêm tầng:** với prototype hay script một lần, dựng object trực
  tiếp nhanh hơn; factory chỉ đáng giá khi việc construct có invariant thật (ở đây là scope +
  task envelope hợp lệ).
- **Eventual consistency là cái giá đi kèm AR-per-transaction:** mỗi `KernelSession` là một
  boundary; muốn đồng bộ giữa parent và child thì phải qua event/ID, không thể mutate chéo —
  UI có thể "flash" tạm thời (Lesson 35, bảng trade-off).
- **Đừng leak `StateStore` ra ngoài:** nếu trả thẳng `session.state` cho code ngoài sửa, ranh
  giới aggregate vỡ (anti-pattern "Aggregate expose internal").
- **Đừng gộp nhiều task vào một session để "tiện":** đó là God Aggregate — lock contention cao,
  khó cô lập lỗi.

---

## 6. Câu hỏi tự kiểm tra

1. `is_active` kiểm tra **hai** điều kiện (`not _closed` VÀ `current_task is TaskEnvelope`). Vì
   sao chỉ một cờ `_closed` là chưa đủ? (Gợi ý: `restore()` ở `session.py:201-202` dựng lại một
   session mà `current_task` đã là `None`.)
2. Tại sao comment ở `session.py:160-161` nhấn mạnh phân biệt `requested_scope=None`
   ("kế thừa scope cha") với `frozenset()` rỗng ("từ chối tất cả")? Coi rỗng là falsy sẽ sai
   thế nào?
3. `complete_task()` vừa đổi state vừa `publish` event trong cùng một method. Theo Lesson 35,
   vì sao event nên emit **từ AR method** chứ không phải từ service bên ngoài?
