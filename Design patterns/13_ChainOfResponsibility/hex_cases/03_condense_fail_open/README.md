# Case 03 — `CondenseResult`: handler modulate-and-forward + fail-open / `_LatchedNext`

> Biến thể thứ ba (và đặc trưng nhất của kiểu middleware) của CoR trong hex_agent: một handler **gọi `nxt` trước**, rồi **sửa (modulate) result envelope** rồi forward ra ngoài — khác hẳn case 02 (`PolicyGate`) chỉ chọn handle-hoặc-forward. Case này còn distill hai tư thế lỗi **fail-open / fail-closed** và cơ chế one-shot `_LatchedNext` bảo đảm tool chạy đúng một lần.

---

## 1. Bối cảnh trong hex_agent

Sau khi một tool chạy xong, result có thể rất lớn (blob, list dài) và sẽ được nạp lại cho model. `CondenseResult` là một middleware **hậu xử lý**: nó gọi `nxt(request)` để lấy result của tool, rồi **rút gọn field `data`** trước khi trả về. Đây là quyền thứ ba mà interface Handler cho phép — *"modify the result envelope"* (`core/middleware.py:13`) — và là điều `PolicyGate` (case 02) không bao giờ làm.

`CondenseResult` còn minh hoạ **tư thế lỗi** của hệ middleware:

- Nó tự đánh dấu `fail_open = True` (`middleware/condense.py:12`) — nghĩa là **advisory** (rút gọn không bao giờ được làm hỏng một tool call đã `ok`).
- Kernel đọc cờ này ở `_wrap` (`core/kernel.py:58, 64-73`): nhánh fail-open bọc `nxt` bằng `_LatchedNext` rồi `try/except`; nếu advisory raise thì kernel **skip** nó, phát event `middleware.skipped` (`core/kernel.py:179-190`) và trả về inner result thay vì fail call.
- Ngược lại, middleware **không** đánh dấu `fail_open` (mọi gate/guard) là **blocking** (mặc định): raise sẽ nổi ra biên kernel thành `ok=False` (`core/kernel.py:58-62, 197-203`).

Cuối cùng, `_LatchedNext` (`core/kernel.py:24-46`) là proxy one-shot quanh handler kế tiếp: chạy `nxt` **tối đa một lần**, lần sau replay outcome cũ. Nó phòng đúng một failure mode (FM-HIGH): một fail-open middleware gọi `nxt` (tool chạy) rồi raise *sau đó* — nếu fallback gọi lại `nxt` thì tool non-idempotent sẽ chạy hai lần.

Vấn đề thật được giải: tách concern "rút gọn output" ra khỏi tool và khỏi client, đồng thời cho phép một số middleware "mềm" (telemetry/condense) hỏng mà không kéo sập cả tool call — nhưng vẫn an toàn với tool có side-effect.

## 2. Trích đoạn code thật

Handler modulate-and-forward (`middleware/condense.py:11-30`):

```python
class CondenseResult:
    fail_open = True  # advisory shrink — a condense failure must not fail an ok tool call
    ...
    def __call__(self, request: ToolRequest, nxt) -> dict[str, Any]:
        env = nxt(request)                       # forward TRƯỚC, lấy result
        if request.name.startswith("llm."):
            return env                            # llm.* không bị rút gọn
        if isinstance(env, dict) and isinstance(env.get("data"), (dict, list, str)):
            condensed = condense(env["data"], max_chars=self.max_chars, max_list=self.max_list)
            changed = condensed != env["data"]
            env["data"] = condensed              # <- MODULATE result
            if changed and self.on_condense:
                self.on_condense(request)
        return env                               # <- forward result ra ngoài
```

Hai tư thế lỗi trong chain builder (`core/kernel.py:58-73`):

```python
if getattr(middleware, "fail_open", False) is not True:
    def handler(request):
        return middleware(request, nxt)          # fail-closed: raise nổi ra biên
    return handler

def handler(request):                            # fail-open (advisory)
    latched = _LatchedNext(nxt)
    try:
        return middleware(request, latched)
    except Exception as exc:                      # advisory hỏng -> skip, giữ inner result
        if on_skip is not None:
            on_skip(middleware, exc)
        return latched(request)                   # replay, KHÔNG chạy lại tool
```

Proxy one-shot (`core/kernel.py:37-46`):

```python
def __call__(self, request: ToolRequest) -> dict[str, Any]:
    if not self._ran:
        self._ran = True
        try:
            self._result = self._nxt(request)
        except Exception as exc:                  # lưu để replay, không chạy lại
            self._exc = exc
    if self._exc is not None:
        raise self._exc
    return self._result
```

Tests cố định hành vi:

