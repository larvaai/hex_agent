# Case 03 — Secret Masking Before UI (SRP)

> Một class guardrail, một actor: đội **UI/Observability**. Một việc: tách payload thành
> **(an toàn cho UI) + (đường dẫn secret để audit)**.

---

## 1. Bối cảnh trong hex_agent

Mọi payload trước khi tới UI/SSE phải đi qua một ranh giới bảo mật cứng: không được để
`api_key`, `password`, `token`, `cookie`... rò ra. `control/redaction.py` (file `1-74`, đã mở
kiểm chứng) đặt một class `Redactor` đúng tại ranh giới đó.

`Redactor` nhận `payload` thô, **đi đệ quy** xuống cả dict lẫn list, thay giá trị của mọi
key bí mật bằng `[REDACTED]`, đồng thời ghi lại đường dẫn đã che (dạng `a.b`, `a[0].b`) cho
audit trail. Quan trọng: **input gốc không bao giờ bị mutate** (`redaction.py:1-7` ghi rõ),
và class này KHÔNG validate event, KHÔNG route, KHÔNG lưu.

`control/emitter.py:56-58` cho thấy nó được gọi đúng tại cổng publish:
`final = self._redactor.apply(staged, level=spec.visibility)`.

---

## 2. Trích đoạn code thật

`control/redaction.py:50-63` — Masker đệ quy + MetadataRecorder:

```python
    def _walk(self, value: Any, path: str, fields: list[str]) -> Any:
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for key, item in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if self._is_secret(str(key)):
                    out[key] = REDACTED
                    fields.append(child_path)
                else:
                    out[key] = self._walk(item, child_path, fields)
            return out
        if isinstance(value, list):
            return [self._walk(item, f"{path}[{index}]", fields) for index, item in enumerate(value)]
        return value
```

`control/redaction.py:65-73` — EventPatcher (trả bản copy, không mutate):

```python
    def apply(self, event: RuntimeEvent, *, level: str | None = None) -> RuntimeEvent:
        """Return a copy of ``event`` with ``ui_payload`` + ``redaction`` filled from ``payload``."""
        ui_payload, fields = self.redact(event.payload)
        info = RedactionInfo(
            level=level or event.redaction.level,
            has_secret=bool(fields),
            redacted_fields=tuple(fields),
        )
        return replace(event, ui_payload=ui_payload, redaction=info)
```

---

## 3. Ánh xạ vai trò pattern <-> code thật

| Vai trò (SRP) | Thành phần code thật | path:line |
|---|---|---|
| SecretIdentifier | `_is_secret` (so khớp tên key, lowercased) + `SECRET_KEYS` | `redaction.py:16-42` |
| Masker (đệ quy) | `_walk` (dict + list) | `redaction.py:50-63` |
| MetadataRecorder | `fields.append(child_path)` trong `_walk` + `redact` trả `sorted(set(fields))` | `redaction.py:44-63` |
| EventPatcher | `apply` (điền `ui_payload` + `RedactionInfo`, dùng `replace`) | `redaction.py:65-73` |

Bốn vai phục vụ **đúng một mục đích**: split payload thành safe-for-UI + secret-audit-trail.

---

## 4. Bản rút gọn chạy được

File: [`event_redaction.py`](./event_redaction.py) — chạy `python3 event_redaction.py`.

**Mô phỏng đúng:** thuật toán `_walk` đệ quy y nguyên, cách đánh path `a.b` / `a[i].b`, tính
case-insensitive của `_is_secret`, và `apply` dùng `dataclasses.replace` nên không mutate
event gốc.

**Lược bỏ:** `RuntimeEvent`/`RedactionInfo` thật (từ `control/events.py`, có nhiều field như
`actor`, `trace`, `seq`...) được thay bằng hai dataclass tối thiểu cùng tên vai trò. Logic
redact **không đổi một dòng**.

Demo: secret ở top-level và trong dict/list lồng đều bị che; path ghi đúng; **assert bất biến
payload gốc không đổi**; `apply` trả event mới còn event cũ nguyên; case `API_KEY`/`Cookie`
viết hoa vẫn bị bắt. Có đối chứng "nếu nhét redaction vào emitter thì mỗi sink phải tự nhớ
che, dễ sót".

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Chi phí:** một lớp đi-qua thêm trước mọi publish; với payload rất lớn, `_walk` copy toàn
  bộ cây (đây là cố ý: để không mutate gốc).
- **Khi nào KHÔNG cần:** nếu hệ thống không bao giờ chuyển secret trong payload (vd UI chỉ
  nhận id tham chiếu), guardrail này có thể là thừa.
- **Cảnh báo:** `SECRET_KEYS` là exact-match theo tên key. Một key tên lạ chứa secret
  (`my_private_thing`) sẽ KHÔNG bị bắt — đây là giới hạn đã biết của cách so-khớp-tên; đừng
  hiểu nhầm Redactor là "phát hiện secret theo nội dung".

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `apply` dùng `replace(event, ...)` để tạo bản mới thay vì gán
   `event.ui_payload = ...`? Bất biến nào sẽ vỡ nếu mutate tại chỗ?
2. `_walk` đệ quy xuống cả list. Với `{"items": [{"token": "x"}]}`, path ghi ra là gì, và vì
   sao việc theo dõi path lại thuộc cùng actor với việc che?
3. Nếu cần thêm một key bí mật mới (vd `bearer`), bạn phải sửa bao nhiêu file/chỗ trong
   thiết kế SRP này? So sánh với trường hợp redaction bị rải khắp các sink.
