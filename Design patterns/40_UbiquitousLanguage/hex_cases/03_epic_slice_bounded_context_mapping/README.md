# Case 03 — Epic/Slice ↔ Bounded Context mapping (UL ở tầng chiến lược)

> Flagship của Ubiquitous Language: UL không dừng ở term lẻ. Epic/Slice trong docstring +
> decision register cột term vào quyết định ⇒ architect và dev chia sẻ MỘT mental model.

## 1. Bối cảnh trong hex_agent

UL thường được dạy ở cấp term ("Submission" vs "Attempt"). hex_agent đẩy nó lên cấp *khái
niệm chiến lược*: mỗi module ghi rõ thuộc Epic nào và hiện thực Slice nào của spec, để
"requirement nói X" và "implementation gọi Y" không trôi khỏi nhau.

- [`supervisor/graph.py:1-8`](../../../../supervisor/graph.py): docstring mở đầu
  *"Supervisor nodes — compose_team / o_decide / run_round / judge / tool. Epic E10."* — tên
  node = tên phase nghiệp vụ; các comment section ghi slice: `compose_team (S10.1)` (dòng 86),
  `o_decide (S10.8)` (dòng 107), `run_round (S10.2/S10.3/S10.5/S10.14)` (dòng 136).
- [`supervisor/contracts.py:1-8`](../../../../supervisor/contracts.py): *"Supervisor data
  contracts ... Epic E10."* — `SessionPlan`, `OrchestratorDecision`, `ContextPacket` khớp
  slice spec.
- [`control/events.py:1`](../../../../control/events.py): *"RuntimeEvent envelope ... Epic
  E21 (S21.1/S21.7-info)."* — E21 nghĩa là "realtime audit + event streaming", không phải
  "LogEntry".
- [`delegation/manager.py:1`](../../../../delegation/manager.py): *"Sequential delegation
  chokepoint..."* — dùng term load-bearing "chokepoint" của glossary ngay trong docstring.
- [`docs/decisions.md:25-27`](../../../../docs/decisions.md) (DEC-2) cột term `roster-growth`,
  `department`, `authority gate` (trỏ `supervisor/graph.py:142-147`) vào quyết định E21; và
  `:103-105` (DEC-8) cột `attribution≠authz`. Rename term ⇒ ADR phải update theo.

## 2. Trích đoạn code thật

Docstring nối code với Epic + node = phase — `supervisor/graph.py:1, 86, 107, 136`:

```python
"""Supervisor nodes — compose_team / o_decide / run_round / judge / tool. Epic E10.
...
"""
# ── compose_team (S10.1) ─────────────────────────────────────────────────────
# ── o_decide (S10.8) ─────────────────────────────────────────────────────────
# ── run_round (S10.2/S10.3/S10.5/S10.14) ─────────────────────────────────────
```

Decision cột term glossary vào quyết định kiến trúc — `docs/decisions.md:25` (DEC-2, rút gọn):

```text
## DEC-2 — ... O là delegator duy nhất; department = alias gom role chạy tuần tự ...
roster-growth + department đều đi qua RuntimeCommand AddAgentToLoop + pending_commands,
apply tại safe checkpoint cuối round ...
... authority gate vẫn là nguồn chân lý sau expansion (supervisor/graph.py:142-147).
```

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò trong Ubiquitous Language | Thành phần hex_agent | Trong file distill |
|---|---|---|
| Epic = feature chiến lược, gọi tên trong code | docstring `Epic E10`, `Epic E21` | `MODULES` fixture + `_EPIC_RE` |
| Slice = mục spec cross-ref trong docstring | `(S10.1)`, `(S21.4)` ... | `_SLICE_RE`, `ModuleRef.slices` |
| Module aligned tới biên Epic | `supervisor/`, `control/`, `delegation/` | key của `MODULES` |
| Domain term xuất hiện trong code | "chokepoint", "authority gate" ... | `GLOSSARY_TERMS`, `ModuleRef.terms` |
| ADR cột term vào quyết định | DEC-2, DEC-8 | `DECISIONS` |
| Traceability matrix | Epic → Slice → Module → Term | `build_matrix()` |
| Phát hiện UL drift chiến lược | rename term không update DEC ⇒ stale | `check_decisions()` → `StaleDecision` |

## 4. Bản rút gọn chạy được

File: [`epic_slice_bounded_context_mapping.py`](epic_slice_bounded_context_mapping.py) — chạy:

```bash
python3 epic_slice_bounded_context_mapping.py
```

Nó **mô phỏng**: parse docstring/comment của vài module (fixture giữ nguyên dấu vết
Epic/Slice/Term thật) → rút Epic + Slice + Term; dựng ma trận `Epic → Slice → Module →
Term`; rồi kiểm DEC-2/DEC-8 còn khớp code không. Đối chứng: dev rename `roster-growth` →
`team_expansion` trong code mà quên update DEC-2 ⇒ ADR thành *stale* (nói dối).

Nó **lược bỏ**: việc đọc file thật + `git grep` + parse Markdown decision register. Fixture
in-memory thay cho file, regex tối thiểu thay cho parser AST. Chỉ dùng thư viện chuẩn.

Bất biến được `assert` chứng minh:
- Epic E10 gom đúng `supervisor/graph.py` + có slice `S10.1` (compose_team);
- Epic E21 gom `control/events.py`;
- `authority gate` xuất hiện trong `supervisor/graph.py`;
- mọi ADR *tươi* khi code khớp; và **stale** khi term bị rename mà DEC không update.

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Epic/Slice trong docstring là một cam kết bảo trì**: spec đổi số slice (S10.5 → S10.7)
  thì docstring phải đổi theo, nếu không cross-ref thành sai. Với project không có spec phân
  slice, gắn Epic/Slice vào code chỉ là *noise*.
- **Decision register cột term ⇒ rename đắt hơn**: đổi một term load-bearing kéo theo update
  ADR + glossary + mọi docstring nhắc tới — đó là chủ ý (rename không nên rẻ), nhưng với
  prototype thì là lực cản.
- **Mapping tự drift im lặng**: nếu không có cơ chế như `check_decisions`, ADR và code lệch
  nhau mà không ai biết. Lợi ích chỉ có khi drift-check được chạy đều (CI/review).
- Khi nhẹ: solo dev, không có tầng "epic/slice", domain phẳng — đừng dựng bộ máy này.

## 6. Câu hỏi tự kiểm tra

1. Vì sao đặt `Epic E10` trong docstring `supervisor/graph.py` lại giúp một *architect* (nói
   "E10 composes teams") và một *dev* (đọc `compose_team`) chia sẻ cùng mental model? Điều gì
   vỡ nếu docstring bỏ Epic/Slice?
2. Trong đối chứng, DEC-2 thành stale khi `roster-growth` bị rename trong code. Ai là người
   "bị hại" đầu tiên bởi một ADR nói dối, và vì sao? (gợi ý: new dev đọc DEC-2 để hiểu quyết
   định).
3. `delegation/manager.py` có term `chokepoint` nhưng *không* ghi Epic trong docstring (epic=
   `-`). Theo bạn, đây là thiếu sót cần sửa hay chấp nhận được? Lập luận theo chi phí/lợi ích
   ở mục 5.
