# Case 03 — Worker Protocol + ScriptedWorker/LocalLLMWorker: Strategy qua DI (OCP)

> Strategy (lesson 25, bảng 2.1 cơ chế #1): interface + nhiều impl, **swap qua DI** chứ không
> qua conditional. "Caller phụ thuộc abstraction, không concrete" (mục 2.3 #4).

---

## 1. Bối cảnh trong hex_agent

`decompose_agent` chia một task lớn thành các task con và đề xuất action cho từng node. Hai môi
trường khác nhau cần hành vi khác nhau: **test** cần kết quả tất định (không chạm mạng), **prod**
cần gọi LLM thật. Bài toán thật: làm sao chuyển đổi hoàn toàn giữa hai cái đó mà caller
(decomposer / graph runner) **không** chứa `if mode == "scripted" ... elif "llm" ...`?

Lời giải (đã mở file kiểm chứng):

- **Abstraction:** `Worker` Protocol — `decompose_agent/worker.py:182-185`:
  `propose(ctx: FourCell) -> dict` + `decompose(node, failure_evidence, reason) -> list[dict]`.
  Là `Protocol` (structural) — impl chỉ cần có 2 method này.
- **Concrete strategy A:** `ScriptedWorker` — `decompose_agent/worker.py:188-227`. Deterministic
  double; `propose()` tra `scripts[node_id][call_count]`, `decompose()` dùng `decompose_scripts`.
- **Concrete strategy B:** `LocalLLMWorker` — `decompose_agent/worker.py:230-301`. LLM-backed;
  `propose()`/`decompose()` gọi `self._chat()` (retry + backoff). `client` injectable nên test
  không chạm mạng. Hoàn toàn khác `ScriptedWorker` nhưng **implement cùng 2 method**.

Cùng motif lặp lại ở supervisor: `OrchestratorPort` + `ScriptedOrchestrator`/`LLMOrchestrator`
(`supervisor/orchestrator.py:15-39`), và `ChatLLM` Protocol + `LLMOrchestrator(llm)` nhận LLM qua
DI (`supervisor/llm.py:52-91`). Thêm strategy mới = thêm class, 0 sửa caller.

---

## 2. Trích đoạn code thật

`decompose_agent/worker.py:182-185` — abstraction:

```python
@runtime_checkable
class Worker(Protocol):
    def propose(self, ctx: FourCell) -> dict[str, Any]: ...
    def decompose(self, node: Node, failure_evidence: Any = None, reason: str | None = None) -> Any: ...
```

`decompose_agent/worker.py:201-213` — strategy A (`ScriptedWorker.propose`, tra script):

```python
def propose(self, ctx: FourCell) -> dict[str, Any]:
    nid = ctx.node_id
    i = self._calls[nid]
    self._calls[nid] += 1
    script = self._scripts.get(nid)
    if script:
        item = script[i] if i < len(script) else script[-1]
        ...
        return item
    ...
```

`decompose_agent/worker.py:279-282` — strategy B (`LocalLLMWorker.propose`, gọi LLM):

```python
def propose(self, ctx: FourCell) -> dict[str, Any]:
    raw = self._chat([{"role": "system", "content": ctx.identity},
                      {"role": "user", "content": ctx.render()}], self._temperature)
    return normalize_action(parse_object(raw))
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò OCP / Strategy | Thành phần trong hex_agent | File:line |
|---|---|---|
| Abstraction | `Worker` Protocol | `decompose_agent/worker.py:182-185` |
| Concrete strategy (test) | `ScriptedWorker` | `decompose_agent/worker.py:188-227` |
| Concrete strategy (prod) | `LocalLLMWorker` | `decompose_agent/worker.py:230-301` |
| Caller phụ thuộc abstraction | decomposer / graph runner (nhận `Worker` qua DI) | `decompose_agent/worker.py:182-185` (contract) |
| Extension point | worker injection (constructor) | DI tại nơi dựng worker |
| Cùng motif (đối chiếu) | `OrchestratorPort` + `ScriptedOrchestrator`/`LLMOrchestrator` | `supervisor/orchestrator.py:15-39` |
| Cùng motif (đối chiếu) | `ChatLLM` Protocol + `LLMOrchestrator(llm)` DI | `supervisor/llm.py:52-91` |

---

## 4. Bản rút gọn chạy được

File: [`worker_strategy_pattern.py`](./worker_strategy_pattern.py)
(`python3 worker_strategy_pattern.py`, exit 0).

**Mô phỏng:** `Worker` Protocol, `ScriptedWorker`, `LocalLLMWorker` (client fake stdlib, có retry
tối thiểu), và `Decomposer` (caller nhận `worker` qua constructor). Demo chứng minh:
- cùng `Decomposer`, swap strategy chỉ bằng đối số constructor (DI) — cả hai đi qua đúng 1 dòng
  `worker.propose(ctx)` (polymorphic dispatch);
- thêm `HybridWorker` (scripted → fallback LLM) và `RandomWorker` — mỗi cái chỉ implement 2 method,
  và mã nguồn `Decomposer` **không đổi 1 dòng** (kiểm bằng `inspect.getsource`).

**Lược bỏ:** `FourCell`/`Node` đầy đủ, repair ladder JSON (`parse_object`/`normalize_action`),
`WorkerError`, cấu hình env-var, backoff thật. `LocalLLMWorker` dùng **fake client** (callable
stdlib) — không mạng, không SDK `openai`. Giữ nguyên trục Strategy: 2 method, DI, ≥ 2 impl khác nhau.

**Đối chứng anti-OCP:** hàm `propose_anti_ocp(mode, ...)` dùng `if/elif` trên `mode`. Thêm
`"hybrid"` buộc **mở lại** hàm cũ và phình param signature; mode lạ chỉ lộ ở runtime (`else: raise`).

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Wrong abstraction (Sandi Metz):** nếu rút Protocol từ chỉ **1 variant**, 80% là sai trục
  (lesson 25, mục 1.6 — chờ rule of 3). `Worker` chỉ xứng đáng vì đã có ≥ 2 impl thật.
- **Frozen interface trap:** nếu sau này một strategy cần dữ liệu mà `propose(ctx)` không có
  (vd: history), bạn dễ bị cám dỗ sửa signature interface đã đóng — đó là vết nứt OCP. Cân nhắc
  Decorator/Context object thay vì đổi seam.
- **Indirection:** dispatch gián tiếp qua Protocol thêm 1 lớp; với code 1 dev sở hữu, < 100 dòng,
  không bên thứ ba, có thể là thừa.
- **OCP cần LSP đi kèm:** nếu một strategy phá contract (raise lạ, return sai type), caller buộc
  `isinstance()` → if/elif quay lại (lesson 26). Strategy chỉ an toàn khi mọi impl giữ contract.

---

## 6. Câu hỏi tự kiểm tra

1. `Decomposer` nhận `Worker` qua constructor (DI) thay vì tự tạo bên trong. Vì sao điều này là
   **điều kiện cấu trúc** để Strategy/OCP khả thi (gợi ý: cầu nối sang DIP, lesson 28)?
2. `ScriptedWorker` và `LocalLLMWorker` có thân hàm hoàn toàn khác nhau nhưng cùng 2 chữ ký method.
   Nếu `LocalLLMWorker.propose` thỉnh thoảng raise exception còn `ScriptedWorker` thì không, điều
   đó vi phạm nguyên tắc nào và khiến caller phải làm gì?
3. `HybridWorker` được thêm vào mà `Decomposer` không đổi. Hãy chỉ ra đâu là "open for extension"
   và đâu là "closed for modification" trong tình huống đó.
