"""Every new toolbox capability resolves through the kernel with the right descriptor. Epic E06."""
from __future__ import annotations

import pytest

from core.bootstrap import build_kernel

TOOLBOX = {"features": {"toolbox": {"enabled": True, "module": "toolbox.feature"}}}

NEW_TOOLS = [
    "fs_str_replace",
    "fs_insert",
    "fs_write_lines",
    "code_index",
    "code_find_symbol",
    "code_find_references",
    "code_dependency_graph",
    "lint_compile",
    "ruff_check",
    "pytest_run",
]


@pytest.fixture
def kernel(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    return build_kernel(TOOLBOX)


@pytest.mark.parametrize("name", NEW_TOOLS)
def test_new_tool_is_registered_not_null(kernel, name):
    assert kernel.registry.has_tool(name)
    resolution = kernel.registry.resolve_tool(name)
    assert resolution.executor.__class__.__name__ != "NullToolPort"
    assert resolution.feature == "toolbox"


def test_read_tools_are_idempotent_low_risk(kernel):
    for name in ("code_index", "code_find_symbol", "code_find_references", "code_dependency_graph"):
        d = kernel.registry.resolve_tool(name).descriptor
        assert d.kind == "read" and d.idempotent is True and d.risk == "low"


def test_editor_tools_are_non_idempotent_effects(kernel):
    for name in ("fs_str_replace", "fs_insert", "fs_write_lines"):
        d = kernel.registry.resolve_tool(name).descriptor
        assert d.kind == "effect" and d.idempotent is False


def test_new_tools_executable_through_kernel(kernel, tmp_path):
    (tmp_path / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    indexed = kernel.execute_tool("code_index", {"path": "."})
    assert indexed["ok"] is True
    assert any(s["name"] == "f" for s in indexed["data"]["symbols"])
    compiled = kernel.execute_tool("lint_compile", {"path": "."})
    assert compiled["ok"] is True
