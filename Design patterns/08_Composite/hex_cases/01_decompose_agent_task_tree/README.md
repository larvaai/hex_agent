# Case 01 — Composite: Cây task của `decompose_agent`

> Decompose Agent Task Tree — cha-con đệ quy, decompose động, lan completion ngược lên.

## 1. Bối cảnh trong hex_agent — vấn đề thật

`decompose_agent` là bộ giải bài toán theo kiểu **chia để trị**: một task lớn được tách (decompose) thành các task con cho tới khi đủ nhỏ để giải trực tiếp. Cấu trúc dữ liệu trung tâm là một **cây task** — và đây là một Composite thật:

- **`Node`** (`decompose_agent/node.py:97-153`) là một đơn vị công việc, frozen dataclass, có `parent`, `depends_on`, `done_when`, `status`. Một node **không tự biết** mình là leaf hay composite — điều đó do cấu trúc cây quyết định. Một node có `done_when` gồm nhiều tiêu chí (dwc>1) thường sẽ phải tách; node nguyên tử (dwc==1) là leaf.

- **`Tree`** (`decompose_agent/tree.py:21-51`) giữ `nodes: dict[str, Node]` và `_children: dict[str, tuple]` (index cha→con). `children_of(node_id)` (dòng 28-29) là **interface đồng nhất** để hỏi con của bất kỳ node nào. `next_node()` (dòng 43-51) là con trỏ DFS chọn node `pending` trái nhất theo `(depth, order)`.

- **`solve()`** (`decompose_agent/solve.py:262-293`) là client: vòng lặp `while tree.next_node()` xử lý từng node **đồng nhất** — không có `isinstance`. Khi một node leaf không giải được nó được tách (`_decompose`, dòng 126-179) và con mới gắn vào cây; cây **lớn lên lúc runtime**. Khi một node xong, `_close_done_parents()` (dòng 223-247) **lan completion ngược lên** cha theo đệ quy bottom-up.

Vấn đề mà Composite giải ở đây: bộ giải phải xử lý **độ sâu tùy ý** (tách bao nhiêu cấp tùy bài toán) mà **không** rải `if isinstance(...)` theo từng cấp, và phải đóng node cha một cách **đúng đắn** khi mọi con (kể cả cháu) đã xong.

## 2. Trích đoạn code thật

Interface đồng nhất + con trỏ + dựng lại index cha-con (`decompose_agent/tree.py:28-51`):

```python
def children_of(self, node_id: str) -> tuple[str, ...]:
    return self._children.get(node_id, ())

def rebuild_children(self) -> None:
    """Recompute the parent→children index from current parent pointers (after runtime
    decomposition attaches new child nodes)."""
    children: dict[str, list[str]] = {nid: [] for nid in self.nodes}
    for node in self.nodes.values():
        if node.parent is not None and node.parent in children:
            children[node.parent].append(node.id)
    self._children = {k: tuple(v) for k, v in children.items()}

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

Closure lan completion ngược lên cha (`decompose_agent/solve.py:223-241`):

```python
def _close_done_parents(tree, workspace_root, root: str, journal: Journal) -> Outcome | None:
    changed = True
    while changed:
        changed = False
        for nid, node in list(tree.nodes.items()):
            if node.status != "decomposed":
                continue
            statuses = [tree.nodes[c].status for c in tree.children_of(nid)]
            ...
            acd_ok = len(statuses) >= 1 and all(s == "done" for s in statuses)  # F1: 0 children → False
            gate = run_checks(node, node_dir(workspace_root, root, nid), child_statuses=statuses)
            if acd_ok and gate.ok:
                tree.set_status(nid, "done")
                ...
                changed = True
