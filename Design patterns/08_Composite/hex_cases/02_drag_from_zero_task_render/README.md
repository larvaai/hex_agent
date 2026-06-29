# Case 02 — Composite: Cây render `TaskNode` của `drag_from_zero`

> Drag-from-Zero TaskNode Tree — render cây phân cấp đệ quy từ event log, không type-check.

## 1. Bối cảnh trong hex_agent — vấn đề thật

`drag_from_zero` là một orchestrator nhiều agent dùng kiến trúc **event-sourcing**: trạng thái không lưu trực tiếp mà được "fold" lại từ một event log. Để hiển thị tiến độ, hệ thống chiếu (project) event log thành một **cây task** rồi render ra text. Đây là Composite ở ngữ cảnh **read-model / rendering**:

- **`TaskNode`** (`drag_from_zero/dragzero/read_model.py:16-27`) là một dataclass duy nhất cho **mọi** node: `id`, `description`, `parent_id`, `status`, và `children: list`. **Không có** phân biệt loại — một node có `children` rỗng là leaf, có con là composite, nhưng cả hai cùng một kiểu (Component).

- **`reduce(events)`** (`read_model.py:30-83`) fold event log thành cây: `ROOT_TASK_CREATED` (dòng 36-39) tạo gốc; `SUBTASK_SPAWNED` (dòng 40-46) tạo node con và **append vào `parent.children`**. Cấu trúc cây hình thành tự nhiên trong lúc fold.

- **`render_tree(root)`** (`drag_from_zero/dragzero/live_view.py:27-50`) duyệt cây bằng một hàm `walk()` **lồng bên trong** (dòng 32-47). Với mỗi node: in glyph trạng thái + description, rồi **đệ quy `walk(child)`** cho mọi `node.children`. **Tuyệt đối không có `isinstance`** — leaf và composite được xử lý y hệt nhau qua duck typing trên `node.children`.

Vấn đề mà Composite giải: UI phải render cây ở **độ sâu tùy ý** (task đẻ subtask, subtask lại đẻ subtask...) bằng **một** hàm render duy nhất, không phải viết lại logic cho mỗi cấp.

## 2. Trích đoạn code thật

Fold event thành cây — gắn con vào cha (`drag_from_zero/dragzero/read_model.py:36-46`):

```python
for e in events:
    t = e.type
    if t == EventType.ROOT_TASK_CREATED:
        node = TaskNode(e.task_id, e.payload.get("description", ""), None, done_when=list(e.payload.get("done_when") or []))
        nodes[e.task_id] = node
        root_id = e.task_id
    elif t == EventType.SUBTASK_SPAWNED:
        parent = e.payload.get("parent")
        node = TaskNode(e.task_id, e.payload.get("subtask", ""), parent, agent_id=e.agent_id,
                        done_when=list(e.payload.get("done_when") or []))
        nodes[e.task_id] = node
        if parent in nodes:
            nodes[parent].children.append(node)
```

Render đệ quy đồng nhất bằng `walk()` lồng (`drag_from_zero/dragzero/live_view.py:32-47`):

```python
def walk(node: TaskNode, prefix: str, is_last: bool, is_root: bool) -> None:
    glyph = GLYPH.get(node.status, "·")
    connector = "" if is_root else ("└─ " if is_last else "├─ ")
    head = f"{prefix}{connector}{glyph} {node.description} [{node.status}]"
    ...
    lines.append(head)
    child_prefix = prefix + ("   " if is_root else ("    " if is_last else "│   "))
    for i, child in enumerate(node.children):
        walk(child, child_prefix, i == len(node.children) - 1, False)
```

## 3. Bảng ánh xạ vai trò pattern ↔ code thật

| Vai trò Composite | Thành phần code thật |
|-------------------|----------------------|
| **Component** (interface chung) | `TaskNode` (`read_model.py:16-27`) — một kiểu duy nhất, có `children: list` |
| **Leaf** | `TaskNode` với `children == []` (vd: status DONE/FAILED, không sinh con) |
| **Composite** | `TaskNode` với `children` không rỗng (status DELEGATED/RUNNING, đã spawn subtask) |
| **Xây cấu trúc cây** | `reduce()` (`read_model.py:30-83`) — fold event, `SUBTASK_SPAWNED` append vào `parent.children` |
| **Đệ quy đóng gói** | `walk()` lồng trong `render_tree()` (`live_view.py:32-47`) — đệ quy trên `node.children` |
| **Client** | `render_tree(root)` / `render(events)` (`live_view.py:27-61`) — gọi `walk` không type-check |

