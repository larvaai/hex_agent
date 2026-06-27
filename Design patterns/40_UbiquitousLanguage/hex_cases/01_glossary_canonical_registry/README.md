# Case 01 — Glossary canonical registry (Glossary as code + CI guard)

> Flagship của Ubiquitous Language trong hex_agent: glossary là *first-class artifact*,
> được CI canh, và rename term là migration nhiều phase.

## 1. Bối cảnh trong hex_agent

`hex_agent` là project 40+ kLOC với nhiều term load-bearing dễ bị mỗi người gọi một kiểu:
"chokepoint" hay "gateway"? "roster-growth" hay "push agent"? "authority gate" hay "ACL
check"? Nếu để trôi, new dev hỏi "X là gì?" và nhận 3 câu trả lời khác nhau — đúng triệu
chứng *semantic dementia* mà bài học 40 cảnh báo.

Lời giải của hex_agent: nâng UL thành hạ tầng.

- [`docs/GLOSSARY.md:1-19`](../../../../docs/GLOSSARY.md) là sổ đăng ký thuật ngữ. Mỗi hàng
  là một term load-bearing có **nghĩa** + **con trỏ tới nơi định nghĩa** (`file:line`).
  Header file nói rõ mục đích: *"Mỗi thuật ngữ load-bearing dùng một lần được định nghĩa ở
  đây để plan/code không tự đặt lại tên."*
- [`harness/tests/test_glossary_invariants.py:1-69`](../../../../harness/tests/test_glossary_invariants.py)
  là **CI gate**: glossary không được mất, bảng không được rỗng hoá, core term phải còn
  hàng, ban-wording phải đăng ký. Maintain glossary trở thành *non-optional*.
- [`docs/decisions.md:25-27`](../../../../docs/decisions.md) (DEC-2) và `:103-105` (DEC-8)
  cột term glossary (roster-growth, department, `attribution≠authz`) vào *quyết định kiến
  trúc* — nên rename term kéo theo update ADR.

## 2. Trích đoạn code thật

Glossary as code — `docs/GLOSSARY.md:7,8,15` (mỗi term: nghĩa + backing `file:line`):

```markdown
| Thuật ngữ | Nghĩa |
|---|---|
| chokepoint | Cửa duy nhất mọi LLM+tool call phải đi qua: `AgentKernel.execute_tool`
              ([core/kernel.py:63](../core/kernel.py)). ... |
| roster-growth | Thêm một agent/role vào team của một TaskLoop ĐANG chạy, qua command
              `AddAgentToLoop`, áp tại safe checkpoint. ... |
| authority gate | Kiểm tra trong `run_round` ([supervisor/graph.py:142-147]...): mọi
              assignment phải target agent đã có trong `selected_agents`... |
```

CI guard chống hollowing-out — `harness/tests/test_glossary_invariants.py:58-62`:

```python
def test_core_terms_each_have_a_row(self):
    text = _glossary_text()
    missing = [t for t in _CORE_TERMS if t not in text]
    assert not missing, (
        "GLOSSARY.md lost canonical term(s): %s" % ", ".join(missing))
```

> Lưu ý trung thực: glossary trỏ `core/kernel.py:63`, nhưng `def execute_tool` thật nằm ở
> **`core/kernel.py:106`** (đã mở file kiểm chứng). Đây là một ví dụ *live* của drift con
> trỏ — chính lý do test invariants tồn tại. Trong file `.py` distill, mình dùng số dòng
> thật `:106`.

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò trong Ubiquitous Language | Thành phần hex_agent | Trong file distill |
|---|---|---|
| Glossary (single source of truth) | `docs/GLOSSARY.md` | `class Glossary` + `class Term` |
| Term = nghĩa + nơi định nghĩa | hàng bảng có backing `file:line` | `Term.definition`, `Term.backing` |
| Synonym deprecated (chống drift) | "không tự đặt lại tên" trong header | `Term.synonyms`, `Term.deprecated` |
| CI guard (non-optional) | `test_glossary_invariants.py` | `Glossary.assert_invariants()` |
| Drift detection (bài học §2.2) | grep deprecated/undefined/orphaned | `drift_check()` → `DriftReport` |
| Rename 5-phase (bài học §2.3) | DEC-2 cột term vào ADR | `plan_rename()` + `apply_rename()` |

## 4. Bản rút gọn chạy được

File: [`glossary_canonical_registry.py`](glossary_canonical_registry.py) — chạy:

```bash
python3 glossary_canonical_registry.py
```

Nó **mô phỏng**: dựng lại glossary thật (4 term tiêu biểu), chạy CI guard kiểu
`test_glossary_invariants.py`, dò drift trên hai đoạn code (lẫn lộn vs sạch), và sinh kế
hoạch rename 5-phase rồi áp (term mới kế thừa nghĩa, term cũ thành synonym giữ lịch sử).

Nó **lược bỏ**: file markdown thật + pytest thật + `git grep` thật được thay bằng glossary
in-memory và scan chuỗi tối thiểu bằng `re`. Toàn bộ chỉ dùng thư viện chuẩn — không import
`hex_agent`.

Bất biến được `assert` chứng minh:
- glossary đầy đủ core term + mọi term có nghĩa và backing (CI guard pass);
- drift detector **bắt** code lẫn lộn (`ExecutionGateway` undefined, `push_agent` deprecated)
  và **im lặng** trên code dùng đúng UL;
- sau rename, term mới giữ nguyên nghĩa, term cũ tồn tại làm synonym (không mất lịch sử).

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Chi phí thiết lập + bảo trì**: phải viết glossary + CI gate + cập nhật khi thêm term.
  Với solo dev / prototype < 3 tháng / CRUD app term đơn giản, kỷ luật này là *overhead*.
- **CI gate quá cứng** dễ thành lực cản: nếu mọi class mới đều bắt buộc có hàng glossary,
  tốc độ prototyping giảm. hex_agent cân bằng bằng cách chỉ canh *term load-bearing*, không
  canh mọi định danh.
- **Con trỏ `file:line` tự drift** (như `:63` vs `:106`): glossary trỏ dòng cụ thể sẽ lệch
  khi code dịch chuyển. Đánh đổi giữa "chính xác chỗ định nghĩa" và "phải maintain con trỏ".
- Khi DÙNG: team ≥ 3 dev, domain phức tạp dễ overload term, codebase sống > 1 năm.

## 6. Câu hỏi tự kiểm tra

1. Vì sao `test_glossary_invariants.py` *skip* (không fail) khi `docs/GLOSSARY.md` vắng ở
   site deployer, nhưng *fail* trong source repo? (gợi ý: glossary là source-only doc, test
   ship cùng harness). Điều này dạy gì về phạm vi của một CI guard?
2. Trong bản distill, `drift_check` phân biệt ba loại drift: undefined / deprecated /
   orphaned. Loại nào nguy hiểm nhất với *new dev onboarding*, và vì sao?
3. Tại sao rename theo 5-phase lại giữ term cũ làm *synonym* thay vì xoá hẳn? Liên hệ với
   "downstream consumer" và Published Language trong bài học gốc.
