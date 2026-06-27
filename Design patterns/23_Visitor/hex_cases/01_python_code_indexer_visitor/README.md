# Case 01 — Python AST Indexer: Visitor qua `ast.NodeVisitor`

> Distill từ **`toolbox/code_index.py:69-127`** trong hex_agent.
> File chạy được: [`python_code_indexer_visitor.py`](./python_code_indexer_visitor.py)

---

## 1. Bối cảnh trong hex_agent — vấn đề thật

Module `toolbox/code_index.py` là một read-only **code index** (Epic E06): nó cho agent
"đánh chỉ mục" workspace — liệt kê class/hàm/method và import — để định vị symbol nhanh mà
không phải đọc lại cả file bằng tay. Docstring đầu file (dòng 1-8) nói rõ: dùng `ast` (Python)
+ regex (JS/TS), mọi path đi qua sandbox, **không mutate workspace**.

Vấn đề thiết kế: ta cần **một operation** (trích symbol + import) chạy trên **một hierarchy
element stable** (cây AST do module `ast` của Python dựng). Cây AST này không phải code của
hex_agent — nó là class của stdlib (`ast.ClassDef`, `ast.FunctionDef`, ...). Ta **không thể**
(và không nên) nhồi method `index()` vào từng class node đó.

Lời giải trong code thật: tách operation ra một **NodeVisitor subclass** — đúng Visitor pattern.

- `class _PythonIndexVisitor(ast.NodeVisitor)` — `toolbox/code_index.py:69-74`
- các handler `visit_ClassDef` / `visit_FunctionDef` / `visit_AsyncFunctionDef` /
  `visit_Import` / `visit_ImportFrom` — `toolbox/code_index.py:76-112`
- entry point `_index_python()` gọi `visitor.visit(tree)` — `toolbox/code_index.py:123-127`

(Đã mở file gốc xác minh đúng các dòng trên.)

---

## 2. Trích đoạn code thật

```python
# toolbox/code_index.py:69-94
class _PythonIndexVisitor(ast.NodeVisitor):
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.class_stack: list[str] = []
        self.symbols: list[dict[str, Any]] = []
        self.imports: list[dict[str, Any]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        self.symbols.append(
            {"type": "class", "name": ".".join([*self.class_stack, node.name]), "file": _rel(self.file_path), **_node_range(node)}
        )
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._visit_function(node, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._visit_function(node, "async_function")

    def _visit_function(self, node: Any, fallback_type: str) -> None:
        symbol_type = "method" if self.class_stack else fallback_type
        name = ".".join([*self.class_stack, node.name]) if self.class_stack else node.name
        self.symbols.append({"type": symbol_type, "name": name, "file": _rel(self.file_path), **_node_range(node)})
        self.generic_visit(node)
```

