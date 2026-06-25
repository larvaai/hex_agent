"""Rigor for the sandboxed toolbox: fs jail escapes, no-shell argv exec, timeout kill, policy gate.

Complements tests/test_toolbox.py (happy path), tests/test_safety.py (resolver/policy units) and
tests_audit/test_security_boundaries.py (lexical-escape matrix). Here we pin the *tool-level* error
branches that those files don't drive — the missing lines in toolbox/terminal.py (18, 40-43) and
toolbox/filesystem.py (19, 50-54) — plus the security invariants the assignment calls for:
no shell metacharacter expansion, timeout-kills-and-reports, workspace cwd, round-trip inside the jail,
and adversarial paths (NUL byte, very long path, symlink, absolute, traversal). Real robustness gaps
found in the jail are exposed via strict-less xfail, never asserted false.
"""
from __future__ import annotations

import os
import shutil
import sys
import time
import uuid

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core.bootstrap import build_kernel
from core.schemas import ToolRequest
from safety.sandbox import SandboxError, resolve_in_workspace, workspace_dir
from toolbox.feature import FEATURE, install
from toolbox.filesystem import FsList, FsRead, FsWrite
from toolbox.terminal import Terminal

TOOLBOX_CONFIG = {"features": {"toolbox": {"enabled": True, "module": "toolbox.feature"}}}


def _req(name: str, **args) -> ToolRequest:
    return ToolRequest(name=name, args=args)


def _echo_bin() -> str:
    """A real echo binary (not a shell builtin) so we can prove argv runs WITHOUT a shell."""
    found = shutil.which("echo")
    if found is None or not os.path.isabs(found):
        # POSIX hosts ship /bin/echo; skip rather than silently weaken the no-expansion proof.
        if os.path.exists("/bin/echo"):
            return "/bin/echo"
        pytest.skip("no standalone echo binary available to prove no-shell expansion")
    return found


# --------------------------------------------------------------------------------------
# terminal_run — argv validation (terminal.py line 18) and policy gate
# --------------------------------------------------------------------------------------


@pytest.mark.audit
@pytest.mark.security
@pytest.mark.parametrize("argv", [[], None, "echo hi", 42, {"a": 1}, ()])
def test_terminal_rejects_non_list_or_empty_argv(argv):
    """terminal.py:18 — the tool itself rejects a non-list/empty argv before touching subprocess."""
    result = Terminal().execute(_req("terminal_run", argv=argv))
    assert result == {"ok": False, "error": "argv must be a non-empty list"}


@pytest.mark.audit
@pytest.mark.security
def test_terminal_missing_argv_key_rejected():
    """No argv key at all -> args.get returns None -> same guarded failure, no crash."""
    assert Terminal().execute(_req("terminal_run")) == {"ok": False, "error": "argv must be a non-empty list"}


@pytest.mark.audit
@pytest.mark.security
@pytest.mark.parametrize(
    ("argv", "code"),
    [
        (["bash", "-c", "echo pwned"], "shell_exe"),
        (["sh", "id"], "shell_exe"),
        (["echo", "a|b"], "shell_token"),
        (["echo", "$(whoami)"], "shell_token"),
        (["rm", "-rf", "x"], "destructive"),
        (["dd", "if=/dev/zero"], "destructive"),
        (["git", "push"], "git_mutation"),
    ],
)
def test_terminal_policy_gate_blocks_dangerous_commands_in_the_tool(monkeypatch, argv, code):
    """Defense in depth: Terminal.execute runs classify_terminal itself, so a *direct* call
    (bypassing SafeToolPort) is still blocked. The inner subprocess must never run."""
    monkeypatch.delenv("AGENT_ALLOW_GIT_MUTATIONS", raising=False)
    result = Terminal().execute(_req("terminal_run", argv=argv))
    assert result["ok"] is False
    assert result["policy_blocked"] is True
    assert result["policy_code"] == code
    # A blocked command must not have produced process output.
    assert "stdout" not in result and "returncode" not in result


# --------------------------------------------------------------------------------------
# terminal_run — NO shell: metacharacters/env vars are passed literally, never expanded
# --------------------------------------------------------------------------------------


