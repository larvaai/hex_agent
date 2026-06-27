# Case 01 — Task Decomposition Navigator: máy trạng thái của Node

> Cùng một "bộ não" Navigator, hành vi xử lý một node **đổi theo `status`** của node đó:
> `pending` thì chờ tới lượt, `active` thì đang chạy, `done` thì có thể đóng cha,
> `blocked` thì lan lỗi lên. Một node `status` lạ **không thể tồn tại** — đúng như não
> không nhảy thẳng Wake → REM.

---

## 1. Bối cảnh trong hex_agent

`decompose_agent/` là bộ giải bài toán bằng cách **đệ quy chia nhỏ**: một task lớn
(`Node`) nếu giải trực tiếp thất bại thì được tách thành các task con, các con giải xong
thì cha tự đóng. Vòng đời của một node đi qua đúng 5 trạng thái — và toàn bộ logic
"đi tiếp ra sao" phụ thuộc vào trạng thái hiện tại, **không** rải `if/elif` khắp nơi.

Vấn đề thật mà pattern giải:
- Một node phải hành xử khác nhau tuỳ trạng thái (chưa tới lượt / đang chạy / đã chia /
  xong / kẹt). Nếu để `status` là chuỗi tự do, mỗi nơi lại tự so sánh chuỗi → gõ sai
  `"complete"` thay `"done"` là cursor bỏ sót node, treo cả cây mà không báo lỗi.
- Cần một **tập trạng thái hữu hạn** được canh gác ngay tại lúc tạo object.

File và dòng đã mở kiểm chứng:
- `decompose_agent/node.py:28` — `VALID_STATUSES` (tập 5 state).
- `decompose_agent/node.py:102-140` — `Node` là `frozen dataclass`; guard `status` ở `__post_init__` (dòng 127-128).
- `decompose_agent/tree.py:31-32` — `Tree.set_status()` đóng gói transition (replace node).
- `decompose_agent/tree.py:43-51` — `Tree.next_node()` cursor chọn node `pending` có mọi dependency `done`.
- `decompose_agent/solve.py:80-121` — `solve_leaf()`: `pending → active → done/blocked/needs_decompose`.
- `decompose_agent/solve.py:229-253` — `_close_done_parents()`: `decomposed → done` (dòng 245).
- `decompose_agent/solve.py:258-304` — `solve()`: vòng lặp Navigator; `outcome.status` quyết nhánh tiếp theo.

---

## 2. Trích đoạn code thật

Tập trạng thái hữu hạn + guard tại construction (`decompose_agent/node.py:28, 127-128`):

```python
VALID_STATUSES = frozenset({"pending", "active", "decomposed", "done", "blocked"})

# ... trong Node.__post_init__:
if self.status not in VALID_STATUSES:
    raise ValueError(f"Node.status must be one of {sorted(VALID_STATUSES)}, got {self.status!r}")
```

Transition được đóng gói + cursor đọc state (`decompose_agent/tree.py:31-32, 43-51`):

```python
def set_status(self, node_id: str, status: str) -> None:
    self.nodes[node_id] = replace(self.nodes[node_id], status=status)

def next_node(self) -> Node | None:
    ready = [
        n for n in self.nodes.values()
        if n.status == "pending"
        and all(self.nodes[dep].status == "done" for dep in n.depends_on)
    ]
    if not ready:
        return None
    return min(ready, key=lambda n: (n.depth, n.order))
```

Behavior đổi theo state kết quả trong driver (`decompose_agent/solve.py:282-298`):

