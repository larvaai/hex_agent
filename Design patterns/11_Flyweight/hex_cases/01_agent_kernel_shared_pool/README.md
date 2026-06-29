# Case 01 — AgentKernel: Shared Frozen Factory + Registry Pool

> Flagship của Flyweight trong `hex_agent`: nhiều session (N) tái dùng MỘT kernel
> đã đông cứng (K=1 instance bất biến). Không có Flyweight, mỗi session phải copy
> nguyên registry + config + danh sách executor.

---

## 1. Bối cảnh trong hex_agent

`hex_agent` chạy nhiều task đồng thời. Mỗi task cần một "session" để giữ trạng thái
riêng (task hiện tại, scope quyền, state store). Nhưng phần "năng lực" — registry các
tool, config hệ thống, các executor — thì **giống nhau cho mọi session** và **không
được thay đổi giữa chừng**.

Kiến trúc tách đôi:

- `AgentKernel` (`core/kernel.py:76-98`) giữ phần **dùng chung, bất biến**: registry,
  events, config. Có method `freeze()` (`core/kernel.py:91-97`) đông cứng config MỘT
  lần trước khi session đầu tiên chạy.
- `KernelSession` (`core/session.py:49-85`) giữ phần **riêng từng task**: identity,
  state, allowed_capabilities — và chỉ **tham chiếu** kernel.
- `SessionFactory` (`core/session.py:104-146`) là nơi DUY NHẤT tạo session; nó gọi
  `kernel.freeze()` (`core/session.py:141`) rồi lắp session trỏ vào cùng kernel.
- `CapabilityRegistry` (`core/registry.py:43-112`) giữ pool `_tools`; `resolve_tool()`
  (`core/registry.py:103-112`) trả về `ToolResolution` từ pool, **không tạo instance
  mới** mỗi lần hỏi. Tool không có descriptor riêng dùng chung `DEFAULT_DESCRIPTOR`
  (`core/registry.py:20`).

Vấn đề thật được giải: nếu mỗi session copy nguyên kernel thì bộ nhớ tăng O(N) theo
số session, và mất bảo đảm "mọi session thấy cùng một bộ năng lực bất biến".

---

## 2. Trích đoạn code thật

`_deep_freeze` biến mọi cấu trúc mutable thành proxy bất biến — `core/kernel.py:14-22`:

```python
def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return frozenset(_deep_freeze(item) for item in value)
    return value
```

`AgentKernel.freeze()` đông cứng config một lần — `core/kernel.py:91-97`:

```python
def freeze(self) -> None:
    """Freeze shared mutable configuration before the first session starts."""
    if self._frozen:
        return
    self.registry.freeze()
    self.config = _deep_freeze(copy.deepcopy(dict(self.config)))
    self._frozen = True
```

`SessionFactory.create_root` — mọi session trỏ vào cùng kernel — `core/session.py:140-144`:

```python
scope = self._effective_root_scope(allowed_capabilities)
self.kernel.freeze()
state = StateStore()
state.set("current_task", task)
session = KernelSession(self.kernel, identity, state, scope)
```

`resolve_tool` trả bản cache, dùng `DEFAULT_DESCRIPTOR` chung — `core/registry.py:103-112`:

```python
def resolve_tool(self, name: str) -> ToolResolution:
    if name in self._tools:
        return ToolResolution(
            self._tools[name],
            self._tool_features.get(name),
            self._descriptors.get(name, DEFAULT_DESCRIPTOR),
        )
    ...
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Flyweight (bài học gốc)            | Thành phần trong hex_agent                                             |
|--------------------------------------------|-----------------------------------------------------------------------|
| `FlyweightFactory` (cache + accessor)      | `AgentKernel` + `CapabilityRegistry.resolve_tool` (`core/registry.py:103`) |
| Shared intrinsic pool (bất biến, chia sẻ)  | `_tools`, `config` sau `freeze()`, `DEFAULT_DESCRIPTOR` (`core/registry.py:20`) |
| `Context` (extrinsic state + ref Flyweight)| `KernelSession` (`core/session.py:49-85`) — trỏ tới `kernel`          |
| `Client` (hỏi Factory, không tự `new`)     | `SessionFactory` (`core/session.py:104-146`)                          |
| Immutability guard                         | `_deep_freeze` (`core/kernel.py:14-22`) + `@dataclass(frozen=True)`    |
| "1 key → 1 instance"                       | pool `_tools` keyed theo tên tool                                      |

---

## 4. Bản rút gọn chạy được

File: [`agent_kernel_shared_pool.py`](./agent_kernel_shared_pool.py) — chạy
`python3 agent_kernel_shared_pool.py`.

**Mô phỏng đúng:**
- `deep_freeze` (distill `core/kernel.py:14-22`): dict → MappingProxyType, set → frozenset.
- `AgentKernel.freeze()` đông cứng config + khóa registry.
- `CapabilityRegistry.resolve_tool()` trả bản cache, dùng chung `DEFAULT_DESCRIPTOR`.
- `SessionFactory.create_root()` gọi `freeze()` rồi lắp session trỏ vào cùng kernel.
- Assert: `s1.kernel is s2.kernel`, `registry is registry`, descriptor chung
  (`id` giống nhau), mutate config sau freeze bị chặn, register tool sau freeze bị chặn.
- Đối chứng `HeavySessionNoFlyweight`: mỗi session `deepcopy(kernel)` → mỗi bản 1 copy.

**Lược bỏ:** middleware pipeline (`_LatchedNext`/`_wrap`), event bus, lineage/metadata,
deep-copy args, scope checking, `create_child`/`restore`. Executor được thay bằng
`EchoTool` tối thiểu. Trọng tâm chỉ giữ đúng vai trò Flyweight: pool chung + factory +
context + immutability.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Phải kỷ luật immutability.** Quên `freeze()` (hoặc dùng dict thường thay
  `MappingProxyType`) thì một session có thể vô tình sửa config dùng chung → mọi
  session khác bị ảnh hưởng (đúng bug "mutable Flyweight" trong bài học gốc).
- **N nhỏ thì thừa.** Nếu chỉ có 1-2 session ngắn hạn, chi phí thiết kế factory +
  freeze lớn hơn phần bộ nhớ tiết kiệm được.
- **Cần kernel khác nhau cho từng task** (config per-task khác hẳn) thì share không hợp;
  lúc đó từng task cần kernel riêng — Flyweight mất ý nghĩa.
- **Bẫy deepcopy:** sau khi freeze, `config` là `mappingproxy` không pickle/deepcopy
  được — bản thân điều này nhắc rằng nên SHARE chứ đừng COPY (xem bước [8] trong demo).

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `AgentKernel` là minh họa Flyweight chứ không phải Singleton? (Gợi ý:
   số lượng *type năng lực* K so với số *session* N; Singleton là Flyweight với K=1.)
2. `resolve_tool()` trả về cùng `DEFAULT_DESCRIPTOR` cho nhiều tool. Đây là intrinsic
   hay extrinsic state? Nếu descriptor đó *mutable* thì hỏng thế nào?
3. Nếu bỏ lời gọi `self.kernel.freeze()` trong `create_root`, kịch bản hỏng cụ thể nào
   có thể xảy ra khi hai session chạy song song?