@pytest.mark.audit
@pytest.mark.security
def test_terminal_does_not_expand_env_var_argument():
    """argv ['echo', '$HOME'] must print the LITERAL '$HOME' — proof there is no shell layer."""
    echo = _echo_bin()
    result = Terminal().execute(_req("terminal_run", argv=[echo, "$HOME"]))
    assert result["ok"] is True
    assert result["stdout"].strip() == "$HOME"


@pytest.mark.audit
@pytest.mark.security
def test_terminal_does_not_glob_or_expand_metacharacters(tmp_path, monkeypatch):
    """A '*' argument is delivered verbatim, not expanded against the cwd's files."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "real_file.txt").write_text("x", encoding="utf-8")
    echo = _echo_bin()
    result = Terminal().execute(_req("terminal_run", argv=[echo, "*.txt"]))
    assert result["ok"] is True
    # If a shell were involved, '*.txt' would expand to 'real_file.txt'.
    assert result["stdout"].strip() == "*.txt"


@pytest.mark.audit
@pytest.mark.security
def test_terminal_argv_element_with_spaces_is_one_argument():
    """A single argv element 'a b c' stays ONE argument (no word splitting => no shell)."""
    result = Terminal().execute(
        _req("terminal_run", argv=[sys.executable, "-c", "import sys\nprint(len(sys.argv) - 1)", "a b c"])
    )
    assert result["ok"] is True
    assert result["stdout"].strip() == "1"


# --------------------------------------------------------------------------------------
# terminal_run — cwd is the workspace; timeout kills and reports; missing binary reported
# --------------------------------------------------------------------------------------


@pytest.mark.audit
@pytest.mark.security
def test_terminal_runs_inside_workspace_cwd(tmp_path, monkeypatch):
    """The child process is launched with cwd == workspace_dir(), and the dir is created."""
    ws = tmp_path / "fresh_ws"  # does not exist yet -> exercises mkdir(parents, exist_ok)
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    assert not ws.exists()
    result = Terminal().execute(
        _req("terminal_run", argv=[sys.executable, "-c", "import os\nprint(os.getcwd())"])
    )
    assert result["ok"] is True
    assert result["stdout"].strip() == str(workspace_dir())
    assert ws.exists()  # mkdir side effect (terminal.py:31)


@pytest.mark.audit
@pytest.mark.security
def test_terminal_kills_and_reports_command_that_outlives_timeout(tmp_path, monkeypatch):
    """terminal.py:42-43 — a sleep longer than the timeout is killed; a clean failure is reported,
    and we return well before the sleep would have finished (process really was terminated)."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    start = time.monotonic()
    result = Terminal().execute(
        _req("terminal_run", argv=[sys.executable, "-c", "import time\ntime.sleep(30)"], timeout=1)
    )
    elapsed = time.monotonic() - start
    assert result == {"ok": False, "error": "timeout after 1s"}
    assert elapsed < 15  # generous budget; the 30s sleep was cut short, not awaited


@pytest.mark.audit
def test_terminal_timeout_is_clamped_to_minimum_one_second():
    """timeout=0/negative is clamped up to 1 (min(max(int(t),1),30)); the report echoes the clamp."""
    result = Terminal().execute(
        _req("terminal_run", argv=[sys.executable, "-c", "import time\ntime.sleep(30)"], timeout=0)
    )
    assert result == {"ok": False, "error": "timeout after 1s"}


@pytest.mark.audit
def test_terminal_timeout_is_clamped_to_maximum_thirty():
    """A timeout above the 30s ceiling is clamped down; a fast command still succeeds promptly."""
    result = Terminal().execute(
        _req("terminal_run", argv=[sys.executable, "-c", "print('ok')"], timeout=10_000)
    )
    assert result["ok"] is True and result["stdout"].strip() == "ok"


@pytest.mark.audit
@pytest.mark.security
def test_terminal_reports_missing_binary_without_crashing():
    """terminal.py:40-41 — FileNotFoundError is converted to a clean failure envelope."""
    result = Terminal().execute(_req("terminal_run", argv=["definitely_no_such_binary_zxq_999"]))
    assert result["ok"] is False
    assert result["error"].startswith("command not found:")


@pytest.mark.audit
def test_terminal_nonzero_exit_is_reported_as_failure_with_streams():
    """A program that exits non-zero -> ok False, returncode preserved, stderr captured."""
    result = Terminal().execute(
        _req("terminal_run", argv=[sys.executable, "-c", "import sys\nsys.stderr.write('boom')\nsys.exit(3)"])
    )
    assert result["ok"] is False
    assert result["returncode"] == 3
    assert "boom" in result["stderr"]