## 4. Bản rút gọn chạy được

File: [`drag_from_zero_task_render.py`](./drag_from_zero_task_render.py) — chạy `python3 drag_from_zero_task_render.py`.

**Mô phỏng gì:**
- `TaskNode` cùng-một-kiểu (giữ `id`, `description`, `parent_id`, `status`, `children`).
- `reduce(events)` fold event log thành cây — giữ **nguyên** cấu trúc `ROOT_TASK_CREATED` tạo gốc, `SUBTASK_SPAWNED` append vào `parent.children`.
- `render_tree(root)` với `walk()` lồng, connector `├─` / `└─` giống bản thật, đệ quy trên `node.children` **không isinstance**.
- Demo dựng cây **sâu 3 cấp** (root → s1 → s1a/s1b) để thấy đệ quy tự thích nghi độ sâu.
- Thêm `count_done_leaves()` — một operation đệ quy **khác** trên cùng cây, minh họa "định nghĩa một lần, đúng mọi cấp".

**Lược bỏ gì:** Bộ `EventType` đầy đủ (`TASK_STARTED`, `TOOL_RESULT`, `DELEGATION_DECIDED`, `HOOK_BLOCKED`...) rút còn 3 loại đủ minh họa cây; glyph/decoration phong phú (agent_id, next_step, tools) rút gọn; `TaskStatus` enum thay bằng hằng chuỗi.

> **Lưu ý sai lệch ngữ nghĩa do rút gọn:** ở bản này, khi `SUBTASK_SPAWNED` gắn con thì cha được set `DELEGATED` ngay (dòng 95-96 của `drag_from_zero_task_render.py`) — chỉ để demo cây sinh ra trạng thái composite mà không cần thêm event. **Bản thật KHÔNG làm vậy:** trong `drag_from_zero/dragzero/read_model.py:64-69`, status `DELEGATED` chỉ được set qua event `DELEGATION_DECIDED` (mode `delegate`/`decompose`) hoặc `DECOMPOSITION_ACCEPTED`, hoàn toàn tách rời với việc append con. Đừng tưởng `reduce` thật tự suy ra `DELEGATED` từ việc có con — đó là quyết định tường minh bằng event riêng.

**Đối chứng (KHÔNG dùng Composite):** `render_naive_BAD()` hard-code render 2 cấp (gốc + con trực tiếp), **bỏ sót** cháu cấp 3 (`s1a`, `s1b`) — chúng biến mất khỏi output. Bản Composite `render_tree()` đệ quy nên in đủ. Output chạy thật cho thấy rõ sự khác biệt.

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Đệ quy có thể tràn stack** với cây cực sâu (Python mặc định ~1000 mức). `render_tree` đệ quy thuần; cây bệnh lý cần chuyển sang duyệt bằng stack tường minh.
- **`children` là `list` mutable trên dataclass.** `reduce` dựa vào `field(default_factory=list)` để mỗi node có list riêng — quên điều này là dính bug "shared mutable default" kinh điển. Composite kiểu này đặt gánh nặng đúng đắn lên việc khởi tạo node.
- **Read-model là projection, không phải nguồn sự thật.** Cây `TaskNode` chỉ đúng nếu fold đúng thứ tự event; một `SUBTASK_SPAWNED` tới trước cha của nó sẽ bị rớt (`if parent in nodes`). Composite ở đây không tự sửa thứ tự — nó giả định log đã đúng.
- **Nếu chỉ cần hiển thị danh sách phẳng** (không phân cấp), `TaskNode.children` + render đệ quy là phức tạp thừa; một list + vòng `for` là đủ.

## 6. Câu hỏi tự kiểm tra

1. `render_tree` không có một dòng `isinstance` nào. Điều gì khiến nó vẫn xử lý đúng cả leaf lẫn composite? (Gợi ý: vai trò của `node.children` và vòng `for` rỗng.)
2. `reduce` gắn con bằng `nodes[parent].children.append(node)`. Nếu event `SUBTASK_SPAWNED` của một cháu tới **trước** event tạo cha nó, chuyện gì xảy ra với cây? Đây là biến thể "Transparent" hay "Safe" về mặt an toàn cấu trúc?
3. Muốn thêm một operation mới "tổng số node đang RUNNING trong cả cây" thì cần sửa `TaskNode` không? So sánh với cách phải sửa nhiều `if isinstance` nếu KHÔNG dùng Composite.
