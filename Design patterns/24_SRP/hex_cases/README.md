# SRP trong hex_agent — Hex Cases (Lesson 24)

> **SRP** = một module/class chỉ có **MỘT lý do để thay đổi** — nghĩa là chỉ phục vụ **MỘT
> actor/stakeholder** (Robert C. Martin). Không phải "1 class làm 1 việc nhỏ", mà là "1 class
> chỉ trả lời cho 1 nhóm người ra lệnh thay đổi".

Bộ case này soi **Single Responsibility Principle xuất hiện thật** trong codebase `hex_agent`.
Mỗi case lấy một module/class có thật, mở file kiểm chứng path:line, rồi distill thành một file
Python **chạy được, chỉ dùng thư viện chuẩn**, giữ đúng vai trò pattern nhưng thay hạ tầng
nặng (LLM/DB/network/file/YAML) bằng fake tối thiểu.

Tham chiếu bài học gốc: [`../24_SRP.md`](../24_SRP.md).

---

## hex_agent tuân thủ SRP thế nào

Codebase phân rã module một cách hệ thống qua các tầng **control / discipline / adapter**.
Mỗi module/class được giới hạn hẹp vào **một stakeholder hoặc một concern**:

- **JsonGateError parsing** — đội discipline/JSON-gate.
- **Budget accounting** — đội run-control (loop orchestrator).
- **Permission validation** — đội security.
- **Event registration / redaction** — đội observability.
- **Authz predicates** — các cổng security.

Kiến trúc tránh god class bằng cách tách **định nghĩa protocol** (`ports/`) khỏi **hiện thực
cụ thể** (`adapters/`), và uỷ thác các concern chuyên biệt cho những module tập trung.

---

## Các case con

| # | Case | Module thật | Actor duy nhất | File chạy |
|---|------|-------------|----------------|-----------|
| 01 | [JSON Output Repair Pipeline](./01_json_gate_parsing/) | `discipline/json_gate.py:1-494` | Validation / JSON-gate | [`json_gate_parsing.py`](./01_json_gate_parsing/json_gate_parsing.py) |
| 02 | [Loop Budget Tracker](./02_budget_accounting/) | `discipline/budget.py:1-68` | Run-orchestration (loop) | [`budget_accounting.py`](./02_budget_accounting/budget_accounting.py) |
| 03 | [Secret Masking Before UI](./03_event_redaction/) | `control/redaction.py:1-74` | UI / Observability | [`event_redaction.py`](./03_event_redaction/event_redaction.py) |
| 04 | [Event-Type Catalog](./04_event_registry/) | `control/event_registry.py:1-100` | Control-plane / deployment eng | [`event_registry.py`](./04_event_registry/event_registry.py) |
| 05 | [Permission Escalation Detection](./05_authorization_predicates/) | `control/authz.py:1-50` | Security checkpoint (S21.6) | [`authorization_predicates.py`](./05_authorization_predicates/authorization_predicates.py) |

Danh mục **vét cạn** mọi occurrence (cả các chỗ ngoài 5 flagship): xem
[`CATALOG.md`](./CATALOG.md).

---

## Cách chạy

```bash
# từng case
python3 01_json_gate_parsing/json_gate_parsing.py
python3 02_budget_accounting/budget_accounting.py
python3 03_event_redaction/event_redaction.py
python3 04_event_registry/event_registry.py
python3 05_authorization_predicates/authorization_predicates.py
```

Mỗi file in narration tiếng Việt từng bước, có `assert` chứng minh bất biến của pattern, và ít
nhất một đối chứng "khi KHÔNG dùng pattern thì hỏng/khó thế nào". Tất cả thoát code 0, không
phụ thuộc thư viện ngoài, không import `hex_agent`.

---

## Sợi chỉ đỏ chung cho cả 5 case

1. **Đặt được tên actor** — mỗi module nêu được "đổi khi nhóm X yêu cầu" với X cụ thể.
2. **Cohesion cao** — mọi field/hàm cùng phục vụ một trục trách nhiệm (LCOM4 = 1).
3. **Test cô lập** — distill được mà KHÔNG cần dựng DB/LLM/network: bằng chứng SRP đã đúng.
4. **Đổi một luật chỉ đụng một file** — không lan (no ripple) sang storage, dispatch, hay
   business logic.
5. **Tách định nghĩa khỏi thực thi** (rõ nhất ở case 04) — đặt nền cho OCP (lesson 25).
