# Case 01 — Worker Protocol: khung `propose`/`decompose`, hai cách hiện thực

> Template Method ở **scale Protocol** (structural typing thay cho inheritance).
> Khung gọi giữ thứ tự bước cố định; hai worker cắm vào cùng khung cho hành vi khác hẳn.

---

## 1. Bối cảnh trong hex_agent

`decompose_agent` là bộ giải bài toán theo cây: mỗi node hoặc được **giải trực tiếp**
(leaf) hoặc bị **chẻ nhỏ** (decompose). Phần "ai làm việc" được tách thành một
khái niệm **Worker**. Vấn đề thật:

- Lúc test, ta cần một worker **tất định** (không gọi mạng, kết quả lặp lại được) để
  kiểm tra logic gate/budget/parse-ladder.
- Lúc chạy thật, worker phải **gọi LLM** (OpenAI-compatible) qua HTTP, có timeout +
  retry + backoff, và parse văn bản trả về.

Hai thứ này hành vi khác nhau một trời một vực, nhưng **bên gọi không nên quan tâm**:
nó chỉ cần "đề xuất một action" hoặc "chẻ một node". hex_agent giải bằng cách định
nghĩa `Worker` là một **Protocol** (structural typing) gồm đúng hai method —
`propose` và `decompose` — rồi để hai lớp hiện thực tự do bên trong.

File thật đã mở kiểm chứng:
- `decompose_agent/worker.py:182-185` — `Worker(Protocol)`.
- `decompose_agent/worker.py:188-227` — `ScriptedWorker`.
- `decompose_agent/worker.py:230-301` — `LocalLLMWorker`.
- `decompose_agent/solve.py:80-122` — `solve_leaf()` (khung gọi `worker.propose`).
- `decompose_agent/solve.py:132-184` — `_decompose()` (khung gọi `worker.decompose`).

---

## 2. Trích đoạn code thật

Khung hợp đồng — `decompose_agent/worker.py:182-185`:

```python
@runtime_checkable
class Worker(Protocol):
    def propose(self, ctx: FourCell) -> dict[str, Any]: ...
    def decompose(self, node: Node, failure_evidence: Any = None, reason: str | None = None) -> Any: ...
```

Hai hiện thực, **cùng chữ ký `propose`**, nội tạng khác hẳn — `worker.py:201-213` (Scripted)
và `worker.py:279-282` (LLM):

```python
class ScriptedWorker:
    def propose(self, ctx: FourCell) -> dict[str, Any]:
        nid = ctx.node_id
        ...
        if script:
            item = script[i] if i < len(script) else script[-1]
            ...
        if self._satisfy is not None:
            return write_action(satisfying_files(self._satisfy.nodes[nid].done_when))
        return write_action({})  # no script, no satisfier → no-op (gate will FAIL)

class LocalLLMWorker:
    def propose(self, ctx: FourCell) -> dict[str, Any]:
        raw = self._chat([{"role": "system", "content": ctx.identity},
                          {"role": "user", "content": ctx.render()}], self._temperature)
        return normalize_action(parse_object(raw))
```

Khung gọi giữ **thứ tự bước cố định**, chỉ `worker.propose` là điểm biến thiên —
`decompose_agent/solve.py:90-117`:

```python
while not attempts.exhausted():
    if budget.step_exceeded():
        return _block(tree, node_id, "BUDGET", journal)
    ctx = assemble_4cell(tree.nodes[node_id], tree, journal)   # bước chung
    try:
        action = worker.propose(ctx)                            # HOOK
    except WorkerError as exc:
        return _block(tree, node_id, "WORKER_ERROR", journal)
    except JsonGateError as exc:
        parse.record_error(); ...
        continue
    ...
    _, rejected = _run_action(action, ...)                      # bước chung
    gate = run_checks(tree.nodes[node_id], nd)                  # bước chung
    if gate.ok:
        tree.set_status(node_id, "done"); return Outcome(...)
```

`_chat` của LLM worker có retry/backoff — `decompose_agent/worker.py:254-277` (rút gọn):

