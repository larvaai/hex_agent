# Composite trong hex_agent — Tổng quan các case thật

> **Composite = tổ chức object thành cây part-whole, để client xử lý đồng nhất single object và composite of objects, đệ quy đóng gói bên trong cấu trúc.**

Tài liệu này soi pattern **Composite (Structural)** trong codebase thật `hex_agent`. Không phải ví dụ cortical column trong bài học gốc (`08_Composite.md`) — mà là nơi pattern **đang chạy thật** trong sản phẩm, được rút gọn (distill) thành code stdlib chạy được để học.

## Composite biểu hiện ở đâu trong hex_agent?

hex_agent có **hai cây part-whole rõ rệt**, cả hai đều mang đủ tính chất cốt lõi của Composite — interface đồng nhất để client xử lý leaf và composite giống nhau, đệ quy nằm trong cấu trúc:

1. **`decompose_agent` — cây task (task tree).** `Node` là một đơn vị công việc. Một node có thể là **leaf** (việc nguyên tử, có tiêu chí `done_when` cụ thể) hoặc **composite** (đã `decomposed` thành con). Vòng lặp `solve()` đi qua cây bằng con trỏ `next_node()` mà **không cần phân biệt** node là leaf hay composite; khi một composite có đủ con xong, completion được **lan ngược lên trên** (`_close_done_parents`) theo đệ quy. Ràng buộc thật: mỗi lần decompose phải làm bài toán **nhỏ đi** (tiêu chí chặt hơn) — đây chính là điều giữ cho cây hữu hạn.

2. **`drag_from_zero` — cây render task (`TaskNode`).** Một event log được "fold" (`reduce`) thành cây `TaskNode`: `ROOT_TASK_CREATED` tạo gốc, `SUBTASK_SPAWNED` gắn con vào cha. Hàm `render_tree(root)` đi DFS bằng một hàm `walk()` lồng bên trong, **không hề có `isinstance`** — leaf và composite được duyệt như nhau qua `node.children`.

## Các case con

| # | Case | Vai trò Composite nổi bật | Nguồn thật chính |
|---|------|---------------------------|------------------|
| 01 | [decompose_agent_task_tree](./01_decompose_agent_task_tree/) | Cây cha-con đệ quy: decompose động + lan completion ngược lên | `decompose_agent/tree.py`, `node.py`, `solve.py` |
| 02 | [drag_from_zero_task_render](./02_drag_from_zero_task_render/) | Render cây phân cấp đệ quy từ event log, không type-check | `drag_from_zero/dragzero/read_model.py`, `live_view.py` |

Mỗi folder có:
- `README.md` — bài học (6 mục): bối cảnh thật, trích đoạn code thật, bảng ánh xạ vai trò, bản rút gọn chạy được, cái giá, câu hỏi tự kiểm tra.
- `<name>.py` — bản distill self-contained, chỉ dùng thư viện chuẩn Python, có `demo()` in narration tiếng Việt + `assert` chứng minh bất biến.

## Vét cạn occurrence

Xem [CATALOG.md](./CATALOG.md) — bảng liệt kê **mọi** chỗ Composite (hoặc cấu trúc cây part-whole) xuất hiện trong hex_agent, kèm `path:line`, mô tả, và độ rõ.

## Điểm khác biệt giữa hai cây (đáng để ý khi học)

- **decompose_agent** giữ **cả hai chiều liên kết**: `parent` (con trỏ con → cha, dạng frozen field trên `Node`) và `_children` (index cha → các id con, dựng lại bằng `rebuild_children()`). Cây **lớn lên lúc runtime** khi decompose, và completion **chảy ngược lên** cha.
- **drag_from_zero** giữ liên kết chiều xuôi qua `children: list` trực tiếp trên `TaskNode` (và `parent_id` để fold). Cây được **dựng một lần từ event log** rồi render đệ quy. Đây là Composite ở ngữ cảnh **rendering / read-model** thuần.

Cùng một pattern, hai sắc thái: một cái "động" (cây sửa khi chạy, đóng nút bottom-up), một cái "tĩnh" (cây projection rồi duyệt). Học cả hai để thấy Composite không chỉ là "list con" mà là **giao diện đồng nhất + đệ quy đóng gói**.
