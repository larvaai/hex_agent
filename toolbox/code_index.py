"""Read-only code index — symbols, references, imports, dependency graph. Epic E06.

Workspace-jailed stdlib ``ast`` (Python) + regex (JS/TS) index so an agent can locate
symbols and references without re-reading whole files by hand. Every path is resolved
through :func:`safety.sandbox.resolve_in_workspace`; nothing here mutates the workspace.

Tools: ``code_index``, ``code_find_symbol``, ``code_find_references``, ``code_dependency_graph``.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from core.schemas import ToolRequest
from safety.sandbox import SandboxError, resolve_in_workspace, workspace_dir

MAX_FILES = 1000
MAX_RESULTS = 500
CODE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx"}
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "agent_runs",
    "qdrant_storage",
    "var",
}


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace_dir())).replace("\\", "/")
    except ValueError:
        return str(path)


def _is_excluded(path: Path) -> bool:
    try:
        parts = set(path.resolve().relative_to(workspace_dir()).parts)
    except ValueError:
        return True
    return bool(parts & EXCLUDED_DIRS)


def _code_files(root: Path, max_files: int) -> tuple[list[Path], bool]:
    if root.is_file():
        ok = root.suffix.lower() in CODE_EXTENSIONS and not _is_excluded(root)
        return ([root] if ok else []), False
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if len(files) >= max_files:
            return files, True
        if not path.is_file() or path.suffix.lower() not in CODE_EXTENSIONS or _is_excluded(path):
            continue
        files.append(path)
    return files, False


def _node_range(node: ast.AST) -> dict[str, int | None]:
    return {
        "lineno": getattr(node, "lineno", None),
        "end_lineno": getattr(node, "end_lineno", None),
    }


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

    def visit_Import(self, node: ast.Import) -> Any:
        for alias in node.names:
            self.imports.append(
                {"type": "import", "module": alias.name, "file": _rel(self.file_path), "lineno": getattr(node, "lineno", None)}
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        self.imports.append(
            {
                "type": "from_import",
                "module": node.module or "",
                "names": [alias.name for alias in node.names],
                "level": node.level,
                "file": _rel(self.file_path),
                "lineno": getattr(node, "lineno", None),
            }
        )


_JS_CLASS_RE = re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)")
_JS_FUNC_RE = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)")
_JS_CONST_FUNC_RE = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"
)
_JS_IMPORT_RE = re.compile(r"^\s*import\s+(?:.+?\s+from\s+)?[\"']([^\"']+)[\"']")


def _index_python(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    visitor = _PythonIndexVisitor(path)
    visitor.visit(tree)
    return visitor.symbols, visitor.imports


def _index_js_like(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    symbols: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        for regex, symbol_type in ((_JS_CLASS_RE, "class"), (_JS_FUNC_RE, "function"), (_JS_CONST_FUNC_RE, "function")):
            match = regex.search(line)
            if match:
                symbols.append({"type": symbol_type, "name": match.group(1), "file": _rel(path), "lineno": lineno})
                break
        import_match = _JS_IMPORT_RE.search(line)
        if import_match:
            imports.append({"type": "import", "module": import_match.group(1), "file": _rel(path), "lineno": lineno})
    return symbols, imports


def _index_file(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if path.suffix.lower() == ".py":
        return _index_python(path)
    return _index_js_like(path)


def _clamp(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(int(value), hi))
    except (TypeError, ValueError):
        return default


def _index_root(path: str, max_files: int) -> dict[str, Any]:
    root = resolve_in_workspace(path or ".")
    files, truncated = _code_files(root, max_files)
    symbols: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for file_path in files:
        try:
            file_symbols, file_imports = _index_file(file_path)
            symbols.extend(file_symbols)
            imports.extend(file_imports)
        except SyntaxError as exc:
            errors.append({"file": _rel(file_path), "error": str(exc), "type": "syntax_error"})
        except Exception as exc:  # pragma: no cover - defensive
            errors.append({"file": _rel(file_path), "error": str(exc), "type": "index_error"})
    return {
        "ok": True,
        "files_count": len(files),
        "truncated": truncated,
        "symbols_count": len(symbols),
        "imports_count": len(imports),
        "symbols": symbols,
        "imports": imports,
        "errors": errors[:100],
    }


class CodeIndex:
    name = "code_index"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        path = str(request.args.get("path", "."))
        max_files = _clamp(request.args.get("max_files", 300), 1, MAX_FILES, 300)
        try:
            result = _index_root(path, max_files)
        except (SandboxError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        result["symbols"] = result["symbols"][:MAX_RESULTS]
        result["imports"] = result["imports"][:MAX_RESULTS]
        return result


class CodeFindSymbol:
    name = "code_find_symbol"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        query = str(request.args.get("name", "")).lower()
        if not query:
            return {"ok": False, "error": "name is required"}
        path = str(request.args.get("path", "."))
        max_files = _clamp(request.args.get("max_files", 300), 1, MAX_FILES, 300)
        max_results = _clamp(request.args.get("max_results", 50), 1, MAX_RESULTS, 50)
        try:
            indexed = _index_root(path, max_files)
        except (SandboxError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        matches = [s for s in indexed["symbols"] if query in str(s.get("name", "")).lower()][:max_results]
        return {"ok": True, "name": request.args.get("name"), "count": len(matches), "matches": matches}


class CodeFindReferences:
    name = "code_find_references"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        name = str(request.args.get("name", ""))
        if not name:
            return {"ok": False, "error": "name is required"}
        path = str(request.args.get("path", "."))
        max_files = _clamp(request.args.get("max_files", 300), 1, MAX_FILES, 300)
        max_results = _clamp(request.args.get("max_results", 100), 1, MAX_RESULTS, 100)
        try:
            root = resolve_in_workspace(path or ".")
        except (SandboxError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        files, truncated = _code_files(root, max_files)
        references: list[dict[str, Any]] = []
        for file_path in files:
            for lineno, line in enumerate(file_path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
                if name in line:
                    references.append({"file": _rel(file_path), "lineno": lineno, "line": line.strip()[:300]})
                    if len(references) >= max_results:
                        return {"ok": True, "name": name, "count": len(references), "truncated": True, "references": references}
        return {"ok": True, "name": name, "count": len(references), "truncated": truncated, "references": references}


class CodeDependencyGraph:
    name = "code_dependency_graph"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        path = str(request.args.get("path", "."))
        max_files = _clamp(request.args.get("max_files", 300), 1, MAX_FILES, 300)
        try:
            indexed = _index_root(path, max_files)
        except (SandboxError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        graph: dict[str, list[str]] = {}
        for item in indexed["imports"]:
            file_name, module = item.get("file"), item.get("module")
            if not file_name or not module:
                continue
            bucket = graph.setdefault(str(file_name), [])
            if str(module) not in bucket:
                bucket.append(str(module))
        return {"ok": True, "files_count": indexed["files_count"], "graph": graph}


CODE_INDEX_TOOLS = (CodeIndex, CodeFindSymbol, CodeFindReferences, CodeDependencyGraph)
