# Visitor Pattern trong hex_agent — hex_cases

> Tài liệu dạy học đi kèm bài `23_Visitor.md`. Khác với bài gốc (dùng analogy microglia
> + ví dụ tự chế), thư mục này soi **chính code thật trong hex_agent** để xem pattern
> Visitor đang sống ở đâu, đóng vai gì, và distill lại thành bản chạy được bằng stdlib.

---

## 1. Tóm tắt: Visitor sống ở đâu trong hex_agent?

Visitor (Behavioral) hiện diện trong hex_agent ở module **code index** — thành phần cho phép
agent định vị symbol/reference trong workspace mà không phải đọc lại toàn bộ file bằng tay.

Trái tim của nó là class **`_PythonIndexVisitor`** trong `toolbox/code_index.py`. Class này
**kế thừa `ast.NodeVisitor`** của thư viện chuẩn Python — đây chính là một hiện thực kinh điển
của Visitor pattern:

- **Element hierarchy stable**: cây AST (`ast.ClassDef`, `ast.FunctionDef`,
  `ast.AsyncFunctionDef`, `ast.Import`, `ast.ImportFrom`...) do module `ast` của Python định nghĩa.
  Hierarchy này cực kỳ ổn định — Python không thêm loại node mới mỗi sprint.
- **ConcreteVisitor**: `_PythonIndexVisitor` cài các method `visit_ClassDef`, `visit_FunctionDef`,
  `visit_AsyncFunctionDef`, `visit_Import`, `visit_ImportFrom` — mỗi method là một mảnh của
  **operation "index symbol + import"**.
- **Double dispatch**: `visitor.visit(tree)` (trong `_index_python`, dòng 126) dispatch theo
  `node.__class__.__name__` để gọi đúng `visit_<NodeType>` — đúng tinh thần `f(element_type, visitor_type)`.
- **State accumulation**: visitor tích luỹ `self.symbols`, `self.imports`, `self.class_stack`
  trong suốt quá trình duyệt mà **không mutate AST**.

Đây là **use case thuần tuý nhất** của Visitor: AST sẽ không đổi (stable), nhưng các operation
trên nó (index, lint, format, optimize, type-check) thì evolve độc lập. Mỗi operation = một
NodeVisitor subclass mới, không phải sửa cây AST.

---

## 2. Vì sao đây là Visitor "sách giáo khoa"?

| Tiêu chí Visitor | Biểu hiện trong hex_agent |
|---|---|
| Hierarchy element stable | Cây AST từ module `ast` — Python không thêm node type theo nhu cầu app |
| Tách operation khỏi element | `_PythonIndexVisitor` index AST mà **không** nhồi method `index()` vào từng node `ast.*` |
| Double dispatch | `visitor.visit(tree)` → `ast.NodeVisitor.visit()` dispatch theo `type(node).__name__` → `visit_ClassDef`... |
| State trong visitor | `class_stack`, `symbols`, `imports` sống suốt traverse |
| Thêm operation mới rẻ | Muốn lấy docstring/decorator → viết NodeVisitor mới, không đụng AST |
| Inverse Open/Closed | Thêm operation dễ; nếu AST thêm node type thì mọi visitor phải thêm `visit_X` — nhưng AST không đổi nên trade-off này "ăn" |

`ast.NodeVisitor` là **Reflective Visitor** (biến thể ở mục 2.4 của bài gốc): nó không cần
mỗi node implement `accept()`; thay vào đó `visit()` dùng `getattr(self, 'visit_' + type(node).__name__)`
để dispatch. Đó là lý do `_PythonIndexVisitor` chỉ cần khai báo các `visit_X` mà không cần
chạm vào class node của thư viện `ast` (vốn là code bên thứ ba — đúng tình huống "muốn áp
operation lên hierarchy mình không sở hữu" mà Visitor giải quyết).

---

## 3. Các case con

| # | Case | Distill từ | Trọng tâm |
|---|------|-----------|-----------|
| 01 | [`python_code_indexer_visitor`](./01_python_code_indexer_visitor/) | `toolbox/code_index.py:69-127` | NodeVisitor index AST: `visit_ClassDef`/`visit_FunctionDef`/`visit_Import`/`visit_ImportFrom`, double dispatch qua `visit(tree)`, state accumulation (`class_stack`, `symbols`, `imports`) không mutate AST |

Xem [CATALOG.md](./CATALOG.md) để có bảng vét cạn mọi occurrence của pattern trong file gốc.

---

## 4. Cách chạy

```bash
cd "Design patterns/23_Visitor/hex_cases"
python3 01_python_code_indexer_visitor/python_code_indexer_visitor.py
```

Mỗi file `.py`:
- Chỉ dùng **thư viện chuẩn Python 3.14** (chủ yếu là module `ast` — đúng module mà code thật dùng).
- Tự chứa, không import gì từ hex_agent.
- In narration tiếng Việt từng bước + có `assert` chứng minh bất biến của pattern.
- Có đối chứng "khi KHÔNG dùng Visitor thì khổ thế nào".