@pytest.mark.audit
def test_terminal_argv_elements_are_stringified():
    """Non-str argv elements are coerced via str() (terminal.py:34) — an int arg prints back."""
    result = Terminal().execute(
        _req("terminal_run", argv=[sys.executable, "-c", "import sys\nprint(sys.argv[1])", 12345])
    )
    assert result["ok"] is True and result["stdout"].strip() == "12345"


# --------------------------------------------------------------------------------------
# terminal_run — cannot read files outside the workspace (argv path-escape policy)
# --------------------------------------------------------------------------------------


@pytest.mark.audit
@pytest.mark.security
def test_terminal_argv_absolute_path_outside_workspace_is_blocked(tmp_path, monkeypatch):
    """An inline program referencing an absolute path outside the jail is refused by policy,
    so a secret outside the workspace can never be exfiltrated through terminal_run."""
    ws = tmp_path / "ws"
    ws.mkdir()
    secret = tmp_path / "outside_secret.txt"
    secret.write_text("TOP-SECRET-XYZ", encoding="utf-8")
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    program = f"print(open({str(secret)!r}).read())"
    result = Terminal().execute(_req("terminal_run", argv=[sys.executable, "-c", program]))
    assert result["ok"] is False
    assert result["policy_blocked"] is True
    assert result["policy_code"] == "path_escape"
    assert "TOP-SECRET-XYZ" not in (result.get("stdout") or "")


# --------------------------------------------------------------------------------------
# filesystem — round-trip inside the jail and read-error branches
# --------------------------------------------------------------------------------------


@pytest.mark.audit
@pytest.mark.security
def test_fs_write_then_read_round_trip_inside_jail(tmp_path, monkeypatch):
    """fs_write under a nested relative path then fs_read returns the same content (byte count exact)."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    content = "Tiếng Việt 🧪 line2"
    w = FsWrite().execute(_req("fs_write", path="nested/dir/file.txt", content=content))
    assert w["ok"] is True
    assert w["bytes"] == len(content.encode("utf-8"))
    r = FsRead().execute(_req("fs_read", path="nested/dir/file.txt"))
    assert r["ok"] is True and r["content"] == content
    # The resolved paths agree and live under the workspace.
    assert r["path"] == w["path"]
    assert r["path"].startswith(str(tmp_path.resolve()))


@pytest.mark.audit
@pytest.mark.security
@pytest.mark.xfail(
    reason="BUG: fs_read uses Path.read_text() with default universal-newline translation, so a "
    "carriage return is silently rewritten to '\\n' on read. The bytes on disk are faithful "
    "(fs_write preserves '\\r'), but the fs_write->fs_read round-trip CORRUPTS any content "
    "containing CR/CRLF. fs_read should pass newline='' to preserve bytes.",
    strict=False,
)
@pytest.mark.parametrize("content", ["\r", "\r\n", "a\rb", "line1\r\nline2"])
def test_fs_read_round_trip_preserves_carriage_returns(tmp_path, monkeypatch, content):
    """Round-trip must return EXACTLY what was written; CR-bearing content currently does not."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    FsWrite().execute(_req("fs_write", path="cr.txt", content=content))
    # On-disk bytes ARE faithful — the corruption is on the read side only.
    assert (tmp_path / "cr.txt").read_bytes() == content.encode("utf-8")
    r = FsRead().execute(_req("fs_read", path="cr.txt"))
    assert r["ok"] is True
    assert r["content"] == content  # currently fails: '\r' comes back as '\n'


@pytest.mark.audit
def test_fs_read_on_directory_is_not_a_file(tmp_path, monkeypatch):
    """filesystem.py:19 — reading a path that resolves to a directory returns 'Not a file'."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "adir").mkdir()
    result = FsRead().execute(_req("fs_read", path="adir"))
    assert result["ok"] is False
    assert result["error"].startswith("Not a file:")


@pytest.mark.audit
def test_fs_read_missing_file_is_not_a_file(tmp_path, monkeypatch):
    """A non-existent path also yields 'Not a file' (no traceback leak)."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    result = FsRead().execute(_req("fs_read", path="ghost.txt"))
    assert result["ok"] is False and result["error"].startswith("Not a file:")


