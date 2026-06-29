"""
Visitor Pattern (Behavioral) — bản distill TRUNG THỰC từ hex_agent.

NGUỒN THẬT distill từ đây (đã mở file xác minh số dòng):
    hex_agent/toolbox/code_index.py
        - class _PythonIndexVisitor(ast.NodeVisitor)        : dòng 69-74   (ConcreteVisitor + __init__ state)
        - visit_ClassDef                                    : dòng 76-82
        - visit_FunctionDef / visit_AsyncFunctionDef        : dòng 84-94
        - visit_Import                                      : dòng 96-100
        - visit_ImportFrom                                  : dòng 102-112
        - _index_python() (entry point gọi visitor.visit)   : dòng 123-127
        - _node_range() helper                              : dòng 62-66

Ý TƯỞNG: Trong hex_agent, agent cần "đánh chỉ mục" code (liệt kê class/hàm/method và các
import) để định vị symbol nhanh mà không đọc lại cả file. Code thật KHÔNG nhồi method
index() vào từng loại node AST của Python — nó tách operation đó ra một NodeVisitor riêng.
Đó chính là Visitor pattern: hierarchy element (cây AST) STABLE, còn operation (index, lint,
format, optimize...) thì evolve độc lập, mỗi operation = một NodeVisitor subclass.

BẢN DISTILL NÀY GIỮ NGUYÊN:
    - Dùng đúng module chuẩn `ast` + `ast.NodeVisitor` (giống hệt code thật) -> double dispatch
      thật qua `visit(tree)` dispatch theo type(node).__name__.
    - Đúng các handler visit_ClassDef / visit_FunctionDef / visit_AsyncFunctionDef /
      visit_Import / visit_ImportFrom.
    - Đúng state accumulation: class_stack (xử lý lồng nhau), symbols, imports — KHÔNG mutate AST.

LƯỢC BỎ (so với code thật) — thay hạ tầng nặng bằng fake stdlib tối thiểu:
    - safety.sandbox.resolve_in_workspace / workspace-jail / đọc file thật trên đĩa
      -> thay bằng SOURCE chuỗi inline + ast.parse trực tiếp.
    - Phần JS/TS index bằng regex (_index_js_like) — không liên quan Visitor, bỏ.
    - Wrapper tool class CodeIndex/CodeFindSymbol... — bỏ, chỉ giữ lõi visitor.

Chạy: python3 python_code_indexer_visitor.py   (yêu cầu Python 3.x; viết cho 3.14, chỉ stdlib)
"""

from __future__ import annotations

import ast
from typing import Any


# ---------------------------------------------------------------------------
# "File nguồn" để index. Ở hex_agent đây là nội dung đọc từ workspace qua sandbox;
# ở bản distill ta nhúng thẳng một chuỗi để self-contained.
# ---------------------------------------------------------------------------
SAMPLE_SOURCE = '''\
import os
from collections import OrderedDict, defaultdict

class Robot:
    """Robot điều khiển — có docstring để DocstringCountVisitor đếm khác 0."""
    def boot(self):
        """Khởi động robot và trả về trạng thái."""
        return "online"

    async def scan(self):
        return []

    class Arm:                 # class lồng trong class -> test class_stack
        def grab(self):
            return "grabbed"

def standalone_helper(x):
    return x * 2

async def fetch_remote(url):
    return url
'''


# ---------------------------------------------------------------------------
# Helper distill từ _node_range() (code_index.py:62-66)
# ---------------------------------------------------------------------------
def _node_range(node: ast.AST) -> dict[str, int | None]:
    return {
        "lineno": getattr(node, "lineno", None),
        "end_lineno": getattr(node, "end_lineno", None),
    }


