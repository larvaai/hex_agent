"""Read-only code index — symbols / find / references / dependency graph. Epic E06."""
from __future__ import annotations

from core.schemas import ToolRequest
from toolbox.code_index import CodeDependencyGraph, CodeFindReferences, CodeFindSymbol, CodeIndex

SAMPLE = '''\
import os
from pathlib import Path


class Widget:
    def render(self):
        return os.getcwd()


def make_widget():
    return Widget()
'''


def _ws(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "mod.py").write_text(SAMPLE, encoding="utf-8")


def _run(tool, **args):
    return tool().execute(ToolRequest(name=tool.name, args=args))


def test_code_index_lists_symbols_and_imports(tmp_path, monkeypatch):
    _ws(tmp_path, monkeypatch)
    out = _run(CodeIndex, path=".")
    assert out["ok"] is True
    names = {s["name"] for s in out["symbols"]}
    assert {"Widget", "Widget.render", "make_widget"} <= names
    modules = {i["module"] for i in out["imports"]}
    assert {"os", "pathlib"} <= modules


def test_find_symbol_is_partial_and_case_insensitive(tmp_path, monkeypatch):
    _ws(tmp_path, monkeypatch)
    out = _run(CodeFindSymbol, name="widget")
    assert out["ok"] is True and out["count"] >= 2
    assert any(m["name"] == "make_widget" for m in out["matches"])


def test_find_references_returns_line_hits(tmp_path, monkeypatch):
    _ws(tmp_path, monkeypatch)
    out = _run(CodeFindReferences, name="Widget")
    assert out["ok"] is True and out["count"] >= 2
    assert all("lineno" in r and "line" in r for r in out["references"])


def test_dependency_graph_keys_by_file(tmp_path, monkeypatch):
    _ws(tmp_path, monkeypatch)
    out = _run(CodeDependencyGraph, path=".")
    assert out["ok"] is True
    assert any("os" in mods for mods in out["graph"].values())


def test_syntax_error_is_captured_not_raised(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "broken.py").write_text("def (:\n", encoding="utf-8")
    out = _run(CodeIndex, path=".")
    assert out["ok"] is True
    assert any(e["type"] == "syntax_error" for e in out["errors"])


def test_path_escape_is_blocked(tmp_path, monkeypatch):
    _ws(tmp_path, monkeypatch)
    out = _run(CodeIndex, path="../../etc")
    assert out["ok"] is False
    assert "outside workspace" in (out["error"] or "")


def test_nul_byte_path_returns_clean_error(tmp_path, monkeypatch):
    _ws(tmp_path, monkeypatch)
    out = _run(CodeIndex, path="x\x00.py")
    assert out["ok"] is False and out["error"]