```python
# tests/test_middleware.py:53-71 — rút gọn tool, bỏ qua llm.*
assert len(r["data"]["echo"]["blob"]) < 120          # tool result condensed
assert len(rl["data"]["content"]) == 500             # llm.* NOT condensed

# tests/test_middleware.py:111-125 — advisory raise -> fail-open
assert r["ok"] is True                    # advisory failure did NOT block the call
assert skipped == ["middleware.skipped"]  # swallow is observable, not silent

# tests/test_middleware.py:160-187 — advisory raise sau nxt -> tool chạy đúng 1 lần
assert counter.n == 1          # executor ran EXACTLY once
assert r["data"]["n"] == 1     # returns the one and only result
```

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò trong CoR | Thành phần trong hex_agent |
|---|---|
| `ConcreteHandler` (modulate-and-forward) | `CondenseResult` — `middleware/condense.py:11-30` |
| forward sang handler kế tiếp | `env = nxt(request)` — `condense.py:21` |
| sửa result envelope (post-process) | `env["data"] = condensed` — `condense.py:27` |
| chọn KHÔNG modulate (passthrough có điều kiện) | `if request.name.startswith("llm."): return env` — `condense.py:22-23` |
| cờ tư thế lỗi (advisory) | `fail_open = True` — `condense.py:12` |
| nhánh fail-open trong chain builder | `_wrap(...)` nhánh advisory — `core/kernel.py:64-73` |
| nhánh fail-closed (mặc định) | `_wrap(...)` nhánh blocking — `core/kernel.py:58-62` |
| proxy one-shot quanh `next` | `_LatchedNext` — `core/kernel.py:24-46` |
| hook quan sát skip | `on_skip` -> event `middleware.skipped` — `core/kernel.py:179-190` |

## 4. Bản rút gọn chạy được

File: [`condense_fail_open.py`](./condense_fail_open.py) — chạy `python3 condense_fail_open.py`.

Nó mô phỏng:
- `CondenseShrink` distill gần nguyên văn `CondenseResult` (kèm `fail_open=True`, bỏ qua `llm.*`, callback `on_condense`); `condense()` distill `discipline/condense.py:13-24`.
- `_wrap` distill **cả hai** nhánh của `core/kernel.py:49-73` (khác case 01/02 chỉ lấy nhánh fail-closed), `_LatchedNext` distill `core/kernel.py:24-46`.
- `MiniKernel` truyền `on_skip` và ghi vào list `skipped` (thay cho `EventBus`/event `middleware.skipped`).
- Năm màn: (1) modulate-and-forward rút gọn result, (2) cùng handler nhưng passthrough nguyên vẹn với `llm.*`, (3) fail-open: advisory raise → call vẫn `ok`, có ghi nhận `skipped`, (4) fail-closed: blocking raise → `ok=False`, (5) latch: advisory gọi `nxt` rồi raise → tool chạy **đúng một lần**.

Đã **lược bỏ**: `ToolRequest`/`CapabilityResult` schema, `EventBus` thật (thay bằng list), `discipline.condense` import (inline lại), wiring qua `core/bootstrap.py`. Trọng tâm giữ nguyên: ba quyền của handler (đặc biệt là *modulate*), hai tư thế lỗi, và bất biến "tool chạy đúng một lần".

Đối chứng "không dùng pattern" / không tách tư thế lỗi: phần [4] cho thấy nếu một middleware không khai báo posture mà raise thì cả call hỏng (`ok=False`); chính cờ `fail_open` + nhánh `_wrap` riêng là thứ cho phép phân biệt "concern mềm được phép hỏng" với "gate phải fail-closed". Nếu nhồi rút gọn + đo lường thẳng vào client thì một lỗi rút gọn sẽ kéo sập tool call hợp lệ.

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Modulate result làm "sự thật" khó truy.** Sau khi `CondenseResult` sửa `data`, log/caller thấy bản đã rút gọn chứ không phải output gốc — debug khó hơn. Vì vậy bản thật bắn `on_condense`/event để việc rút gọn quan sát được.
- **Fail-open dễ giấu lỗi.** Một advisory hỏng âm thầm có thể che mất bug thật; hex_agent giảm rủi ro bằng cách phát `middleware.skipped` (không nuốt im lặng). Chỉ middleware **thật sự advisory** mới nên fail-open — mọi gate/guard phải để mặc định fail-closed.
- **Latch chỉ đúng cho nhánh fail-open.** `Retry` gọi `nxt` nhiều lần **có chủ đích** nên fail-closed và nhận `nxt` thô, KHÔNG latch (`core/kernel.py:56`). Dùng nhầm latch cho retry sẽ vô hiệu hoá retry. Vị trí một middleware trong phổ idempotent/posture rất quan trọng.
- **Thứ tự với handler khác.** Đặt `condense` trước hay sau `retry`/`timing` cho hành vi khác (rút gọn trước khi đo, hay đo trước khi rút gọn). Khi không cần hậu xử lý theo thứ tự, một bước transform đơn lẻ rõ hơn là nhét vào chuỗi.

## 6. Câu hỏi tự kiểm tra

1. `CondenseResult` gọi `nxt(request)` ở **dòng đầu** của `__call__`, còn `PolicyGate` (case 02) thì có thể **không bao giờ** gọi `nxt`. Khác biệt này phản ánh hai "quyền" nào khác nhau của một handler CoR?
2. Vì sao chỉ nhánh **fail-open** mới bọc `nxt` bằng `_LatchedNext`, còn nhánh fail-closed (gồm cả `Retry`) lại nhận `nxt` thô? Điều gì hỏng nếu latch luôn cả `Retry`?
3. Một advisory middleware gọi `nxt` (tool side-effect chạy) rồi raise trong hậu xử lý. Nếu `_wrap` ở fallback gọi `nxt` thật lần nữa thay vì `latched(request)`, failure mode gì xảy ra với một tool non-idempotent? (Gợi ý: `core/kernel.py:24-27`.)
4. `CondenseResult` chủ động `return env` ngay cho tool `llm.*` mà không modulate. Vì sao một handler "modulate-and-forward" đôi khi lại chọn **không** modulate, và điều đó có vi phạm vai trò CoR của nó không?
