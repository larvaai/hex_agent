import pytest

from safety.policy import ToolPolicy, classify_terminal
from safety.sandbox import SandboxError, resolve_in_workspace


def test_sandbox_resolves_inside(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    p = resolve_in_workspace("a/b.txt")
    assert str(p).startswith(str(tmp_path.resolve()))


def test_sandbox_escape_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    with pytest.raises(SandboxError):
        resolve_in_workspace("../../etc/passwd")


def test_policy_blocks_shell_exe():
    d = classify_terminal(["bash", "-c", "echo hi"])
    assert d.allowed is False and d.code == "shell_exe"


def test_policy_blocks_redirect_token():
    assert classify_terminal(["python3", "-c", "x", ">", "f"]).allowed is False


def test_policy_allows_python_argv():
    assert classify_terminal(["python3", "-c", "print(1)"]).allowed is True


def test_policy_blocks_git_mutation(monkeypatch):
    monkeypatch.delenv("AGENT_ALLOW_GIT_MUTATIONS", raising=False)
    d = ToolPolicy().check("git_commit", {})
    assert d.allowed is False and d.code == "git_mutation"