```python
for attempt in range(self._retries + 1):
    try:
        resp = client.chat.completions.create(...)
        return resp.choices[0].message.content or ""
    except Exception as exc:
        last = exc
        if attempt < self._retries and _is_transient(exc):
            _sleep(self._retry_base * (2 ** attempt)); continue
        break
raise WorkerError(f"LLM call failed after {self._retries + 1} attempt(s): {detail}")
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Template Method | Thành phần trong hex_agent |
|---|---|
| Abstract template / khung hợp đồng | `Worker(Protocol)` — `worker.py:182-185` |
| Abstract hook (must implement) | `propose(ctx)`, `decompose(node, ...)` |
| ConcreteClass A (test double) | `ScriptedWorker` — `worker.py:188-227` |
| ConcreteClass B (production) | `LocalLLMWorker` — `worker.py:230-301` |
| Shared concrete operations (skeleton ở bên gọi) | `assemble_4cell`, `_run_action`, `run_checks`, budget/parse ladder — `solve.py:90-117` |
| Template method (vòng cố định) | `solve_leaf` — `solve.py:80-122`; `_decompose` — `solve.py:132-184` |
| Internal helper dùng chung của ConcreteClass B | `_chat`, `_get_client` — `worker.py:247-277` |

Lưu ý văn phong bài gốc: đây **không phải** inheritance (không có base class +
`override`). hex_agent dùng **Protocol** — đúng tinh thần "favor composition over
inheritance" mà mục 2.5 và phần Python-native của bài gốc đề cập. Khung vẫn cố định,
hook vẫn là điểm biến thiên; chỉ là contract được ép bằng structural typing.

---

## 4. Bản rút gọn chạy được

File: [`worker_protocol_system.py`](./worker_protocol_system.py) — chỉ dùng stdlib.

Nó mô phỏng:
- `Worker(Protocol)` + `runtime_checkable` y như thật.
- `ScriptedWorker` (script/satisfy) và `LocalLLMWorker` (gọi endpoint + retry).
- `solve_leaf` và `decompose_node` là **khung gọi** giữ thứ tự bước bất biến.

Nó lược bỏ / thay thế:
- **LLM/HTTP thật** → `FakeChatEndpoint` tất định; có tham số `transient_failures`
  để minh hoạ retry/backoff mà không cần socket.
- **Repair ladder** parse văn bản méo → chỉ còn `json.loads` + kiểm tra kiểu.
- **Cây node / journal / cache** → rút về `Node` phẳng và một vòng-thử nhỏ.

Các điểm chứng minh (assert) trong demo:
- Cùng `solve_leaf` nhận **cả hai** worker, không `if/elif` theo loại (mục C).
- Endpoint lỗi 2 lần rồi ok → đúng **3** lần gọi (2 retry + 1 thành công) (mục D).
- Endpoint chết hẳn → `WorkerError` → outcome `blocked/WORKER_ERROR`, **không crash** (mục E).
- Đối chứng `solve_leaf_NO_PATTERN`: thêm worker mới → khung Protocol nhận ngay, còn
  bản `if/elif` **nổ `TypeError`** (mục G).

Chạy:

```bash
python3 worker_protocol_system.py
```

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Protocol không bắt buộc lúc compile**: `ScriptedWorker`/`LocalLLMWorker` *không*
  kế thừa `Worker`. Nếu lỡ đổi chữ ký `propose`, không có lỗi cho tới khi runtime nổ
  (hoặc tới khi mypy/`@runtime_checkable` bắt được). Bù lại: linh hoạt, không coupling.
- **Nếu thực sự có nhiều code chung giữa các worker** (không chỉ contract), Protocol
  thuần sẽ khiến bạn copy-paste. Khi đó cân nhắc một base class với hook — đúng dạng
  Template Method cổ điển. Ở đây hex_agent đặt code chung ra **bên gọi** (`solve_leaf`),
  nên Protocol là lựa chọn gọn.
- **Khi chỉ có 1 worker duy nhất**: Protocol là thừa — viết thẳng. Pattern chỉ trả
  giá xứng đáng khi có ≥2 hiện thực thật sự khác nhau (ở đây: test double vs production).
- Nhớ cảnh báo mục 1.4 bài gốc: nếu hook cần đổi **thứ tự** bước → không phải Template
  Method nữa; dùng Strategy/Pipeline.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao hex_agent đặt code chung (`assemble_4cell`, `run_checks`, budget) ở
   `solve_leaf` chứ không nhét vào một base class `Worker`? Điều đó nói gì về ranh giới
   giữa "khung" và "hook"?
2. `_chat` phân biệt lỗi *transient* (retry) với lỗi *vĩnh viễn* (raise `WorkerError`
   ngay). Nếu coi cả hai như nhau thì bất biến nào của pattern bị vi phạm về mặt
   "hook phải idempotent / có hợp đồng rõ"?
3. Trong demo, đối chứng `solve_leaf_NO_PATTERN` nổ `TypeError` khi gặp worker lạ.
   Hãy chỉ ra dòng nào trong bản Protocol khiến worker lạ chạy được ngay mà không cần
   sửa khung.
