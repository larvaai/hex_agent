from core.bootstrap import build_kernel

TOOLBOX = {"features": {"toolbox": {"enabled": True, "module": "toolbox.feature"}}}


def _kernel(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    return build_kernel(TOOLBOX)


def test_fs_write_then_read(tmp_path, monkeypatch):
    k = _kernel(tmp_path, monkeypatch)
    w = k.execute_tool("fs_write", {"path": "d/a.txt", "content": "hi"})
    assert w["ok"] is True
    r = k.execute_tool("fs_read", {"path": "d/a.txt"})
    assert r["ok"] is True and r["data"]["content"] == "hi"


def test_fs_read_escape_blocked(tmp_path, monkeypatch):
    k = _kernel(tmp_path, monkeypatch)
    r = k.execute_tool("fs_read", {"path": "../../etc/passwd"})
    assert r["ok"] is False
    assert "outside workspace" in (r["error"] or "")


def test_terminal_argv_runs(tmp_path, monkeypatch):
    k = _kernel(tmp_path, monkeypatch)
    r = k.execute_tool("terminal_run", {"argv": ["python3", "-c", "print('hi')"]})
    assert r["ok"] is True
    assert "hi" in r["data"]["stdout"]


def test_terminal_shell_blocked_by_policy(tmp_path, monkeypatch):
    k = _kernel(tmp_path, monkeypatch)
    r = k.execute_tool("terminal_run", {"argv": ["bash", "-c", "echo hi"]})
    assert r["ok"] is False
    assert r["data"].get("policy_blocked") is True
