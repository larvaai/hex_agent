# Ubiquitous Language (DDD) trong hex_agent — Case study từ codebase thật

> Đi kèm bài học gốc: [`../40_UbiquitousLanguage.md`](../40_UbiquitousLanguage.md).
> Thư mục này KHÔNG phải lý thuyết lại — nó chỉ ra pattern **Ubiquitous Language (UL)**
> đang sống thật trong codebase `hex_agent` ở đâu, rồi distill mỗi chỗ thành một file
> Python chạy được chỉ bằng thư viện chuẩn.

## Ubiquitous Language là gì (nhắc 1 dòng)

UL là **ngôn ngữ chung giữa business expert và developer**, *strict trong một bounded
context*. Cùng một từ phải xuất hiện *giống nhau* trong code, test, doc, event và lời nói.
Khi term trôi (`Submission` ở code, `Attempt` ở test, `Try` ở meeting) — đó là *semantic
dementia* của codebase. Bài học 40 dạy: **giữ glossary as code, dò drift, lập kế hoạch
rename theo nhiều phase**.

## hex_agent thể hiện UL như thế nào

Không như nhiều project chỉ "đặt tên cho hay", `hex_agent` nâng UL lên thành *hạ tầng*:

1. **Glossary as code** — [`docs/GLOSSARY.md`](../../../docs/GLOSSARY.md) là sổ đăng ký
   thuật ngữ load-bearing (chokepoint, roster-growth, department alias, safe checkpoint,
   trust-O, authority gate, `attribution≠authz`...). Mỗi term có nghĩa + trỏ tới
   `file:line` định nghĩa nó. Glossary được **CI canh** bởi
   [`harness/tests/test_glossary_invariants.py`](../../../harness/tests/test_glossary_invariants.py):
   file không được mất, bảng không được rỗng hoá, các term core phải còn hàng.

2. **Event đặt tên bằng UL** — supervisor/delegation phát event `loop.team_composed`,
   `loop.decision`, `delegation.started`, `delegation.finished` — *tên theo nghĩa nghiệp
   vụ*, không phải `agents_selected` hay `job_done`. Vocabulary metadata cũng theo domain:
   `ACTOR_TYPES = {human, agent, tool, system, runtime}`,
   `VISIBILITY_LEVELS = {public, ui_safe, internal, secret, restricted}`.

3. **Epic/Slice nối ngôn ngữ chiến lược với code** — docstring module ghi `Epic E10`
   (Supervisor), `Epic E21` (Control Plane), và các slice `S10.1`, `S10.8`, `S21.4`...
   nối thẳng "implementation" với "requirement". Decision register
   [`docs/decisions.md`](../../../docs/decisions.md) (DEC-2, DEC-8) cột chặt term glossary
   (roster-growth, department, `attribution≠authz`) vào quyết định kiến trúc.

## Các case con

| # | Flagship | Distill cái gì | Folder |
|---|---|---|---|
| 01 | **Glossary canonical registry** | Glossary as code + CI guard chống drift; mô phỏng drift-check & rename impact 5-phase | [`01_glossary_canonical_registry/`](01_glossary_canonical_registry/) |
| 02 | **Domain event naming consistency** | Event đặt tên bằng UL (`delegation.finished`, `loop.team_composed`); đối chứng với tên jargon | [`02_domain_event_naming_consistency/`](02_domain_event_naming_consistency/) |
| 03 | **Epic/Slice ↔ bounded context mapping** | Epic/Slice trong docstring + decisions; ma trận Epic→Slice→Module→Term; phát hiện UL drift khi mapping vỡ | [`03_epic_slice_bounded_context_mapping/`](03_epic_slice_bounded_context_mapping/) |

Mỗi folder có `README.md` (6 mục: bối cảnh → trích code thật → bảng ánh xạ → bản rút gọn
→ cái giá → câu hỏi tự kiểm) và một file `.py` chạy được:

```bash
python3 01_glossary_canonical_registry/glossary_canonical_registry.py
python3 02_domain_event_naming_consistency/domain_event_naming_consistency.py
python3 03_epic_slice_bounded_context_mapping/epic_slice_bounded_context_mapping.py
```

Cả ba in narration tiếng Việt từng bước, có đối chứng "khi KHÔNG dùng pattern", và
`assert` chứng minh bất biến của UL. Chỉ dùng thư viện chuẩn Python 3.14 — không import
`hex_agent`, không bên thứ ba.

## Vét cạn occurrence

Xem [`CATALOG.md`](CATALOG.md) cho bảng MỌI chỗ UL xuất hiện trong codebase (đã mở file
xác minh `path:line`), gồm cả các chỗ không thành flagship riêng (RoleSpec, contracts,
DelegationPolicyEngine, broker, command registry, doctrine doc...).

## Một lưu ý trung thực về số dòng

Glossary trỏ `AgentKernel.execute_tool` tới `core/kernel.py:63`, nhưng tại thời điểm dựng
case này `def execute_tool` thực nằm ở **`core/kernel.py:106`** (đã mở file kiểm chứng).
Tài liệu trong thư mục này dùng số dòng *thật đã xác minh*. Đây cũng chính là một ví dụ
sống của bài học: con trỏ trong glossary có thể *drift* khi code dịch chuyển — lý do
`test_glossary_invariants.py` tồn tại.
