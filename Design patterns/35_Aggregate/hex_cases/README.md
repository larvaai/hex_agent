# Aggregate (DDD) trong hex_agent — hex_cases

> Tài liệu dạy học đi kèm Lesson 35 (`../35_Aggregate.md`). Mỗi case là một bản **distill
> trung thực** từ code thật của `hex_agent`, chạy được bằng Python 3.14 chuẩn, không phụ thuộc
> thư viện ngoài. Mục tiêu: nhìn pattern **Aggregate** sống thật trong codebase, không phải ví
> dụ "submission/quiz" giả định.

---

## Pattern này xuất hiện ở đâu trong hex_agent?

Aggregate (DDD) hiện diện trong `hex_agent` chủ yếu ở khâu **quản lý state và vòng đời task**.
Pattern thể hiện qua ba dấu hiệu kinh điển: (1) một *consistency boundary* với state riêng tư,
(2) public API gác **invariant**, và (3) **publish domain event** từ bên trong method.

Ba ổ rõ nhất:

- **`TaskLoopState`** (`supervisor/state.py`) — máy trạng thái của một lượt chạy multi-agent,
  gom cụm acceptance check + agent turn + artifact, gác bất biến "chỉ FINISHED khi tất cả AC đạt".
- **`KernelSession` + `SessionIdentity`** (`core/session.py`) — ngữ cảnh thực thi một task, cô
  lập vòng đời (`_closed`/`is_active`), publish event, factory enforce scope. Danh tính bất biến
  (`frozen=True`) làm value object.
- **`Tree`** (`decompose_agent/tree.py`) — quản lý cụm `Node` bất biến, đảm bảo toàn vẹn tham
  chiếu + bất chu trình; mọi mutation đi qua `Tree.set_status()` (immutable replace).

Các cấu trúc này bảo vệ bất biến (tính hợp lệ của state machine, toàn vẹn tham chiếu, bất chu
trình) thông qua mutation có kiểm soát và phát domain event.

---

## Các case con (flagship)

| # | Case | Nguồn thật | Vai trò AR |
|---|------|-----------|------------|
| 01 | [`01_taskloop_state_aggregate`](./01_taskloop_state_aggregate/) | `supervisor/state.py:80-145` | `TaskLoopState` = Aggregate Root; `AcceptanceCheck`/`AgentTurn` = internal entity; `all_accepted`/`is_terminal` = invariant |
| 02 | [`02_kernel_session_aggregate`](./02_kernel_session_aggregate/) | `core/session.py:15-203` (+ `core/state.py:8-28`) | `KernelSession` = Aggregate Root; `SessionIdentity` = value object; `SessionFactory` = factory; `StateStore` = internal entity |

Mỗi thư mục case có: một `README.md` (6 mục: bối cảnh, trích code thật, bảng ánh xạ, bản rút
gọn, cái giá, câu hỏi tự kiểm tra) và một file `.py` self-contained có `demo()`.

---

## Bản đồ đầy đủ mọi occurrence

Xem [`CATALOG.md`](./CATALOG.md) — bảng vét cạn mọi nơi pattern (hoặc biến thể của nó: invariant
tại construction, value object, projection) xuất hiện trong codebase, kèm `path:line` và độ rõ.

---

## Cách chạy

```bash
python3 01_taskloop_state_aggregate/taskloop_state_aggregate.py
python3 02_kernel_session_aggregate/kernel_session_aggregate.py
```

Cả hai thoát code 0, in narration từng bước (tiếng Việt) kèm `assert` chứng minh bất biến, và
mỗi case có ít nhất một **đối chứng** cho thấy "khi KHÔNG dùng pattern thì hỏng thế nào".

---

## Ghi chú đọc hiểu

- **Khác biệt có chủ đích với code thật:** code thật của hex_agent ưu tiên *serialize được*
  (checkpoint SQLite/S3) nên nhiều aggregate dùng `@dataclass` field public. Bản distill case 01
  cố ý **siết encapsulation chặt hơn** (private field + command method) để dạy thuần nguyên lý
  "invariant inside AR". Mỗi README ghi rõ chỗ nào là code thật, chỗ nào là distill siết thêm.
- **Value object vs aggregate:** rất nhiều cấu trúc trong `control/` và `decompose_agent/` là
  *immutable value object* với validation tại `__post_init__` (xem CATALOG). Chúng dùng chung
  *nguyên lý* "invalid state should be impossible" của Lesson 35 nhưng **không phải** aggregate
  root (vì bất biến ⇒ không có lifecycle mutation). Đừng nhầm hai loại.
