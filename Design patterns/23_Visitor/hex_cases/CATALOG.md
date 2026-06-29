# CATALOG — mọi occurrence của Visitor trong hex_agent

Bảng vét cạn các điểm code hiện thực/biểu hiện pattern Visitor, lấy từ bước discover và
**đã mở lại file gốc xác minh số dòng** (`toolbox/code_index.py`).

Tất cả path tính tương đối từ root `/Users/uspro/Desktop/namnson/hex_agent/`.

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `toolbox/code_index.py:69-74` | Khai báo `class _PythonIndexVisitor(ast.NodeVisitor)` + `__init__` khởi tạo state visitor (`class_stack`, `symbols`, `imports`). Đây là **ConcreteVisitor** của pattern. | cao |
| `toolbox/code_index.py:76-82` | `visit_ClassDef` — ghi nhận symbol class với qualified name (xử lý lồng nhau qua `class_stack`), push tên class, gọi `generic_visit(node)` để tiếp tục traverse, rồi pop. | cao |
| `toolbox/code_index.py:84-94` | `visit_FunctionDef` (84-85) + `visit_AsyncFunctionDef` (87-88) cùng uỷ quyền cho helper `_visit_function` (90-94) — quyết định symbol là `method` hay `function` dựa vào `class_stack`, ghi symbol, tiếp tục `generic_visit`. | cao |
| `toolbox/code_index.py:96-100` | `visit_Import` — trích tên module từ các `node.names`, ghi vào `imports`. | cao |
| `toolbox/code_index.py:102-112` | `visit_ImportFrom` — trích module + danh sách tên + `level` của from-import, ghi vào `imports`. | cao |
| `toolbox/code_index.py:123-127` | `_index_python()` — **entry point dùng Visitor**: `ast.parse(...)` → tạo `_PythonIndexVisitor` → gọi `visitor.visit(tree)` (dòng 126, kích hoạt double dispatch toàn cây) → trả `symbols, imports` đã tích luỹ. | cao |
| `toolbox/code_index.py:62-66` | `_node_range(node)` — helper đọc `lineno`/`end_lineno` của node, dùng trong các `visit_X` để gắn vị trí symbol. Hỗ trợ visitor (không phải vai chính nhưng thuộc cơ chế). | trung bình |

## Ghi chú phân loại

- **Reflective Visitor**: hex_agent không tự viết `accept()` cho từng node. Nó dựa vào
  `ast.NodeVisitor.visit()` của stdlib, vốn dispatch bằng
  `getattr(self, 'visit_' + type(node).__name__, self.generic_visit)`. Đây là biến thể
  "Reflective Visitor" ở mục 2.4 bài gốc — tiết kiệm boilerplate `accept`, đánh đổi type-safety.
- **Stateful Visitor**: `_PythonIndexVisitor` tích luỹ state (`symbols`, `imports`, `class_stack`)
  trong suốt traverse — biến thể "Stateful Visitor".
- `_index_js_like` (dòng 130-142) **không** dùng Visitor — nó quét regex theo dòng vì JS/TS không
  có sẵn AST stdlib. Đối chiếu này nhấn mạnh: Visitor chỉ áp dụng được khi có **hierarchy element
  stable** (AST Python); với input không có AST, hex_agent buộc phải fallback sang regex tuyến tính.