# ===========================================================================
# ConcreteVisitor — distill từ _PythonIndexVisitor (code_index.py:69-112)
#
# Đây là Visitor pattern dạng Reflective Visitor: ta KHÔNG viết accept() cho
# từng node. ast.NodeVisitor.visit() tự dispatch bằng
#     getattr(self, 'visit_' + type(node).__name__, self.generic_visit)
# -> đúng tinh thần double dispatch f(element_type, visitor_type).
# ===========================================================================
class PythonIndexVisitor(ast.NodeVisitor):
    def __init__(self, file_label: str) -> None:
        self.file_label = file_label
        # State của visitor — sống suốt quá trình traverse, KHÔNG nằm trong AST.
        self.class_stack: list[str] = []                # ngăn xếp tên class để build qualified name
        self.symbols: list[dict[str, Any]] = []         # accumulator: class/method/function
        self.imports: list[dict[str, Any]] = []         # accumulator: import / from-import

    # --- visit_ClassDef (code_index.py:76-82) ---------------------------------
    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        qualified = ".".join([*self.class_stack, node.name])
        self.symbols.append(
            {"type": "class", "name": qualified, "file": self.file_label, **_node_range(node)}
        )
        # push -> traverse con (generic_visit) -> pop : đúng pattern duyệt cây có ngữ cảnh.
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    # --- visit_FunctionDef (code_index.py:84-85) ------------------------------
    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._visit_function(node, "function")

    # --- visit_AsyncFunctionDef (code_index.py:87-88) -------------------------
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._visit_function(node, "async_function")

    # --- helper _visit_function (code_index.py:90-94) -------------------------
    def _visit_function(self, node: Any, fallback_type: str) -> None:
        # Trong class -> 'method'; ngoài class -> 'function'/'async_function'.
        symbol_type = "method" if self.class_stack else fallback_type
        name = ".".join([*self.class_stack, node.name]) if self.class_stack else node.name
        self.symbols.append(
            {"type": symbol_type, "name": name, "file": self.file_label, **_node_range(node)}
        )
        self.generic_visit(node)

    # --- visit_Import (code_index.py:96-100) ----------------------------------
    def visit_Import(self, node: ast.Import) -> Any:
        for alias in node.names:
            self.imports.append(
                {
                    "type": "import",
                    "module": alias.name,
                    "file": self.file_label,
                    "lineno": getattr(node, "lineno", None),
                }
            )

    # --- visit_ImportFrom (code_index.py:102-112) -----------------------------
    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        self.imports.append(
            {
                "type": "from_import",
                "module": node.module or "",
                "names": [alias.name for alias in node.names],
                "level": node.level,
                "file": self.file_label,
                "lineno": getattr(node, "lineno", None),
            }
        )


