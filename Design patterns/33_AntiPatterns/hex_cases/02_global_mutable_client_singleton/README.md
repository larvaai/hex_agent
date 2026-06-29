# Case 02 — Global Mutable Module-Level Client

> **Anti-pattern**: Global Mutable State, kèm Cargo Cult Singleton và Premature
> Optimization.
> **Bệnh lý não (Lesson 33)**:
> - mục 1.3.c *Loss of diversity* — cocaine addiction ép mọi reward dồn về **một** đường
>   dopamine. Ở code: mọi `call_llm` dồn về **một** `_client` chung.
> - mục 1.3.d *Wrong timing* — Premature Optimization: cache trước khi đo, mất flexibility.

---

## 1. Bối cảnh trong hex_agent

`llm/adapter.py` là adapter gọi endpoint chat tương thích OpenAI cho local model. Để tránh
import `openai` ở thời điểm load module (một mong muốn *chính đáng*: "lazy import"), tác giả
khai báo một biến module-level `_client` (dòng 9), khởi tạo lười trong `_get_client()` (dòng
25-32), và cung cấp `reset_client()` (dòng 35-37) để xoá cache.

Vấn đề: "lazy import" bị trộn lẫn với "global mutable cache". Một instance `OpenAI` **duy
nhất** được tạo ở lần gọi đầu rồi chia sẻ cho **mọi** caller về sau, sống mãi cho tới khi
ai đó nhớ gọi `reset_client()`. `call_llm()` (dòng 72-77) tuy *có* cửa dependency injection
(tham số `client=`), nhưng mặc định vẫn rơi về `_get_client()` toàn cục.

Hệ quả thực tế:
- **Test mất isolation**: các test chia sẻ chung `_client`; quên `reset_client()` giữa các
  test → state rò từ test này sang test khác.
- **Coupling toàn cục**: không thể có hai cấu hình LLM song song (vd hai base_url) trong
  cùng tiến trình — kẻ init đầu tiên "khoá" cấu hình.
- **Premature Optimization**: chi phí tạo client/import là không đáng kể, nhưng cái cache
  toàn cục đổi lấy nó bằng chi phí coupling cao.

File đã mở kiểm chứng: `/Users/uspro/Desktop/namnson/hex_agent/llm/adapter.py`, dòng 9,
25-37, và 72-77.

---

## 2. Trích đoạn code thật

```python
# llm/adapter.py:9
_client: Any = None
```

```python
# llm/adapter.py:25-37
def _get_client() -> Any:
    global _client
    if _client is None:
        from openai import OpenAI  # lazy import

        cfg = _defaults()
        _client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"], timeout=cfg["timeout"])
    return _client


def reset_client() -> None:
    global _client
    _client = None
```

```python
# llm/adapter.py:72-77 — cửa DI có sẵn, nhưng mặc định rơi về global
def call_llm(messages, *, model=None, temperature=0.2, json_mode=True, client=None) -> str:
    cfg = _defaults()
    active = client if client is not None else _get_client()
    ...
```

---

## 3. Bảng ánh xạ vai trò pattern ↔ code thật

| Vai trò trong anti-pattern | Code thật (`llm/adapter.py`) | Bản distill (`global_mutable_client_singleton.py`) |
|----------------------------|------------------------------|----------------------------------------------------|
| Biến trạng thái toàn cục mutable | `_client: Any = None` (dòng 9) | `_client: Optional[FakeClient] = None` |
| Lazy-init + cache toàn cục | `_get_client()` (25-32) | `_get_client()` |
| Đường thoát (dễ quên) | `reset_client()` (35-37) | `reset_client()` |
| Caller rơi về global | `call_llm()` (72-77) | `call_llm_global()` |
| Hạ tầng nặng (LLM/network) | `openai.OpenAI(...)` | `FakeClient(base_url=...)` (stdlib) |
| (Đối chứng) bản chữa: factory + DI | *cửa `client=` có sẵn nhưng mặc định global* | `make_client()` + `call_llm_di()` |

---

## 4. Bản rút gọn chạy được

File: [`global_mutable_client_singleton.py`](./global_mutable_client_singleton.py)
(`python3 global_mutable_client_singleton.py`, chỉ stdlib).

