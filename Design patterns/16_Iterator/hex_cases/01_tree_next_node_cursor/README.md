# Case 01 — Tree Cursor Iterator: `next_node()` cho DAG traversal

> Iterator tường minh, rõ nét nhất trong hex_agent. Đây là "saccade controller" của decompose agent: nó quyết định "node tiếp theo ở đâu" thay cho `solve()`, đúng như SC quyết định fixation thay cho võng mạc.

---

## 1. Bối cảnh trong hex_agent

Decompose agent giải một task bằng cách "decompose-until-trivial": cây task là một **DAG** — mỗi node có `parent` (cây phân rã) và `depends_on` (ràng buộc thứ tự: node B không được làm trước khi A `done`). Vấn đề: `solve()` cần duyệt cây này theo đúng **topo-order** (không "climb early"), nhưng nếu chính `solve()` phải tự sort topo + theo dõi status thì:

- nó phải biết cấu trúc bên trong của tree (rò rỉ encapsulation),
- và logic topo-sort sẽ bị nhân bản ở mọi chỗ cần duyệt.

Giải pháp: dồn toàn bộ logic "node nào kế tiếp" vào **một cursor** — `Tree.next_node()`. `solve()` chỉ kéo cursor đến khi `None`.

File thật:
- `decompose_agent/tree.py:43-51` — `Tree.next_node()` (cursor).
- `decompose_agent/solve.py:262-295` — vòng `solve()` (client).

Docstring đầu `tree.py` nói thẳng:
> "`next_node` is the cursor: the leftmost `pending` node whose dependencies are all `done`, by `(depth, order)`. The topo order over `depends_on` IS the 'don't climb early' rule, free." (`tree.py:5-8`)

---

## 2. Trích đoạn code thật

Cursor — `decompose_agent/tree.py:43-51`:

```python
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

Client — `decompose_agent/solve.py:262-295` (lược):

```python
while (node := tree.next_node()) is not None:
    nid = node.id
    ...
    if outcome.status == "done":
        cf = _close_done_parents(tree, workspace_root, root, journal)
        ...
        continue
    if outcome.status == "needs_decompose":
        d = _decompose(tree, nid, ...)
        ...
        continue  # children are pending now — the cursor picks them up
```

Chú ý câu comment ở dòng 295: *"children are pending now — the cursor picks them up"*. `solve()` chỉ đẻ con rồi `continue`; nó **tin** cursor sẽ tự nhặt con lên ở vòng sau. Đó là biểu hiện đẹp nhất của "client không biết cách duyệt".

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Iterator | Trong hex_agent | Trong bản distill (`tree_next_node_cursor.py`) |
|------------------|-----------------|------------------------------------------------|
| **Aggregate** (Iterable) | `Tree` sở hữu `nodes: dict[str, Node]` | `class Tree` với `nodes` |
| **Iterator / cursor** | `Tree.next_node()` — state cursor nằm trong _status_ của node, không có index riêng | `Tree.next_node()` y hệt |
| **Item** | `Node` (frozen dataclass) | `Node` (frozen dataclass) |
| **Cursor advance** | `tree.set_status(nid, "done")` làm tập `ready` đổi | `tree.set_status(...)` |
| **Client** | vòng `while (node := tree.next_node())` trong `solve()` | hàm `solve(tree)` |
| **Thứ tự duyệt (Strategy ẩn)** | `min(ready, key=(depth, order))` + ràng buộc `depends_on` | giữ nguyên |

Điểm tinh tế: **không có biến `cursor` kiểu int**. "State cursor" của iterator này chính là tập hợp `status` của các node — mỗi lần một node thành `done`, tập `ready` đổi, và `next_node()` tự trả ra node kế tiếp. Đây là external iterator có logic riêng, đúng mục 2.5 ("ConcreteIterator chứa state cursor") của bài gốc.

---

## 4. Bản rút gọn chạy được

File: [`tree_next_node_cursor.py`](tree_next_node_cursor.py)

**Mô phỏng:** dựng tay một cây `root` + 3 con (`c0`, `c1`, `c2`), trong đó `c1` `depends_on` `c0`. Cố tình chèn `c1` **trước** `c0` trong dict để chứng minh cursor không đi theo thứ tự chèn. Sau đó chạy `solve()` chỉ-gọi-`next_node()`, in thứ tự duyệt, và kiểm tra các bất biến.

**Đối chứng (`naive_iterate_wrong`):** nếu client tự duyệt `dict.values()` theo thứ tự chèn, `c1` bị duyệt **trước** `c0` mà nó phụ thuộc — "climb early". `assert` chứng minh đúng lỗi này. Đây là cái giá của việc không có cursor che giấu logic topo.

**Lược bỏ so với bản thật:** load YAML + validate referential integrity/acyclicity (`load_tree`), LLM worker (`worker.propose`/`decompose`), journal, cache, budget, reduce node. Thay worker bằng `fake_solve()` chỉ in ra. Trọng tâm là **traversal**, nên mọi thứ không liên quan đến cursor đều bị bỏ.

**Bất biến được `assert`:**
1. Mọi node được duyệt đúng 1 lần.
2. `c0` (dependency) luôn được giải **trước** `c1` (không climb early).
3. `root` (depth nhỏ nhất) được trả đầu tiên.
4. Sau khi cạn, `next_node()` trả `None`.
5. Hai cursor trên hai tree độc lập không ảnh hưởng nhau (bất biến 2 của mục 2.4 bài gốc).

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **`next_node()` là O(N) mỗi lần gọi** (quét toàn bộ `nodes`). Với cây nhỏ (đặc trưng của decompose) thì ổn, nhưng với hàng triệu node thì cursor kiểu "quét lại từ đầu" sẽ chậm — khi đó nên giữ một priority queue/heap như ví dụ 1 của bài gốc.
- **Cursor đọc state từ chính Aggregate** (status của node). Nếu có nhiều luồng cùng đổi status, cursor có thể trả kết quả không xác định → cần khoá hoặc snapshot (bài gốc, mục 2.4 bất biến 3). Bản thật chạy "one process, one cursor" nên không cần.
- **Nếu chỉ cần duyệt một list phẳng đúng một lần**, đây là overhead — `for x in list` là đủ (cảnh báo mục 1.5 bài gốc: "Iterator không phải for-loop với extra steps"). Iterator này đáng giá **chỉ vì** logic duyệt là topo-order phức tạp.

---

## 6. Câu hỏi tự kiểm tra

1. "State cursor" của `next_node()` được lưu ở đâu? (Gợi ý: không phải một biến `int` — nó nằm trong cái gì của Aggregate?) Điều đó khiến hai cursor song song trên _cùng một_ tree khác gì so với trên hai tree khác nhau?
2. Comment `solve.py:295` viết "children are pending now — the cursor picks them up". Nếu `_decompose()` đẻ con nhưng quên set chúng về `pending`, cursor sẽ làm gì? Bất biến nào trong bản distill bắt được lỗi này?
3. Vì sao chèn `c1` trước `c0` trong dict mà cursor vẫn trả `c0` trước? Nếu ta xoá điều kiện `all(... depends_on ... == "done")` khỏi `next_node()`, đối chứng `naive_iterate_wrong` và bản đúng có còn khác nhau không?