# ===========================================================================
# Entry point — distill từ _index_python() (code_index.py:123-127)
# ===========================================================================
def index_python(source: str, file_label: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tree = ast.parse(source, filename=file_label)   # cây AST = Element hierarchy (STABLE)
    visitor = PythonIndexVisitor(file_label)        # ConcreteVisitor
    visitor.visit(tree)                             # <-- DOUBLE DISPATCH toàn cây
    return visitor.symbols, visitor.imports


# ---------------------------------------------------------------------------
# Một ConcreteVisitor THỨ HAI để chứng minh sức mạnh của Visitor:
# thêm operation mới (đếm docstring) mà KHÔNG đụng vào cây AST, KHÔNG sửa
# PythonIndexVisitor. Đây chính là "thêm op = thêm visitor" của pattern.
# ---------------------------------------------------------------------------
class DocstringCountVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.with_docstring = 0
        self.without_docstring = 0

    def _check(self, node: Any) -> None:
        if ast.get_docstring(node):
            self.with_docstring += 1
        else:
            self.without_docstring += 1
        self.generic_visit(node)

    visit_ClassDef = _check
    visit_FunctionDef = _check
    visit_AsyncFunctionDef = _check


# ---------------------------------------------------------------------------
# ĐỐI CHỨNG: "khi KHÔNG dùng Visitor" — viết tay vòng lặp + isinstance chuỗi dài.
# Mục tiêu: cho cùng kết quả symbols, nhưng cho thấy nó cồng kềnh, không tái dùng
# traversal, và mỗi operation mới lại phải copy nguyên khối isinstance này.
# (Đây là anti-pattern "isinstance check thay vì double dispatch" ở bài gốc.)
# ---------------------------------------------------------------------------
def index_without_visitor(source: str, file_label: str) -> list[dict[str, Any]]:
    tree = ast.parse(source, filename=file_label)
    symbols: list[dict[str, Any]] = []

    def walk(node: ast.AST, class_stack: list[str]) -> None:
        for child in ast.iter_child_nodes(node):
            # Phải tự phân loại bằng isinstance — không có dispatch tự động.
            if isinstance(child, ast.ClassDef):
                qualified = ".".join([*class_stack, child.name])
                symbols.append({"type": "class", "name": qualified, "file": file_label, **_node_range(child)})
                walk(child, [*class_stack, child.name])
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fallback = "function" if isinstance(child, ast.FunctionDef) else "async_function"
                stype = "method" if class_stack else fallback
                name = ".".join([*class_stack, child.name]) if class_stack else child.name
                symbols.append({"type": stype, "name": name, "file": file_label, **_node_range(child)})
                walk(child, class_stack)
            else:
                walk(child, class_stack)

    walk(tree, [])
    return symbols


# ---------------------------------------------------------------------------
def demo() -> None:
    print("=" * 72)
    print("CASE 01 — Visitor pattern: PythonIndexVisitor (distill từ code_index.py)")
    print("=" * 72)

    print("\n[Bước 1] Parse source -> cây AST (Element hierarchy STABLE của module `ast`).")
    print("         Đây là hierarchy ta KHÔNG sở hữu (stdlib) — Visitor cho phép")
    print("         áp operation lên nó mà không cần sửa class node.")

    print("\n[Bước 2] Tạo PythonIndexVisitor và gọi visitor.visit(tree).")
    print("         ast.NodeVisitor.visit() DISPATCH theo type(node).__name__ ->")
    print("         visit_ClassDef / visit_FunctionDef / visit_Import / ... (double dispatch).")
    symbols, imports = index_python(SAMPLE_SOURCE, "robot.py")

    print("\n[Bước 3] State tích luỹ trong visitor (KHÔNG nằm trong AST):")
    print("  -- SYMBOLS --")
    for s in symbols:
        print(f"    [{s['type']:<14}] {s['name']:<20} (dòng {s['lineno']})")
    print("  -- IMPORTS --")
    for im in imports:
        if im["type"] == "import":
            print(f"    [import        ] {im['module']} (dòng {im['lineno']})")
        else:
            print(f"    [from_import   ] from {im['module']} import {im['names']} (dòng {im['lineno']})")

    # -------- ASSERT chứng minh tính đúng đắn của Visitor --------
    names = {s["name"] for s in symbols}
    types = {s["name"]: s["type"] for s in symbols}

    # 1. class lồng nhau -> qualified name nhờ class_stack (state visitor).
    assert "Robot" in names, "Phải index được class Robot"
    assert "Robot.Arm" in names, "class lồng nhau phải có qualified name Robot.Arm"
    # 2. hàm trong class -> 'method'; ngoài class -> 'function'/'async_function'.
    assert types["Robot.boot"] == "method", "boot() trong class phải là method"
    assert types["Robot.scan"] == "method", "scan() async trong class vẫn là method"
    assert types["standalone_helper"] == "function", "hàm top-level là function"
    assert types["fetch_remote"] == "async_function", "async hàm top-level là async_function"
    # 3. import được tách thành import vs from_import.
    import_modules = {im["module"] for im in imports if im["type"] == "import"}
    from_modules = {im["module"] for im in imports if im["type"] == "from_import"}
    assert "os" in import_modules, "phải bắt được 'import os'"
    assert "collections" in from_modules, "phải bắt được 'from collections import ...'"
    print("\n[ASSERT] OK: qualified name, method/function, import/from_import đều đúng.")

    # -------- Thêm OPERATION MỚI mà KHÔNG đụng AST, KHÔNG sửa visitor cũ --------
    print("\n[Bước 4] Thêm operation mới = thêm visitor mới (DocstringCountVisitor),")
    print("         KHÔNG sửa AST, KHÔNG sửa PythonIndexVisitor. Đây là Open/Closed")
    print("         theo chiều 'thêm operation' — sweet spot của Visitor.")
    tree = ast.parse(SAMPLE_SOURCE, filename="robot.py")
    doc_visitor = DocstringCountVisitor()
    doc_visitor.visit(tree)
    print(f"         có docstring: {doc_visitor.with_docstring}, "
          f"không docstring: {doc_visitor.without_docstring}")
    assert doc_visitor.with_docstring + doc_visitor.without_docstring == len(symbols), \
        "DocstringCountVisitor phải duyệt đúng số class/hàm như PythonIndexVisitor"
    print("[ASSERT] OK: cùng cây AST, visitor thứ hai chạy độc lập, kết quả nhất quán.")

    # -------- ĐỐI CHỨNG: không dùng Visitor --------
    print("\n[Bước 5] ĐỐI CHỨNG — index_without_visitor(): tự viết walk + chuỗi isinstance.")
    manual = index_without_visitor(SAMPLE_SOURCE, "robot.py")
    manual_view = sorted((s["type"], s["name"]) for s in manual)
    visitor_view = sorted((s["type"], s["name"]) for s in symbols)
    assert manual_view == visitor_view, "bản thủ công phải ra cùng kết quả"
    print("         Kết quả GIỐNG, NHƯNG:")
    print("           - Phải tự lặp ast.iter_child_nodes + tự đệ quy + tự giữ class_stack.")
    print("           - Mỗi loại node = một nhánh isinstance; thêm op mới = copy cả khối này.")
    print("           - Mất dispatch tự động của NodeVisitor -> dễ quên một loại node.")
    print("[ASSERT] OK: cùng output, nhưng Visitor gọn hơn và tách bạch traversal/operation.")

    print("\n" + "=" * 72)
    print("KẾT LUẬN: AST = Element hierarchy stable; PythonIndexVisitor = ConcreteVisitor;")
    print("visitor.visit(tree) = double dispatch; symbols/imports/class_stack = state.")
    print("Thêm operation (index, đếm docstring, lint...) = thêm visitor, KHÔNG sửa AST.")
    print("=" * 72)


if __name__ == "__main__":
    demo()
