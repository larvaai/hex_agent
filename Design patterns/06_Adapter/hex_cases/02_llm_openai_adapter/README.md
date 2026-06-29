# Case 02 — Adapter LLM: bọc client kiểu-OpenAI, dịch lỗi thành envelope JSON

> Adapter ở đây là **lớp dịch interface + chống đỡ (resilience)** thuần túy. API
> `openai.OpenAI` có thể ném exception và trả về nhiều status khác nhau; `call_llm()`
> dịch mọi mode lỗi thành một envelope JSON ổn định để **caller không bao giờ phải bắt
> exception**.

---

## 1. Bối cảnh trong hex_agent

Vòng lặp agent (ReAct) cần gọi một mô hình ngôn ngữ qua HTTP kiểu-OpenAI (LM Studio,
llama.cpp, vLLM...). Những server local này hay hỏng theo nhiều kiểu khó chịu:
- server chưa bật → kết nối bị refuse (lỗi #1 của local-LLM);
- timeout, rớt kết nối, 429, 5xx — đáng retry;
- một số server từ chối `response_format={"type":"json_object"}` và 400.

Domain không muốn rải `try/except` ở mọi nơi gọi LLM. Vì vậy `call_llm()` đứng làm
**Adapter**: target interface là `call_llm(messages, json_mode=True) -> str` với cam kết
**không bao giờ raise** — luôn trả một chuỗi JSON (kết quả thật, hoặc envelope lỗi).

File:line thật (đã mở kiểm chứng):
- `llm/adapter.py:72-119` — `call_llm(...)`: vòng retry + exponential backoff, downgrade
  `json_object → text`, và ráp thông điệp lỗi actionable.
- `llm/adapter.py:25-32` — `_get_client()`: lazy tạo `openai.OpenAI`, injectable (tham số
  `client` cho test).
- `llm/adapter.py:40-50` — `_is_transient()`: phân loại lỗi đáng retry (duck-typed, không
  import lớp exception của openai).
- `llm/adapter.py:53-59` — `_is_connection_error()`: phát hiện endpoint không tới được.
- `llm/adapter.py:62-69` — `_is_response_format_error()`: server từ chối json_object.
- `llm/adapter.py:105-119` — ráp `message` nêu URL + gợi ý "is the server running?" + cause.
- `tests/test_llm_adapter.py:54-82` — `_DeadClient` + `test_connection_failure_message_is_actionable`.

---

## 2. Trích đoạn code thật

Vòng gọi + xử lý lỗi — `llm/adapter.py:87-103`:

```python
while attempt < attempts:
    try:
        response = active.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""
    except Exception as exc:
        last_exc = exc
        if json_mode and not downgraded and _is_response_format_error(exc):
            kwargs["response_format"] = {"type": "text"}   # downgrade json_object -> text
            downgraded = True
            continue
        if attempt + 1 < attempts and _is_transient(exc):
            _sleep(cfg["retry_base"] * (2 ** attempt))      # backoff: 0.5, 1.0, 2.0, ...
            attempt += 1
            continue
        break
```

Dịch lỗi thành envelope actionable — `llm/adapter.py:113-119`:

```python
if last_exc is not None and _is_connection_error(last_exc):
    detail = f"{detail} — cannot reach the LLM at {cfg['base_url']}; is the server running?"
return json.dumps(
    {"action": "final", "finish_reason": "error",
     "message": f"LLM request failed after {attempt + 1} attempt(s): {detail}"},
    ensure_ascii=False,
)
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Adapter (GoF)             | Thành phần trong hex_agent                                         |
|-----------------------------------|-------------------------------------------------------------------|
| **Target** (interface + hành vi client kỳ vọng) | `call_llm()` signature + cam kết "luôn trả JSON, không raise" — `llm/adapter.py:72-119` |
| **Adaptee**                       | `openai.OpenAI` (qua `client.chat.completions.create`)            |
| **Adapter**                       | các hàm cấp-module `_get_client`, `_is_transient`, `_is_connection_error`, `call_llm` — `llm/adapter.py` |
| **Client**                        | `discipline.parse_action()` và code gọi agent / test               |
| **Test double cho Adaptee**       | `_FakeClient`, `_DeadClient` — `tests/test_llm_adapter.py:10-24, 54-68` |

Lưu ý phân biệt pattern: retry/backoff và downgrade là **tiện ích dịch interface**, không
phải logic nghiệp vụ. Nếu adapter bắt đầu quyết định "nên gọi tool nào" thì đã sang địa hạt
khác (Strategy/orchestrator), không còn là Adapter.

---

## 4. Bản rút gọn chạy được

File: [`llm_openai_adapter.py`](./llm_openai_adapter.py) — `python3 llm_openai_adapter.py`.

Mô phỏng:
- `call_llm()` cùng các helper `_is_transient` / `_is_connection_error` /
  `_is_response_format_error` — giữ nguyên vai trò gốc, cùng exponential backoff.
- Bốn adaptee giả: `_OkClient`, `_DeadClient` (mô phỏng `APIConnectionError`),
  `_FlakyThenOkClient` (503 vài lần rồi OK), `_RejectsJsonObjectClient`.
- Demo lần lượt: thành công; server chết → envelope nêu URL + gợi ý + cause; retry nuốt 503;
  hết retry vẫn trả envelope (không raise); downgrade json_object → text; và đối chứng
  `raw_call_no_adapter` gọi thẳng adaptee → lãnh exception mờ mịt.
- Các **assert** chứng minh: nội dung qua nguyên vẹn; `message` chứa URL + "is the server
  running" + "refused"; số lần gọi adaptee đúng với chính sách retry; thứ tự format thử
  đúng `[json_object, text]`.

Lược bỏ:
- `openai.OpenAI` thật + mạng → thay bằng client giả stdlib.
- Đọc cấu hình từ biến môi trường (`_defaults()` đọc `LLM_BASE_URL`, `LLM_MAX_RETRIES`...) →
  hằng số cố định cho demo; `_sleep` thành no-op để chạy nhanh (đúng như test monkeypatch
  `_sleep` ở `tests/test_llm_adapter.py:76`).

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Nuốt lỗi quá tay**: vì adapter không bao giờ raise, một lỗi cấu hình thật có thể bị
  chôn trong envelope. Phải đảm bảo caller thực sự đọc `finish_reason == "error"` (ở đây là
  `parse_action`), nếu không lỗi sẽ trôi qua âm thầm.
- **Phân loại lỗi bằng duck-typing** (`getattr(exc, "status_code")`, tên class chứa
  "connection") đánh đổi sự chặt chẽ lấy việc không phải import lớp exception của openai. Khi
  thư viện đổi cấu trúc exception, phân loại có thể sai — cần test canh giữ.
- Nếu bạn **đang sở hữu** cả hai phía và có thể đặt một interface chung ngay từ đầu, có khi
  không cần adapter — chỉ cần thiết kế API tốt. Adapter sáng giá nhất khi adaptee là
  third-party bạn không sửa được.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `call_llm()` chọn **không raise** mà trả envelope `final`/error? Điều gì sẽ khó hơn
   nếu nó raise như `openai` gốc?
2. Khi server từ chối `json_object`, vì sao adapter downgrade sang `text` mà **không tốn** một
   lượt retry (xem `downgraded` ở `llm/adapter.py:95-98`)?
3. `test_connection_failure_message_is_actionable` kiểm 3 thứ trong `message`. Đó là 3 thứ
   gì, và vì sao chúng quan trọng với người vận hành local-LLM?
