"""Adversarial checks for every local I/O and process-execution boundary."""
from __future__ import annotations

import sys

import pytest

import ui.server as ui_server
from core.bootstrap import build_kernel
from core.schemas import ToolRequest
from observability.event_log import EventLogger
from safety.policy import SafeToolPort, ToolPolicy, classify_terminal
from safety.sandbox import SandboxError, resolve_in_workspace
from toolbox.filesystem import FsList, FsRead, FsWrite
from toolbox.terminal import Terminal


TOOLBOX_CONFIG = {
    "features": {"toolbox": {"enabled": True, "module": "toolbox.feature"}}
}


@pytest.mark.audit
@pytest.mark.security
@pytest.mark.parametrize(
    "raw_path",
    ["../escape", "../../escape", "..\\escape", "C:/Windows/System32/drivers/etc/hosts"],
)
def test_workspace_resolver_rejects_every_lexical_escape(tmp_path, monkeypatch, raw_path):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path / "workspace"))
    with pytest.raises(SandboxError, match="outside workspace"):
        resolve_in_workspace(raw_path)


@pytest.mark.audit
@pytest.mark.security
def test_workspace_resolver_rejects_symlink_escape(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    link = workspace / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"host does not permit symlink creation: {exc}")
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(workspace))

    with pytest.raises(SandboxError, match="outside workspace"):
        resolve_in_workspace("link/secret.txt")


@pytest.mark.audit
@pytest.mark.security
@pytest.mark.parametrize("tool", [FsRead(), FsWrite(), FsList()])
def test_all_filesystem_tools_reject_escape(tmp_path, monkeypatch, tool):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path / "workspace"))
    request = ToolRequest(name=tool.name, args={"path": "../../outside", "content": "x"})

    result = tool.execute(request)

    assert result["ok"] is False
    assert "outside workspace" in result["error"]


@pytest.mark.audit
def test_filesystem_utf8_write_reports_physical_byte_count(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    content = "Tiếng Việt 🧪"

    result = FsWrite().execute(ToolRequest(name="fs_write", args={"path": "utf8.txt", "content": content}))

    assert result == {
        "ok": True,
        "path": str((tmp_path / "utf8.txt").resolve()),
        "bytes": len(content.encode("utf-8")),
    }
    assert (tmp_path / "utf8.txt").read_bytes() == content.encode("utf-8")


@pytest.mark.audit
def test_filesystem_read_non_utf8_returns_failure_envelope(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "binary.bin").write_bytes(b"\xff\xfe\x00")

    result = FsRead().execute(ToolRequest(name="fs_read", args={"path": "binary.bin"}))

    assert result["ok"] is False
    assert "UTF-8" in result["error"]


@pytest.mark.audit
@pytest.mark.security
@pytest.mark.parametrize(
    ("argv", "code"),
    [
        (["bash", "-c", "echo pwned"], "shell_exe"),
        (["cmd.exe", "/c", "echo pwned"], "shell_exe"),
        (["echo", "x|whoami"], "shell_token"),
        (["echo", "$(whoami)"], "shell_token"),
        (["rm", "-rf", "."], "destructive"),
        (["git", "reset", "--hard"], "git_mutation"),
        (["git.exe", "push"], "git_mutation"),
    ],
)
def test_terminal_policy_denies_high_risk_command_matrix(monkeypatch, argv, code):
    monkeypatch.delenv("AGENT_ALLOW_GIT_MUTATIONS", raising=False)
    decision = classify_terminal(argv)
    assert decision.allowed is False
    assert decision.code == code
    assert decision.risk == "blocked"


@pytest.mark.audit
@pytest.mark.security
def test_safe_tool_never_invokes_inner_executor_when_blocked():
    class Bomb:
        def execute(self, request):
            raise AssertionError("blocked executor was invoked")

    safe = SafeToolPort("terminal_run", Bomb(), ToolPolicy())
    result = safe.execute(ToolRequest(name="terminal_run", args={"argv": ["sh", "-c", "id"]}))

    assert result["ok"] is False
    assert result["policy_blocked"] is True
    assert result["policy_code"] == "shell_exe"


@pytest.mark.audit
@pytest.mark.security
def test_terminal_cannot_read_file_outside_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    secret = tmp_path / "outside-secret.txt"
    secret.write_text("TOP-SECRET", encoding="utf-8")
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(workspace))
    program = f"from pathlib import Path\nprint(Path({str(secret)!r}).read_text())"

    result = Terminal().execute(
        ToolRequest(name="terminal_run", args={"argv": [sys.executable, "-c", program]})
    )

    assert result["ok"] is False
    assert "TOP-SECRET" not in result.get("stdout", "")


@pytest.mark.audit
@pytest.mark.security
@pytest.mark.parametrize("run_id", ["../escape", "..\\escape", "nested/../../escape"])
def test_event_logger_rejects_path_like_run_ids(run_id):
    with pytest.raises(ValueError, match="run_id"):
        EventLogger(run_id=run_id)


@pytest.mark.audit
@pytest.mark.security
@pytest.mark.parametrize(
    "name",
    [".env", ".ENV", ".env.local", "id_rsa", "private.pem", "signing.KEY", "cert.p12"],
)
def test_ui_file_preview_blocks_sensitive_names_and_suffixes(tmp_path, monkeypatch, name):
    monkeypatch.setattr(ui_server, "workspace_dir", lambda: tmp_path)
    (tmp_path / name).write_text("secret", encoding="utf-8")
    with pytest.raises(PermissionError, match="sensitive"):
        ui_server.read_file_snapshot("workspace", name)


@pytest.mark.audit
@pytest.mark.security
def test_ui_file_preview_blocks_traversal_symlink_binary_non_utf8_and_oversize(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    monkeypatch.setattr(ui_server, "workspace_dir", lambda: root)

    with pytest.raises(ValueError, match="outside"):
        ui_server.read_file_snapshot("workspace", "../outside.txt")
    (root / "nul.bin").write_bytes(b"safe-prefix\x00payload")
    with pytest.raises(ValueError, match="binary"):
        ui_server.read_file_snapshot("workspace", "nul.bin")
    (root / "bad.txt").write_bytes(b"\xff\xfe")
    with pytest.raises(ValueError, match="UTF-8"):
        ui_server.read_file_snapshot("workspace", "bad.txt")
    (root / "large.txt").write_bytes(b"x" * (ui_server.MAX_FILE_BYTES + 1))
    with pytest.raises(ValueError, match="preview limit"):
        ui_server.read_file_snapshot("workspace", "large.txt")


@pytest.mark.audit
def test_builtin_tool_descriptors_match_retry_and_risk_semantics():
    kernel = build_kernel(TOOLBOX_CONFIG)
    expected = {
        "fs_read": ("read", True, "low"),
        "fs_list": ("read", True, "low"),
        "fs_write": ("effect", False, "medium"),
        "terminal_run": ("effect", False, "high"),
    }

    actual = {}
    for name in expected:
        descriptor = kernel.registry.resolve_tool(name).descriptor
        actual[name] = (descriptor.kind, descriptor.idempotent, descriptor.risk)

    assert actual == expected
