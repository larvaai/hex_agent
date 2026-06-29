# Anti-Patterns trong hex_agent — Hồ sơ bệnh lý (Pathology Atlas)

> Tài liệu này soi codebase `hex_agent` qua **lăng kính phòng ngự** của Lesson 33.
> Không phải để "bắt lỗi" tác giả, mà để *luyện con mắt 30 giây/file*: thấy smell, gọi
> tên anti-pattern, chỉ ra nguyên lý vi phạm và lesson chữa.

Nhắc lại quy tắc vàng của bài học gốc:

> **Không có code production hoàn hảo.** Mọi codebase có 1-2 anti-pattern *chấp nhận
> được*. Mục tiêu là *nhận biết và quản lý*, không phải "loại bỏ 100%".

`hex_agent` nhìn chung là một codebase **khỏe**: có boundary kiến trúc rõ (Hexagonal —
`core/`, `discipline/`, `llm/`, `control/`, `ui/`), phần lớn class tuân thủ SRP, đặt tên
theo domain chứ không phải `*Manager`/`*Helper`. Nhưng nó vẫn mang **2 anti-pattern thật**
đáng đem ra giảng, cộng một loạt smell *borderline* (chấp nhận được nhưng đáng nhìn kỹ).

---

## TÓM TẮT — pattern "Anti-Patterns" hiện diện ở đâu

| # | Anti-pattern | Vị trí thật | Bệnh lý não (Lesson 33) | Nguyên lý vi phạm |
|---|--------------|-------------|-------------------------|-------------------|
| 01 | **Swallowing Exceptions** (nuốt ngoại lệ) | `discipline/json_gate.py:338-343`, `:373-378` | Demyelination MS — *mất lớp cách điện / mất tín hiệu* | Mất ngữ cảnh lỗi; debug bị mù |
| 02 | **Global Mutable State** + Cargo Cult Singleton + Premature Optimization | `llm/adapter.py:9, 25-37` | Cocaine: *mọi reward → một đường dopamine* (mất diversity) + pruning sai timing | Coupling toàn cục; test mất isolation |

Hai anti-pattern này được **distill** thành code chạy được trong các thư mục con
`01_*/` và `02_*/`. Mỗi case có:
- `README.md` — bài học 6 mục (bối cảnh thật, trích code thật, bảng ánh xạ vai trò, bản
  rút gọn, cái giá, câu hỏi tự kiểm tra).
- `<name>.py` — bản distill **chỉ dùng stdlib Python 3.14**, có `demo()`, có đối chứng
  "khi KHÔNG dùng pattern", có `assert` chứng minh bất biến.

---

## DANH SÁCH CASE CON (flagship)

### [01_swallowed_exceptions_json_repair](./01_swallowed_exceptions_json_repair/)
**Swallowing Exceptions in JSON Repair Pipeline** — điểm giảng: *mất ngữ cảmh lỗi*.

`discipline/json_gate.py` có hàm `_safe()` (dòng 338-343) bắt **toàn bộ** `Exception` rồi
trả `None` *không log một dòng nào*. `try_literal_eval()` (dòng 373-378) cũng nuốt ngoại
lệ y hệt. Hậu quả: khi LLM trả JSON hỏng và pipeline retry mãi không thoát, người debug
*không phân biệt được* "rule X chạy và thất bại" với "rule X chưa bao giờ được gọi tới".
Thông tin "tại sao parse hỏng" bốc hơi.

Ánh xạ neuroscience: **Loss of insulation** (demyelination MS) — đường truyền không có
lớp cách điện thì tín hiệu (ở đây là *ngữ cảnh lỗi*) bị nhiễu/biến mất.

### [02_global_mutable_client_singleton](./02_global_mutable_client_singleton/)
**Global Mutable Module-Level Client** — Cargo Cult Singleton + Premature Optimization.

`llm/adapter.py` khai báo biến module-level `_client` (dòng 9), lazy-init trong
`_get_client()` (dòng 25-32), và reset bằng `reset_client()` (dòng 35-37). Một instance
`OpenAI` duy nhất được chia sẻ cho **mọi** lời gọi, sống mãi cho tới khi ai đó nhớ gọi
`reset_client()`. "Lazy import" là hợp lý — nhưng *lazy ≠ global + mutable*. Cái cache
toàn cục này gây coupling giữa mọi call, làm test chia sẻ state và dễ rò state giữa các
test nếu quên reset.

Ánh xạ neuroscience: **Loss of diversity** (cocaine: mọi reward dồn về một đường dopamine)
— mọi call dồn về một instance chung; cộng **Premature Optimization** (cache trước khi đo,
trong khi chi phí import là không đáng kể còn chi phí coupling thì cao).

---

## CÁC SMELL CÒN LẠI (borderline)

Xem bảng vét cạn trong [CATALOG.md](./CATALOG.md). Đó là các occurrence *chấp nhận được*
trong bối cảnh domain (event-fold phức tạp, chuỗi repair JSON, threading có lock đúng...)
nhưng đáng đưa vào checklist code review để "trigger conversation", đúng tinh thần Mục
Architect của bài học gốc.

> Đọc thứ tự đề xuất: `README.md` (file này) → `01_*` → `02_*` → `CATALOG.md`.