**Mô phỏng gì**: giữ đúng *bộ ba* `_client` global / `_get_client()` lazy-cache /
`reset_client()`, cùng cửa DI `call_llm_di()`. `FakeClient` thay `openai.OpenAI` và nhớ
`base_url` để ta *nhìn thấy* "call này thực sự đi tới endpoint nào".

Ba kịch bản đối chứng:
- **(A)** Hai caller, hai cấu hình (`server-A` vs `server-B`). Bản global: caller thứ hai
  **bị route nhầm** sang `server-A` vì `_client` đã cache lần đầu (`_created_count == 1`).
  Bản DI: mỗi caller đúng endpoint (`_created_count == 2`).
- **(B)** Cùng hai caller với factory/DI — isolation phục hồi.
- **(C)** Dưới *đồng thời* (hai thread đồng bộ qua `Barrier`): bản global ép **mọi** luồng
  về đúng **một** endpoint (kẻ thắng cuộc đua init); bản DI giữ đúng hai endpoint riêng.

Các `assert` chứng minh: global luôn tạo đúng 1 instance và làm caller-2 nhận endpoint của
caller-1; DI tạo 1 instance/cấu hình và mỗi caller giữ đúng endpoint; dưới đồng thời, global
hội tụ về 1 endpoint (`len(distinct)==1`) còn DI giữ 2 (`len(distinct)==2`).

**Lược bỏ gì**: không có `openai`, không network, không retry/backoff thật (đó là phần
*đúng đắn* của `call_llm`, không liên quan anti-pattern này). `FakeClient.chat()` chỉ trả
chuỗi mã hoá `base_url`.

---

## 5. Cái giá / khi nào KHÔNG nên (và khi nào CHẤP NHẬN được)

**Cái giá**:
- **Mất isolation test**: state rò giữa các test trừ khi *luôn nhớ* `reset_client()` —
  đúng kiểu lỗi dễ quên nhất.
- **Không chạy song song nhiều cấu hình**: một tiến trình chỉ "ôm" được một client; muốn
  hai base_url đồng thời là bất khả với đường mặc định.
- **Cargo Cult**: "lazy nên cache toàn cục" là suy luận sai. *Lazy* nghĩa là *hoãn tạo tới
  khi cần*, không nghĩa là *tái dùng mãi một instance*. Hai khái niệm bị gộp.
- **Premature Optimization**: tối ưu (cache) một thứ rẻ (tạo client) bằng giá đắt (coupling).

**Khi nào việc này *chấp nhận được***:
- Khi đối tượng thật sự là **một tài nguyên dùng chung, không trạng thái-theo-caller, đắt
  để tạo** (vd: connection pool có khoá thread đúng, cấu hình *bất biến* toàn tiến trình).
  Lúc đó singleton là quyết định kiến trúc hợp lý — nhưng nên *bất biến* và *được tiêm vào
  qua composition root*, không phải biến module-level mà ai cũng `global` được.
- Bản chữa nhẹ nhất ở đây **đã có sẵn**: tham số `client=` của `call_llm`. Chỉ cần làm DI
  trở thành đường *chính* (composition root tạo client một lần, truyền xuống), còn
  `_get_client()` lùi về một fallback rõ ràng — hoặc bỏ hẳn global, dùng factory.
- Quy tắc Lesson 33: đừng "loại bỏ 100%" một cách máy móc. Với một CLI single-config chạy
  một lần rồi thoát, global client gần như vô hại. Anti-pattern này "cắn" mạnh nhất ở
  **test** và **đa cấu hình** — đúng hai bối cảnh `hex_agent` quan tâm (có server UI chạy
  nhiều run, có test suite).

---

## 6. Câu hỏi tự kiểm tra

1. Trong `_get_client()` thật, `base_url`/`cfg` được đọc ở thời điểm nào, và điều gì xảy ra
   nếu caller thứ hai muốn một `base_url` khác? (Gợi ý: chạy `.py`, xem mục (A).)
2. Phân biệt "lazy import" (điều *đúng* mà tác giả muốn) với "global mutable cache" (điều
   *vô tình* kèm theo). Làm sao có lazy mà không có global?
3. `call_llm()` đã có tham số `client=`. Bạn sẽ tái cấu trúc thế nào để DI thành đường
   chính và xoá sự phụ thuộc vào `_client` toàn cục? Nêu rủi ro nếu *quên* `reset_client()`
   giữa hai test.
