# Repository / Factory / Specification (DDD) trong hex_agent — Case studies

> Bộ case này distill 3 supporting pattern của DDD (**Repository**, **Factory**, **Specification**)
> trực tiếp từ codebase thật `hex_agent`. Mỗi case là một bản rút gọn **chạy được bằng Python
> chuẩn (3.14)**, giữ đúng vai trò/cấu trúc của code gốc, thay hạ tầng nặng (LLM / SQLite /
> file / network) bằng fake tối thiểu.

Văn phong theo bài học gốc: `../37_RepoFactorySpec.md`.

---

## 1. Ba pattern trong một câu

Aggregate (Lesson 35) cần 3 dịch vụ hỗ trợ — và `hex_agent` hiện thực đủ cả ba:

- **Repository** = abstraction over persistence, *collection-like API* giấu kỹ thuật lưu trữ,
  1 repo cho 1 aggregate, return AR (không expose entity nội bộ).
  Trong hex_agent: `SqliteTaskLoopStore` (SQLite), `InMemoryDelegationStore`, `InMemoryVectorStore`
  — đều ẩn sau **Protocol port** (`DelegationStorePort`, `VectorStorePort`).
- **Factory** = đóng gói việc *tạo* aggregate phức tạp, phân biệt rõ **2 path**: `create()` (aggregate
  mới — enforce invariant, sinh ID, publish event) vs `reconstitute()/restore()` (rebuild từ state
  đã persist — *trust* state, KHÔNG re-validate, KHÔNG emit event).
  Trong hex_agent: `SessionFactory.create_root / create_child / restore` và `Node.from_dict`.
- **Specification** = predicate business rule tái sử dụng (`is_satisfied_by` / `is_satisfied`),
  dùng trong validation, query, và construction guidance.
  Trong hex_agent: `AcceptanceCheck.is_satisfied`, `DoneWhen` (FORBIDDEN_VERDICT_KEYS), các kiểm
  tra referential-integrity/acyclicity trong `load_tree`.

---

## 2. Vì sao chọn 2 flagship này

| # | Case | File gốc | Vì sao đáng học |
|---|------|----------|-----------------|
| 01 | `session_factory` | `core/session.py:104-203` | Factory DDD **2 path** sách giáo khoa: `create_root/create_child` (enforce invariant + freeze deps + publish event) vs `restore` (trust persisted state, không re-check, không emit). Có **business rule ở factory** (scope con phải là subset của cha) — không đẩy xuống AR. |
| 02 | `node_factory_validation` | `decompose_agent/node.py:97-173` | Factory method (`from_dict`) enforce invariant tại lúc dựng qua `__post_init__`. `DoneWhen` áp một **Specification an toàn**: từ chối mọi key dạng verdict (`verdict/passed/status/score/done`) — worker đề xuất, gate mới ghi verdict. Path-jailing (`assert_safe_relpath`) là một predicate kiểu specification áp lúc construct. |

Hai case bù trừ nhau: case 01 cho thấy **Repository (state snapshot/restore) + Factory 2 path**;
case 02 cho thấy **Factory + Specification (validation-as-construction)**. Gộp lại phủ đủ cả ba pattern.

---

## 3. Các case con

- [`01_session_factory/`](01_session_factory/) — `SessionFactory` đa-path: create vs restore, enforcement scope.
- [`02_node_factory_validation/`](02_node_factory_validation/) — `Node`/`DoneWhen` factory với invariant + spec chống forgery.

Mỗi thư mục có:
- `README.md` — bài học (6 mục): bối cảnh thật, trích code thật, bảng ánh xạ vai trò, bản rút gọn,
  cái giá / khi nào không dùng, câu hỏi tự kiểm tra.
- `<name>.py` — code self-contained, chạy `python3 <name>.py` thoát code 0.

---

## 4. Vét cạn occurrence

Xem [`CATALOG.md`](CATALOG.md) — bảng MỌI vị trí Repository/Factory/Specification trong codebase
(path:line, mô tả, độ rõ). Bao gồm cả những impl phụ (DecompCache, StateStore, EventTypeRegistry,
control/commands.py, ...) ngoài 2 flagship.

---

## 5. Cách chạy

```bash
python3 "01_session_factory/session_factory.py"
python3 "02_node_factory_validation/node_factory_validation.py"
```

Cả hai chỉ dùng thư viện chuẩn, không import `hex_agent` hay bên thứ ba.