@pytest.mark.audit
def test_fs_read_non_utf8_file_reports_decode_failure(tmp_path, monkeypatch):
    """filesystem.py:22-23 — a binary file surfaces a clean UTF-8 failure, not a UnicodeDecodeError."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "bin.dat").write_bytes(b"\xff\xfe\x00\x01")
    result = FsRead().execute(_req("fs_read", path="bin.dat"))
    assert result["ok"] is False and "UTF-8" in result["error"]


# --------------------------------------------------------------------------------------
# filesystem — fs_list branches (missing / file / dir)  filesystem.py:50-54
# --------------------------------------------------------------------------------------


@pytest.mark.audit
def test_fs_list_missing_path_returns_empty(tmp_path, monkeypatch):
    """filesystem.py:50-51 — listing a non-existent path is an empty, successful result."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    assert FsList().execute(_req("fs_list", path="nope")) == {"ok": True, "entries": []}


@pytest.mark.audit
def test_fs_list_on_file_returns_just_its_name(tmp_path, monkeypatch):
    """filesystem.py:52-53 — listing a file yields a single-entry list of its basename."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "solo.txt").write_text("x", encoding="utf-8")
    assert FsList().execute(_req("fs_list", path="solo.txt")) == {"ok": True, "entries": ["solo.txt"]}


@pytest.mark.audit
def test_fs_list_on_directory_is_sorted(tmp_path, monkeypatch):
    """filesystem.py:54 — directory entries come back sorted (deterministic ordering)."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    for name in ("c.txt", "a.txt", "b.txt"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    (tmp_path / "zdir").mkdir()
    result = FsList().execute(_req("fs_list", path="."))
    assert result["ok"] is True
    assert result["entries"] == sorted(result["entries"]) == ["a.txt", "b.txt", "c.txt", "zdir"]


@pytest.mark.audit
def test_fs_list_default_path_is_workspace_root(tmp_path, monkeypatch):
    """No path arg defaults to '.' => the workspace root, not the cwd."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "only.txt").write_text("x", encoding="utf-8")
    assert FsList().execute(_req("fs_list")) == {"ok": True, "entries": ["only.txt"]}


# --------------------------------------------------------------------------------------
# filesystem — every tool rejects path escapes (traversal / absolute / symlink / windows)
# --------------------------------------------------------------------------------------


@pytest.mark.audit
@pytest.mark.security
@pytest.mark.parametrize("tool", [FsRead(), FsWrite(), FsList()])
@pytest.mark.parametrize(
    "bad_path",
    [
        "../escape",
        "../../../../etc/passwd",
        "/etc/passwd",
        "/absolute/outside",
        "..\\windows_escape",
        "C:/Windows/System32",
        "nested/../../escape",
    ],
)
def test_filesystem_tools_reject_escape_paths(tmp_path, monkeypatch, tool, bad_path):
    """Each fs tool turns a SandboxError into a clean 'outside workspace' failure envelope."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path / "ws"))
    result = tool.execute(_req(tool.name, path=bad_path, content="x"))
    assert result["ok"] is False
    assert "outside workspace" in result["error"]


@pytest.mark.audit
@pytest.mark.security
@pytest.mark.parametrize("tool_name", ["fs_read", "fs_write", "fs_list"])
def test_filesystem_symlink_pointing_outside_is_blocked(tmp_path, monkeypatch, tool_name):
    """A symlink inside the jail that targets an outside dir cannot be used to escape:
    resolve() follows the link, and the resolved real path fails the is_relative_to check."""
    ws = tmp_path / "ws"
    outside = tmp_path / "outside"
    ws.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("SENSITIVE", encoding="utf-8")
    try:
        (ws / "link").symlink_to(outside, target_is_directory=True)
    except OSError as exc:  # pragma: no cover - host without symlink perms
        pytest.skip(f"host does not permit symlink creation: {exc}")
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    tool = {"fs_read": FsRead(), "fs_write": FsWrite(), "fs_list": FsList()}[tool_name]
    result = tool.execute(_req(tool_name, path="link/secret.txt", content="x"))
    assert result["ok"] is False
    assert "outside workspace" in result["error"]
    # And the sensitive content never leaked through the read path.
    assert "SENSITIVE" not in str(result.get("content", ""))


