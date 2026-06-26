"""Surgical file-editor primitives: str_replace / insert / write_lines. Epic E06."""
from __future__ import annotations

from core.schemas import ToolRequest
from toolbox.filesystem import FsInsert, FsStrReplace, FsWriteLines


def _run(tool, **args):
    return tool().execute(ToolRequest(name=tool.name, args=args))


def _seed(tmp_path, monkeypatch, name="f.py", text="a = 1\nb = 2\nc = 3\n"):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path / name


def test_str_replace_happy_path(tmp_path, monkeypatch):
    f = _seed(tmp_path, monkeypatch)
    out = _run(FsStrReplace, path="f.py", old_text="b = 2", new_text="b = 20")
    assert out["ok"] is True and out["replacements"] == 1
    assert "b = 20" in f.read_text(encoding="utf-8")


def test_str_replace_count_mismatch_refuses(tmp_path, monkeypatch):
    f = _seed(tmp_path, monkeypatch, text="x\nx\nx\n")
    out = _run(FsStrReplace, path="f.py", old_text="x", new_text="y", expected_replacements=1)
    assert out["ok"] is False
    assert out["found_replacements"] == 3
    assert f.read_text(encoding="utf-8") == "x\nx\nx\n"  # unchanged


def test_str_replace_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    out = _run(FsStrReplace, path="nope.py", old_text="a", new_text="b")
    assert out["ok"] is False and "does not exist" in out["error"]


def test_insert_before_line(tmp_path, monkeypatch):
    f = _seed(tmp_path, monkeypatch)
    out = _run(FsInsert, path="f.py", line=2, content="inserted = True")
    assert out["ok"] is True
    assert f.read_text(encoding="utf-8").splitlines()[1] == "inserted = True"


def test_insert_append_at_end(tmp_path, monkeypatch):
    f = _seed(tmp_path, monkeypatch)
    out = _run(FsInsert, path="f.py", line=4, content="d = 4")
    assert out["ok"] is True
    assert f.read_text(encoding="utf-8").splitlines()[-1] == "d = 4"


def test_insert_out_of_range_rejected(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    out = _run(FsInsert, path="f.py", line=99, content="z")
    assert out["ok"] is False and out["valid_range"] == [1, 4]


def test_write_lines_create(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    out = _run(FsWriteLines, path="new.py", lines=["import os", "print(os.getcwd())"])
    assert out["ok"] is True and out["lines_written"] == 2
    assert (tmp_path / "new.py").read_text(encoding="utf-8") == "import os\nprint(os.getcwd())\n"


def test_write_lines_overwrite_guard(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, name="exists.py")
    out = _run(FsWriteLines, path="exists.py", lines=["new"])
    assert out["ok"] is False and "overwrite is false" in out["error"]


def test_write_lines_rejects_non_string_items(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    out = _run(FsWriteLines, path="bad.py", lines=["ok", 123])
    assert out["ok"] is False and "must be a string" in out["error"]


def test_editor_path_escape_blocked(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    out = _run(FsStrReplace, path="../../etc/passwd", old_text="root", new_text="x")
    assert out["ok"] is False and "outside workspace" in out["error"]


def test_nul_byte_path_returns_clean_error(tmp_path, monkeypatch):
    # Path.resolve() rejects an embedded NUL with a bare ValueError — the tool must
    # surface a clean ok=False envelope, not crash.
    _seed(tmp_path, monkeypatch)
    out = _run(FsStrReplace, path="evil\x00.py", old_text="a", new_text="b")
    assert out["ok"] is False and out["error"]
