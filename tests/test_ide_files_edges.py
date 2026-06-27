"""L1 backend-integration — files.py edge guards (binary / oversize / ignored-dir / sensitive /
symlink / agent-runs hiding). No model, no browser; calls the real ``ui.ide.files`` ops.

These pin the edges the load-bearing file surface depends on but that no existing test covered.
Each guard is exercised through the *real* door it actually defends, not a paraphrase of it:

- binary editing is disabled at the **read/decode** boundary (files.py:180-181) — the editor's open
  step. (write_file has no NUL guard; a NUL written via the JSON API is write-once-unreadable. That
  is a minor product gap, LOGGED per plan DEC-T4, not patched here — this is a test-only round.)
- ignored-dirs / var/agent_runs hiding is a **project-scope** rule (files.py:89-91,112-113); the
  agent's workspace scope is its own small sandbox and is shown whole.
"""
from __future__ import annotations

import os

import pytest

import ui.ide.files as files


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    return ws


@pytest.fixture()
def project(tmp_path, monkeypatch):
    """A throwaway repo root so project-scope walks a tiny tree, never the real checkout."""
    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.setattr(files, "PROJECT_DIR", proj)
    return proj


# ── binary / oversize (files.py:180-181, :216) ───────────────────────────────────
def test_write_binary_rejected(workspace):
    """The editor refuses to open a binary file — a NUL in the first 4 KiB trips _decode
    (files.py:180-181). Invert: dropping the NUL guard would let read_file return mojibake instead
    of raising, so this assertion bites the guard, not jsdom."""
    (workspace / "bin.dat").write_bytes(b"\x00\x01\x02BINARY")
    with pytest.raises(files.FileOpError, match="binary"):
        files.read_file("workspace", "bin.dat")


def test_write_oversized_rejected(workspace):
    too_big = "a" * (files.MAX_FILE_BYTES + 1)
    with pytest.raises(files.FileOpError, match="exceeds edit limit"):
        files.write_file("workspace", "huge.txt", too_big)


# ── tree hides ignored dirs + agent_runs (project scope) ─────────────────────────
def test_tree_hides_ignored_dirs(project):
    (project / ".git").mkdir()
    (project / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (project / "node_modules").mkdir()
    (project / "node_modules" / "x.js").write_text("//\n", encoding="utf-8")
    (project / "keep.py").write_text("x = 1\n", encoding="utf-8")

    names = _top_level_names(files.tree_snapshot("project")["tree"])
    assert "keep.py" in names
    assert ".git" not in names and "node_modules" not in names


def test_project_scope_hides_agent_runs(project):
    runs = project / "var" / "agent_runs" / "run1"
    runs.mkdir(parents=True)
    (runs / "checkpoint.json").write_text("{}", encoding="utf-8")
    (project / "var").mkdir(exist_ok=True)
    (project / "var" / "workspace").mkdir(exist_ok=True)
    (project / "var" / "workspace" / "keep.py").write_text("x = 1\n", encoding="utf-8")

    var_node = _find_child(files.tree_snapshot("project")["tree"], "var")
    assert var_node is not None
    assert "agent_runs" not in _child_names(var_node)
    # and the path is refused on a direct read, not merely hidden from the listing
    with pytest.raises(files.FileOpError, match="hidden"):
        files.read_file("project", "var/agent_runs/run1/checkpoint.json")


# ── sensitive create / rename / delete (files.py:225-267) ────────────────────────
@pytest.mark.security
@pytest.mark.parametrize("name", [".env", "id_rsa", "secret.pem"])
def test_sensitive_crud_blocked(workspace, name):
    # create a sensitive name → refused
    with pytest.raises(files.FileOpError, match="sensitive"):
        files.create_path("workspace", name, "file")
    # rename a normal file *into* a sensitive name → refused
    files.create_path("workspace", "ok.txt", "file")
    with pytest.raises(files.FileOpError, match="sensitive"):
        files.rename_path("workspace", "ok.txt", name)
    # delete an existing sensitive file → refused (placed on disk out-of-band)
    (workspace / name).write_text("SECRET=1", encoding="utf-8")
    with pytest.raises(files.FileOpError, match="sensitive"):
        files.delete_path("workspace", name)


# ── symlink not followed (files.py:145-147 + jail) ───────────────────────────────
@pytest.mark.security
def test_symlink_not_followed(workspace, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "passwd").write_text("root:x:0:0\n", encoding="utf-8")
    os.symlink(outside, workspace / "link")

    # the tree marks it a symlink and does NOT descend into the foreign dir
    link_node = _find_child(files.tree_snapshot("workspace")["tree"], "link")
    assert link_node is not None and link_node["type"] == "symlink"
    assert "children" not in link_node

    # resolving through the symlink escapes the jail → refused
    with pytest.raises(files.FileOpError, match="outside root"):
        files.read_file("workspace", "link/passwd")


# ── tree helpers ──────────────────────────────────────────────────────────────────
def _top_level_names(tree: dict) -> set[str]:
    return _child_names(tree)


def _child_names(node: dict) -> set[str]:
    return {c["name"] for c in node.get("children", [])}


def _find_child(node: dict, name: str) -> dict | None:
    for child in node.get("children", []):
        if child["name"] == name:
            return child
    return None