@pytest.mark.audit
@pytest.mark.security
def test_fs_write_cannot_create_outside_workspace_via_symlinked_parent(tmp_path, monkeypatch):
    """Belt-and-braces: a blocked fs_write must not have created any file outside the jail."""
    ws = tmp_path / "ws"
    outside = tmp_path / "outside"
    ws.mkdir()
    outside.mkdir()
    try:
        (ws / "link").symlink_to(outside, target_is_directory=True)
    except OSError as exc:  # pragma: no cover
        pytest.skip(f"host does not permit symlink creation: {exc}")
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    result = FsWrite().execute(_req("fs_write", path="link/created.txt", content="evil"))
    assert result["ok"] is False
    assert not (outside / "created.txt").exists()


# --------------------------------------------------------------------------------------
# Adversarial path inputs — NUL byte (REAL BUG) and very long path
# --------------------------------------------------------------------------------------


@pytest.mark.audit
@pytest.mark.security
@pytest.mark.xfail(
    reason="BUG: a NUL-byte path makes Path.resolve() raise bare ValueError in resolve_in_workspace; "
    "the fs tools only catch SandboxError, so the embedded-null ValueError escapes as an uncaught "
    "crash instead of a clean 'outside workspace' / failure envelope.",
    strict=False,
)
@pytest.mark.parametrize("tool", [FsRead(), FsWrite(), FsList()])
def test_filesystem_nul_byte_path_returns_failure_envelope_not_crash(tmp_path, monkeypatch, tool):
    """A NUL byte must be rejected as a clean failure, never propagate as an uncaught exception."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    result = tool.execute(_req(tool.name, path="evil\x00.txt", content="x"))
    assert result["ok"] is False  # would crash with ValueError before reaching here


@pytest.mark.audit
@pytest.mark.security
def test_resolver_nul_byte_documents_uncaught_valueerror(tmp_path, monkeypatch):
    """Honest pin of the gap at the source: resolve_in_workspace raises a *bare* ValueError (not the
    SandboxError subclass the tools catch) for an embedded NUL — that is exactly why the tools crash."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    with pytest.raises(ValueError) as exc:
        resolve_in_workspace("evil\x00.txt")
    # It is NOT a SandboxError, so `except SandboxError` in the tools does not catch it.
    assert not isinstance(exc.value, SandboxError)
    assert "null" in str(exc.value).lower()


@pytest.mark.audit
@pytest.mark.security
def test_fs_read_and_list_handle_very_long_path_without_crashing(tmp_path, monkeypatch):
    """A pathologically long single component must not crash read/list; it simply isn't a file."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    long_name = "a" * 5000
    assert FsRead().execute(_req("fs_read", path=long_name))["ok"] is False
    assert FsList().execute(_req("fs_list", path=long_name)) == {"ok": True, "entries": []}


@pytest.mark.audit
@pytest.mark.security
@pytest.mark.xfail(
    reason="ROBUSTNESS GAP: fs_write of a >NAME_MAX single component raises an uncaught "
    "OSError('File name too long') from write_text instead of returning a failure envelope. "
    "Stays inside the jail, so not a security escape, but a crash rather than a clean error.",
    strict=False,
)
def test_fs_write_very_long_name_returns_failure_envelope_not_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    result = FsWrite().execute(_req("fs_write", path="b" * 5000, content="x"))
    assert result["ok"] is False  # currently raises OSError before this


# --------------------------------------------------------------------------------------
# Property: any relative path that stays inside the jail round-trips; coercion is total
# --------------------------------------------------------------------------------------


@pytest.mark.audit
@pytest.mark.property
@given(
    rel=st.lists(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=8),
        min_size=1,
        max_size=4,
    ),
    # Exclude '\r': fs_read's universal-newline translation corrupts CR on round-trip
    # (covered honestly by the dedicated xfail below); here we pin ordinary-text fidelity.
    content=st.text(alphabet=st.characters(blacklist_characters="\r"), max_size=64),
)
def test_property_inside_jail_paths_round_trip(tmp_path, monkeypatch, rel, content):
    """For any safe relative path, fs_write then fs_read returns identical content and resolves
    strictly inside the workspace. Each Hypothesis example gets a FRESH workspace so a component
    generated as a file in one example never collides with the same name as a dir in the next."""
    ws = tmp_path / ("prop_ws_" + uuid.uuid4().hex)
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    rel_path = "/".join(rel)
    w = FsWrite().execute(_req("fs_write", path=rel_path, content=content))
    assert w["ok"] is True
    assert w["path"].startswith(str(ws.resolve()))
    r = FsRead().execute(_req("fs_read", path=rel_path))
    assert r["ok"] is True and r["content"] == content


@pytest.mark.audit
@pytest.mark.property
@given(prefix=st.sampled_from(["../", "../../", "..\\", "/", "C:/", "C:\\"]),
       tail=st.text(alphabet="abc/_", min_size=1, max_size=10))
def test_property_escape_prefixes_always_blocked(tmp_path, monkeypatch, prefix, tail):
    """No traversal/absolute/windows prefix ever resolves inside the jail — always rejected."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path / "ws"))
    result = FsRead().execute(_req("fs_read", path=prefix + tail))
    assert result["ok"] is False
    assert "outside workspace" in result["error"]


