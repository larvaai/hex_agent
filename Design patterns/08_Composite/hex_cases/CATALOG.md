# CATALOG — mọi occurrence của Composite trong hex_agent

Bảng vét cạn các chỗ pattern **Composite** (hoặc cấu trúc cây part-whole xử lý đệ quy đồng nhất) xuất hiện trong codebase thật. Mọi `path:line` đã được mở và xác minh. Path tương đối so với root `/Users/uspro/Desktop/namnson/hex_agent`.

| path:line | Mô tả | Độ rõ |
|-----------|-------|-------|
| `decompose_agent/tree.py:28-29` | `children_of(node_id)` trả về tuple id các con — **interface đồng nhất** để truy vấn con ở bất kỳ cấp nào của cây. | cao |
| `decompose_agent/tree.py:34-41` | `rebuild_children()` dựng lại index cha→con từ con trỏ `parent` sau khi decompose runtime gắn con mới. Quản lý quan hệ cha-con tường minh. | cao |
| `decompose_agent/tree.py:43-51` | `next_node()` — con trỏ DFS: chọn node `pending` trái nhất theo `(depth, order)` mà mọi `depends_on` đã `done`. Client duyệt cây mà không phân biệt leaf/composite. | cao |
| `decompose_agent/tree.py:62-76` | `_depth_of()` đi ngược chuỗi `parent` về gốc, phát hiện chu trình cha. Bất biến bảo vệ cấu trúc cây (không cho cây thành đồ thị vòng). | trung bình |
| `decompose_agent/node.py:97-153` | `Node` (frozen dataclass) là **Component**: có `parent`, `depends_on`, `done_when`. Mỗi node thay thế được cho nhau trong cây; client không phân biệt leaf vs composite. | cao |
| `decompose_agent/solve.py:126-179` | `_decompose()` gắn con vào cây khi một work node cần tách. Dòng 176 gọi `cache.commit()` thêm node con mới — cây **lớn lên động** lúc chạy. | cao |
| `decompose_agent/solve.py:223-247` | `_close_done_parents()` duyệt các node `decomposed`, nếu mọi con đã `done` thì đóng cha, **lan ngược bottom-up** đệ quy. Đây là closure thuần của Composite. | cao |
| `decompose_agent/solve.py:262-293` | Vòng lặp driver `solve()`: `while tree.next_node()` xử lý từng node đồng nhất — leaf thì `solve_leaf()`, composite thì `_decompose()`, rồi đóng cha. | cao |
| `decompose_agent/store.py:1-9, 35-37` | Two-phase commit: `commit` gắn cạnh con AND lật cha thành `decomposed` trong một `os.replace`. Bảo toàn cấu trúc Composite khi persist. | trung bình |
| `decompose_agent/tests/test_solve_recurse.py:24-34` | `test_happy_decompose_then_children_done_then_parent_done`: vòng đời Composite đầy đủ — cha decompose, con sinh & giải, cha đóng khi mọi con done. | cao |
| `decompose_agent/tests/test_tree.py:9-30` | Test con trỏ `next_node` và index con dẫn xuất từ con trỏ `parent`; phần sau test phát hiện chu trình. Bất biến bảo vệ cấu trúc Composite. | trung bình |
| `drag_from_zero/dragzero/read_model.py:16-27` | `TaskNode` dataclass với `id, description, parent_id, status, children`. **Không phân biệt loại** — mọi node cùng schema (Component). | cao |
| `drag_from_zero/dragzero/read_model.py:36-46` | `reduce()` fold event log thành cây: `ROOT_TASK_CREATED` tạo gốc, `SUBTASK_SPAWNED` gắn con vào `parent.children`. Dựng cấu trúc cây từ event. | cao |
| `drag_from_zero/dragzero/live_view.py:27-50` | `render_tree(root)` đi DFS bằng `walk()` lồng (dòng 32-47): in status rồi đệ quy `walk(child)` cho mọi con. **Không type-check**, duck typing trên `node.children`. | cao |
| `drag_from_zero/tests/test_slice2_adapter.py:9-18` | Test dùng `reduce` + `render_tree` qua port adapter; truy cập cây `TaskNode` sau khi fold event. Kiểm chứng cấu trúc cây. | trung bình |
| `drag_from_zero/tests/unit/test_live_view.py:17-25` | Unit test `render_tree` với cây `TaskNode` dựng tay; chứng minh render chạy đồng nhất ở mọi độ sâu lồng. | trung bình |
| `ui/server.py:105-140` | `_tree_node(path, root, scope, counter)` dựng cây file-system đệ quy: thư mục thì gom con đệ quy (dòng 126-137). Composite cho cây file. | trung bình |
| `ui/ide/files.py:127-162` | `_tree_node()` tương tự — duyệt thư mục đệ quy. Composite áp cho cấu trúc file system. | trung bình |

## Hai flagship (case con)

- **01** `decompose_agent_task_tree` — distill từ `tree.py:28-51`, `node.py:97-153`, `solve.py:223-293`.
- **02** `drag_from_zero_task_render` — distill từ `read_model.py:16-46`, `live_view.py:27-50`.
