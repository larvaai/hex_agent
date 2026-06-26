"""Unit-level FsSandbox + Tools: round-trips, escape blocking, never-raise ToolResults."""
import sys

import pytest

from dragzero import SandboxError, ToolResult
from dragzero.adapters.tools_fs import (
    FsSandbox,
    ListDirTool,
    ReadFileTool,
    RunCommandTool,
    WriteFileTool,
    build_fs_tools,
    default_tool_catalog,
)


# --- FsSandbox directly --------------------------------------------------

def test_sandbox_write_read_roundtrip(tmp_path):
    sb = FsSandbox(tmp_path)
    n = sb.write("a.txt", "hello")
    assert n == 5
    assert sb.read("a.txt") == "hello"
    assert (tmp_path / "a.txt").read_text() == "hello"


def test_sandbox_listdir_sorted_names(tmp_path):
    sb = FsSandbox(tmp_path)
    sb.write("b.txt", "x")
    sb.write("a.txt", "y")
    assert sb.listdir() == ["a.txt", "b.txt"]


def test_sandbox_write_creates_parent_dirs(tmp_path):
    sb = FsSandbox(tmp_path)
    sb.write("sub/deep/c.txt", "z")
    assert (tmp_path / "sub" / "deep" / "c.txt").read_text() == "z"


def test_resolve_escape_raises_sandbox_error(tmp_path):
    sb = FsSandbox(tmp_path)
    with pytest.raises(SandboxError):
        sb.resolve("../x")


def test_resolve_root_itself_is_allowed(tmp_path):
    sb = FsSandbox(tmp_path)
    assert sb.resolve(".") == sb.root


# --- ReadFileTool --------------------------------------------------------

def test_read_tool_ok_for_existing_file(tmp_path):
    (tmp_path / "f.txt").write_text("content")
    res = ReadFileTool().run({"path": "f.txt"}, FsSandbox(tmp_path))
    assert isinstance(res, ToolResult)
    assert res.ok is True
    assert res.output == "content"


def test_read_tool_missing_file_returns_not_ok(tmp_path):
    res = ReadFileTool().run({"path": "nope.txt"}, FsSandbox(tmp_path))
    assert isinstance(res, ToolResult)
    assert res.ok is False
    assert res.error  # carries a message, never raises


def test_read_tool_escape_path_blocked(tmp_path):
    res = ReadFileTool().run({"path": "../../etc/passwd"}, FsSandbox(tmp_path))
    assert res.ok is False
    assert "escapes sandbox" in res.error


# --- WriteFileTool -------------------------------------------------------

def test_write_tool_writes_and_reports_bytes(tmp_path):
    sb = FsSandbox(tmp_path)
    res = WriteFileTool().run({"path": "w.txt", "content": "abcd"}, sb)
    assert isinstance(res, ToolResult)
    assert res.ok is True
    assert res.output == "wrote 4 bytes to w.txt"
    assert (tmp_path / "w.txt").read_text() == "abcd"


def test_write_tool_escape_path_blocked(tmp_path):
    res = WriteFileTool().run({"path": "../evil.txt", "content": "x"}, FsSandbox(tmp_path))
    assert res.ok is False
    assert "escapes sandbox" in res.error


# --- ListDirTool ---------------------------------------------------------

def test_list_dir_tool_lists_names(tmp_path):
    sb = FsSandbox(tmp_path)
    sb.write("one.txt", "1")
    sb.write("two.txt", "2")
    res = ListDirTool().run({}, sb)
    assert isinstance(res, ToolResult)
    assert res.ok is True
    assert res.output == "one.txt\ntwo.txt"


# --- RunCommandTool ------------------------------------------------------

def test_run_command_missing_argv_not_ok(tmp_path):
    res = RunCommandTool().run({}, FsSandbox(tmp_path))
    assert isinstance(res, ToolResult)
    assert res.ok is False
    assert "non-empty 'argv'" in res.error


def test_run_command_empty_argv_not_ok(tmp_path):
    res = RunCommandTool().run({"argv": []}, FsSandbox(tmp_path))
    assert res.ok is False
    assert "non-empty 'argv'" in res.error


def test_run_command_benign_command_succeeds(tmp_path):
    argv = [sys.executable, "-c", "print('ok')"]
    res = RunCommandTool().run({"argv": argv}, FsSandbox(tmp_path))
    assert isinstance(res, ToolResult)
    assert res.ok is True
    assert "ok" in res.output


# --- catalog / registry builders ----------------------------------------

def test_default_catalog_excludes_run_command():
    cat = default_tool_catalog()
    assert set(cat) == {"read_file", "write_file", "list_dir"}
    assert "run_command" not in cat


def test_default_catalog_includes_run_command_when_asked():
    cat = default_tool_catalog(include_run_command=True)
    assert "run_command" in cat
    assert isinstance(cat["run_command"], RunCommandTool)


def test_build_fs_tools_count():
    assert len(build_fs_tools()) == 3
    assert len(build_fs_tools(include_run_command=True)) == 4