# --------------------------------------------------------------------------------------
# feature.install — registration wiring + the safety chokepoint end-to-end
# --------------------------------------------------------------------------------------


@pytest.mark.audit
def test_install_registers_feature_and_all_tools():
    """install() registers the toolbox feature and every advertised capability behind SafeToolPort."""
    kernel = build_kernel({"features": {}})
    install(kernel)
    names = {t["name"] for t in kernel.registry.list_tools()}
    # The original core four always register…
    assert {"fs_read", "fs_write", "fs_list", "terminal_run"} <= names
    feature_names = {f["name"] for f in kernel.registry.list_features()}
    assert FEATURE.name in feature_names
    # …and the descriptor's advertised capabilities match exactly what got wired (the real invariant).
    wired_toolbox = {t["name"] for t in kernel.registry.list_tools() if t["feature"] == FEATURE.name}
    assert set(FEATURE.capabilities) == wired_toolbox


@pytest.mark.audit
def test_install_applies_retry_and_risk_descriptors():
    """The per-tool retry/risk semantics survive registration (idempotent reads vs risky effects)."""
    kernel = build_kernel(TOOLBOX_CONFIG)
    expected = {
        "fs_read": ("read", True, "low"),
        "fs_list": ("read", True, "low"),
        "fs_write": ("effect", False, "medium"),
        "terminal_run": ("effect", False, "high"),
    }
    for name, (kind, idem, risk) in expected.items():
        d = kernel.registry.resolve_tool(name).descriptor
        assert (d.kind, d.idempotent, d.risk) == (kind, idem, risk)


@pytest.mark.audit
@pytest.mark.security
def test_kernel_terminal_policy_block_wrapped_in_envelope(tmp_path, monkeypatch):
    """End-to-end through the kernel: a destructive command is blocked by SafeToolPort and the
    raw tool fields are carried under the CapabilityResult 'data' key (ok False, policy_blocked)."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    kernel = build_kernel(TOOLBOX_CONFIG)
    result = kernel.execute_tool("terminal_run", {"argv": ["rm", "-rf", "/"]})
    assert result["ok"] is False
    assert result["data"]["policy_blocked"] is True
    assert result["data"]["policy_code"] == "destructive"


@pytest.mark.audit
@pytest.mark.security
def test_kernel_fs_write_then_read_round_trip(tmp_path, monkeypatch):
    """End-to-end happy path through the kernel envelope (content lands under data.content)."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    kernel = build_kernel(TOOLBOX_CONFIG)
    w = kernel.execute_tool("fs_write", {"path": "k/round.txt", "content": "kernel-rt"})
    assert w["ok"] is True
    r = kernel.execute_tool("fs_read", {"path": "k/round.txt"})
    assert r["ok"] is True and r["data"]["content"] == "kernel-rt"


@pytest.mark.audit
@pytest.mark.security
def test_kernel_terminal_no_shell_expansion_end_to_end(tmp_path, monkeypatch):
    """The no-shell guarantee holds through the full kernel path too: '$HOME' stays literal."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    echo = _echo_bin()
    kernel = build_kernel(TOOLBOX_CONFIG)
    result = kernel.execute_tool("terminal_run", {"argv": [echo, "$HOME"]})
    assert result["ok"] is True
    assert result["data"]["stdout"].strip() == "$HOME"