```python
if outcome.status == "done":
    cf = _close_done_parents(tree, workspace_root, root, journal)
    ...
    continue
if outcome.status == "needs_decompose":
    d = _decompose(tree, nid, worker, ...)
    ...
    continue
# leaf blocked (UNSOLVABLE_LEAF / BUDGET / PARSE_BUDGET)
_propagate_block(tree, nid, journal)
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò State pattern | Thành phần trong hex_agent | Ghi chú |
|---|---|---|
| **Context** | `Tree` (`tree.py`) + mỗi `Node` (`node.py`) | Tree giữ tập node, delegate việc chọn node kế qua `next_node()`; mỗi Node là context của một task, mang `status`. |
| **State (interface)** | field `Node.status` thuộc `VALID_STATUSES` | "Interface" ở đây là ngầm: behavior hợp lệ được định nghĩa theo giá trị status. |
| **ConcreteState** | 5 giá trị: `pending`, `active`, `decomposed`, `done`, `blocked` | Mỗi state cho phép một tập hành vi/transition khác. |
| **Transition (đóng gói)** | `Tree.set_status()` (`tree.py:31-32`) | Mọi transition đi qua đây → một chỗ để audit. |
| **Transition state-driven** | `solve_leaf`/`solve_reduce` set status theo kết quả gate | `pending→active→done/blocked`. |
| **Transition context-driven** | `_close_done_parents` đọc status các con → đóng cha | `decomposed→done`. |
| **Guard** | `frozen` + `__post_init__` + `next_node` chỉ chạy khi deps `done` | Không cho state lạ tồn tại; không "leo sớm". |

---

## 4. Bản rút gọn chạy được

File: [`task_decomposition_navigator.py`](./task_decomposition_navigator.py)

Mô phỏng đúng:
- `Node` frozen + `VALID_STATUSES` + guard ở `__post_init__`.
- `Tree.set_status()` (replace) và `Tree.next_node()` (cursor đọc status).
- `solve_leaf` / `solve_reduce` / `_decompose` / `_close_done_parents` / `_propagate_block`
  và driver `solve()` với nhánh theo `outcome.status`.
- Hai kịch bản: happy-path (`decomposed→done` cascade) và block (`blocked` lan lên cha).
- Một đối chứng: `naive_advance` gán chuỗi tự do để thấy vì sao thiếu tập state hữu hạn là nguy hiểm.

Lược bỏ (thay bằng fake stdlib):
- **Worker LLM 35B** → `MockWorker` với kịch bản cố định (`done`/`decompose`/`block`).
- **Gate đọc artifact trên đĩa** (`decompose_agent/gates.py`) → quyết định pass/fail bằng kịch bản worker, không chạm filesystem.
- Bỏ `Journal`, `budget`, `cache`, `reduce_op` thật — chỉ giữ phần thể hiện máy trạng thái.

Chạy:
```bash
python3 task_decomposition_navigator.py
```

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- Nếu `status` chỉ là **dữ liệu báo cáo** (in ra cho người dùng) chứ không **lái hành vi**,
  thì dùng enum/chuỗi đơn giản là đủ — không cần dựng máy trạng thái (xem các mục `clarity: low`
  trong CATALOG: `graph/state.py`, `ui/server.py`).
- Tập state quá ít (2-3) và mỗi state hành xử gần giống → một cờ boolean rẻ hơn.
- `frozen + replace` đánh đổi: mỗi transition tạo object mới (chi phí cấp phát). Với cây
  rất lớn cần cân nhắc; ở đây nó mua được **bất biến** (không ai mutate status lén).
- Khi số chiều trạng thái orthogonal tăng (status × kind × depth-budget...) dễ nổ state —
  hex_agent tránh bằng cách tách `kind` (work/reduce) ra khỏi `status`, không nhân chéo.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `Node` được khai báo `frozen` thay vì cho sửa `node.status = "done"` trực tiếp?
   Bất biến nào của State pattern được bảo vệ nhờ điều đó?
2. `next_node()` chỉ là một biểu thức lọc trên `status` + `depends_on`. Nếu thay bằng
   `if/elif` liệt kê từng state thì khi thêm state mới (vd `paused`) ta phải sửa ở những đâu?
3. Trong kịch bản block, vì sao `root` chuyển `decomposed → blocked` chứ không `→ done`?
   Hàm nào thực hiện và nó đọc trạng thái của ai để quyết?
