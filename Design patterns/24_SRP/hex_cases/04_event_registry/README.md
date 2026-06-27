# Case 04 — Event-Type Catalog with Visibility (SRP)

> Một registry, một actor: đội **Control-plane / deployment eng**. Một việc: là **nguồn sự
> thật** khai báo "event type nào hợp lệ + ai được thấy".

---

## 1. Bối cảnh trong hex_agent

Trong hệ event-driven, nếu mỗi module tự đặt tên event và tự liệt kê "type nào hợp lệ", các
module sẽ lệch nhau và một type gõ sai sẽ lọt qua silently rồi vỡ ở downstream.

`control/event_registry.py` (file `1-100`, đã mở kiểm chứng) tách **định nghĩa** khỏi **thực
thi**: `EventTypeRegistry` giữ một dict các `EventTypeSpec` (nạp từ
`config/runtime_event_types.yaml`), phơi một query API thuần đọc, và quan trọng nhất —
`assert_known` ném `ControlContractError` khi gặp type lạ.

Điểm SRP cốt lõi nằm ở `control/emitter.py:56`: `spec = self._registry.get(event.event_type)`
được gọi **trước** khi publish. Nếu type lạ thì **REGISTRY ném**, không phải emitter. Thêm
event type mới = sửa YAML rồi restart, KHÔNG đụng code emitter/authz/redactor.

---

## 2. Trích đoạn code thật

`control/event_registry.py:47-61` — Validator (gate) + QueryPort:

```python
    def assert_known(self, event_type: str) -> None:
        if event_type not in self._specs:
            raise ControlContractError(
                f"Unknown event_type: {event_type!r}. Declare it in runtime_event_types.yaml."
            )

    def get(self, event_type: str) -> EventTypeSpec:
        self.assert_known(event_type)
        return self._specs[event_type]

    def visibility(self, event_type: str) -> str:
        return self.get(event_type).visibility

    def types(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))
```

`control/emitter.py:56-61` — emitter dùng registry làm cổng gác, không tự quyết:

```python
        spec = self._registry.get(event.event_type)  # ControlContractError if unknown
        staged = event if event.seq else replace(event, seq=self._seq.next(event.session_id))
        final = self._redactor.apply(staged, level=spec.visibility)
        for sink in self._sinks:
            sink.emit(final)
        return final
```

---

## 3. Ánh xạ vai trò pattern <-> code thật

| Vai trò (SRP) | Thành phần code thật | path:line |
|---|---|---|
| Catalog | `EventTypeRegistry._specs` (dict theo `event_type`) + `EventTypeSpec` | `event_registry.py:22-42` |
| QueryPort | `__contains__`, `get`, `visibility`, `types` | `event_registry.py:44-61` |
| Validator (gate) | `assert_known` (ném `ControlContractError`) | `event_registry.py:47-51` |
| Parser | `parse_event_registry` (kiểm cấu trúc YAML, validate visibility) | `event_registry.py:64-93` |
| Enforcement (actor khác) | `EventEmitter.emit_event` gọi `registry.get` | `emitter.py:53-61` |

Registry trả lời "type này hợp lệ không / ai được thấy"; emitter chỉ publish. Hai trách nhiệm,
hai actor, tách bạch.

---

## 4. Bản rút gọn chạy được

File: [`event_registry.py`](./event_registry.py) — chạy `python3 event_registry.py`.

**Mô phỏng đúng:** `EventTypeSpec`, `EventTypeRegistry` với toàn bộ query API,
`assert_known` làm gate, `parse_event_registry` kiểm tra cấu trúc + validate `visibility`, và
một `EventEmitter` thu nhỏ gọi `registry.get` trước khi "publish" vào list.

**Lược bỏ:** việc đọc YAML từ đĩa được thay bằng một `dict` Python in-memory — đúng như
`parse_event_registry` gốc vốn nhận `data: dict` *đã* được `yaml.safe_load`, nên không cần
`pyyaml`. `ControlContractError` là Exception tự định nghĩa thay cho `control/errors.py`.

Demo: dựng registry từ config in-memory; assert mọi visibility hợp lệ; type lạ bị chặn TẠI
REGISTRY (emitter không publish); **thêm type mới chỉ bằng sửa config, emitter dùng lại y
nguyên** (đặt nền cho OCP ở lesson 25); Parser từ chối `visibility='world_readable'` (giá trị
KHÔNG nằm trong `VISIBILITY_LEVELS`). Có đối chứng
"không registry -> mỗi emitter tự liệt kê -> Shotgun Surgery".

> **Đối chiếu thật:** `VISIBILITY_LEVELS` ở đây chép nguyên 5 mức từ `control/events.py:25` —
> `{'public', 'ui_safe', 'internal', 'secret', 'restricted'}`. Vì `'public'` LÀ mức hợp lệ
> trong hệ thật, ví dụ "visibility sai" dùng `'world_readable'` (giá trị bịa) để không mâu
> thuẫn với hành vi thật của Parser.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Chi phí:** thêm một file cấu hình + một bước nạp; với hệ chỉ có 2-3 event cố định, một
  `frozenset` hằng có thể đủ.
- **Khi nào KHÔNG cần:** prototype không có yêu cầu phân quyền visibility, không có người
  ngoài team muốn thêm event type.
- **Cảnh báo:** registry là single source of truth — nếu để hai nguồn (YAML + một list
  hard-code) thì lợi ích biến mất. Giữ đúng một nguồn.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao việc "type lạ thì ai ném lỗi" lại quan trọng cho SRP? Điều gì xảy ra với tính tách
   bạch nếu chính `EventEmitter` tự giữ danh sách type hợp lệ?
2. `parse_event_registry` validate `visibility` nằm trong `VISIBILITY_LEVELS` ngay lúc nạp.
   Vì sao bắt lỗi lúc nạp tốt hơn bắt lỗi lúc publish?
3. Để thêm event type `agent.after_run` với `visibility: ui_safe`, theo thiết kế này bạn cần
   đụng bao nhiêu file mã nguồn? Câu trả lời nói gì về quan hệ SRP -> OCP?