```python
# toolbox/code_index.py:123-127  — entry point dùng Visitor
def _index_python(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    visitor = _PythonIndexVisitor(path)
    visitor.visit(tree)            # <-- kích hoạt double dispatch toàn cây
    return visitor.symbols, visitor.imports
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò trong Visitor pattern | Thành phần trong hex_agent (`code_index.py`) |
|---|---|
| **Element hierarchy** (stable) | Cây AST: `ast.ClassDef`, `ast.FunctionDef`, `ast.AsyncFunctionDef`, `ast.Import`, `ast.ImportFrom` (do module `ast` của Python định nghĩa) |
| **Visitor interface** | `ast.NodeVisitor` (stdlib) — cung cấp `visit()` + `generic_visit()` |
| **ConcreteVisitor** | `_PythonIndexVisitor` (dòng 69-112) |
| **`accept()` / cơ chế dispatch** | `ast.NodeVisitor.visit(node)`: `getattr(self, 'visit_' + type(node).__name__, generic_visit)` — Reflective Visitor, không cần `accept()` viết tay |
| **`visit_X` handlers** | `visit_ClassDef` (76), `visit_FunctionDef` (84), `visit_AsyncFunctionDef` (87), `visit_Import` (96), `visit_ImportFrom` (102) |
| **Traverse / đệ quy** | `self.generic_visit(node)` đi xuống con + `visitor.visit(tree)` ở entry point (dòng 126) |
| **Operation** | Trích & index symbol (class/method/function) + import |
| **State của Visitor** | `class_stack` (qualified name cho node lồng nhau), `symbols`, `imports` — sống suốt traverse, **không** nằm trong AST |

---

## 4. Bản rút gọn chạy được

File [`python_code_indexer_visitor.py`](./python_code_indexer_visitor.py) mô phỏng đúng lõi trên.

**Giữ nguyên (trung thực với code thật):**
- Dùng đúng `ast` + `ast.NodeVisitor` của stdlib → **double dispatch thật**, không giả lập.
- Đúng 5 handler `visit_ClassDef` / `visit_FunctionDef` / `visit_AsyncFunctionDef` /
  `visit_Import` / `visit_ImportFrom` và helper `_visit_function`.
- Đúng state `class_stack` → qualified name (`Robot.Arm.grab`), phân biệt `method` vs
  `function`/`async_function`, tách `import` vs `from_import`.

**Lược bỏ (thay hạ tầng nặng bằng fake stdlib):**
- `safety.sandbox.resolve_in_workspace` / workspace-jail / đọc file thật trên đĩa
  → thay bằng chuỗi `SAMPLE_SOURCE` nhúng inline + `ast.parse` trực tiếp.
- Nhánh index JS/TS bằng regex (`_index_js_like`) — không dùng Visitor nên bỏ.
- Các wrapper tool (`CodeIndex`, `CodeFindSymbol`, ...) — bỏ, chỉ giữ lõi visitor.

**Bổ sung để dạy học:**
- `DocstringCountVisitor` — một ConcreteVisitor **thứ hai**, chứng minh "thêm operation =
  thêm visitor, không sửa AST cũng không sửa visitor cũ" (Open/Closed theo chiều operation).
- `index_without_visitor()` — **đối chứng**: tự viết `walk` + chuỗi `isinstance`; ra **cùng
  kết quả** nhưng cồng kềnh, không tách bạch traversal/operation, và mỗi op mới phải copy lại
  cả khối isinstance (đúng anti-pattern "isinstance thay vì double dispatch" của bài gốc).
- Các `assert` chứng minh bất biến: qualified name của node lồng nhau, phân loại method/function,
  tách import/from_import, và hai visitor duyệt cùng số node.

Chạy:
```bash
python3 python_code_indexer_visitor.py   # in narration tiếng Việt + assert, thoát code 0
```

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Inverse Open/Closed**: hex_agent thêm operation rẻ (viết NodeVisitor mới như đếm docstring,
  lint, đo độ phức tạp...). Nhưng nếu **hierarchy element** phải thêm loại node mới thì mọi
  visitor phải thêm `visit_X`. Ở đây trade-off đó "ăn" vì cây AST của Python **cực kỳ stable** —
  chọn Visitor là đúng chỗ.
- **Khi không có hierarchy stable thì Visitor bất lực**: chính `code_index.py` minh hoạ — JS/TS
  không có AST stdlib nên hex_agent phải fallback sang quét regex tuyến tính (`_index_js_like`,
  dòng 130-142), **không** dùng Visitor. Nếu cố ép Visitor lên input không có cây node ổn định
  thì sai pattern.
- **Reflective dispatch mất type-safety**: `ast.NodeVisitor` dùng `getattr` theo tên class. Gõ
  sai tên handler (`visit_ClasDef`) sẽ **âm thầm** rơi vào `generic_visit` thay vì báo lỗi —
  đúng anti-pattern "forgotten visit_X" của bài gốc.
- Nếu chỉ cần **một thao tác đơn giản, một lần** trên cây nhỏ, dùng `ast.walk` + `match-case`
  có khi gọn hơn cả việc dựng một NodeVisitor subclass.

---

## 6. Câu hỏi tự kiểm tra

1. Trong `_index_python()` (dòng 123-127), dòng nào kích hoạt double dispatch, và `ast.NodeVisitor`
   quyết định gọi `visit_ClassDef` hay `visit_Import` dựa vào cái gì?
2. `class_stack` đóng vai trò gì? Vì sao nhờ nó mà `grab` trong `Robot.Arm` được index thành
   `Robot.Arm.grab` với type `method` chứ không phải `function`? (Gợi ý: xem `visit_ClassDef`
   push/pop quanh `generic_visit`.)
3. Muốn thêm operation "liệt kê mọi decorator của hàm" vào code index, theo Visitor pattern bạn
   sẽ thêm gì và **không** được đụng vào đâu? Nếu cây AST của Python thêm một loại node mới thì
   chi phí dồn về phía nào — và vì sao trade-off đó vẫn chấp nhận được ở đây?