```

## 3. Bảng ánh xạ vai trò pattern ↔ code thật

| Vai trò Composite | Thành phần code thật |
|-------------------|----------------------|
| **Component** (interface chung) | `Node` (`node.py:97-153`) — mọi node cùng kiểu, có `parent`/`status`/`done_when`; thay thế được cho nhau trong cây |
| **Leaf** | `Node` nguyên tử (có `done_when`, giải trực tiếp bằng `solve_leaf`, `solve.py:80-121`) |
| **Composite** | `Node` đã `decomposed`, có con — con index qua `_children`, con trỏ ngược qua `parent` |
| **Phép truy vấn con đồng nhất** | `Tree.children_of()` (`tree.py:28-29`) |
| **Đệ quy đóng gói (aggregation đi lên)** | `_close_done_parents()` (`solve.py:223-247`) — đóng cha khi mọi con done, lặp tới hội tụ |
| **Client** | `solve()` (`solve.py:262-293`) — vòng lặp `next_node()` xử lý leaf/composite như nhau |
| **Cây lớn lên động** | `_decompose()` + `cache.commit()` (`solve.py:126-179`) + `rebuild_children()` (`tree.py:34-41`) |

## 4. Bản rút gọn chạy được

File: [`decompose_agent_task_tree.py`](./decompose_agent_task_tree.py) — chạy `python3 decompose_agent_task_tree.py`.

**Mô phỏng gì:**
- `Node` (frozen), `Tree` với `children_of` / `rebuild_children` / `next_node` — giữ **nguyên** chữ ký và logic con trỏ `(depth, order)`.
- `solve()` driver, `_decompose()` gắn con (cây lớn lên động), `_close_done_parents()` lan completion ngược lên — giữ **nguyên** vòng đời Composite.
- Demo: gốc `root` (dwc=2) tách 2 cấp thành 4 leaf, các leaf giải xong, closure đóng `root.1`, `root.2`, rồi `root`.

**Lược bỏ gì:** LLM Worker thay bằng `ScriptedWorker` (giải được leaf khi `depth >= ngưỡng`, mô phỏng ràng buộc "bài toán phải nhỏ đi"); gate chấm artifact, YAML loader, store two-phase commit, journal, budget — đều bỏ. Trọng tâm giữ lại đúng **interface đồng nhất + đệ quy đóng gói**.

**Đối chứng (KHÔNG dùng Composite):** `naive_all_done_BAD()` kiểm tra "cả cây xong" chỉ bằng cách nhìn **con trực tiếp** — trả `True` cho node `A` dù cháu `A.1.y` còn `pending`. Bản Composite `composite_all_done_GOOD()` đệ quy đồng nhất nên trả đúng `False`. Đây chính là lỗi "quên đệ quy xuống cấp dưới" mà bài học gốc cảnh báo.

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Đồng bộ hai chiều liên kết tốn công.** Cây giữ cả `parent` (con→cha) lẫn `_children` (cha→con); mỗi lần cây đổi phải gọi `rebuild_children()` để không lệch. Nếu cấu trúc chỉ cần một chiều, đây là phức tạp thừa.
- **Closure đệ quy có giá O(n) mỗi lần đóng.** `_close_done_parents` lặp `while changed` toàn bộ node tới khi hội tụ; với cây rất lớn cần lập chỉ mục thông minh hơn.
- **Nếu cấu trúc phẳng hoặc độ sâu cố định 1-2 cấp**, một list đơn giản + 1 phép `all(...)` dễ đọc hơn; Composite chỉ thắng khi **độ sâu tùy ý** và cần áp **nhiều operation** đồng nhất lên cây.
- **Bất biến phải được bảo vệ.** Cây Composite mà thành đồ thị có chu trình (parent cycle) sẽ làm đệ quy treo — bản thật chặn điều này tại `_depth_of` (`tree.py:62-76`). Composite không miễn phí về tính đúng đắn cấu trúc.

## 6. Câu hỏi tự kiểm tra

1. Vì sao `next_node()` chọn theo `(depth, order)` chứ không phải thứ tự khai báo? Điều này liên quan gì tới việc cây **lớn lên lúc runtime** (con mới có `depth` lớn hơn)?
2. `_close_done_parents()` dùng vòng `while changed`. Nếu thay bằng một lượt quét duy nhất (không lặp) thì cây 3 cấp có đóng được tới gốc không? Giải thích bằng thứ tự các node được đóng.
3. Trong bản thật, một node `Node` không có method `add_child` — việc gắn con đi qua con trỏ `parent` rồi `rebuild_children()`. Đây là biến thể "Transparent" hay "Safe" của Composite (xem bài học gốc), và đánh đổi gì?
