"""test_bash_write_guard.py — PostToolUse:Bash advisory that SURFACES a write to
a guarded config path spelled through the shell (telemetry-class, fail-open).

write_guard (PreToolUse:Write|Edit) blocks the agent's file tools from editing
gate config, but it is blind to a Bash redirect / tee / sed -i / python open()
aimed at the same path. This hook can't block (PostToolUse runs AFTER the
command), so it does the one honest thing left: detect the bypass, record it to
the telemetry ledger, and nudge — the edited file is tracked, so it also shows
as a git diff. Defense-in-depth surfacing, never a gate.

The blessed workaround (write to /tmp then cp/mv into place) is deliberately NOT
flagged: cp/mv is the sanctioned, visible path. Reading a guarded file and
redirecting ELSEWHERE is not a write to it and must stay silent.
"""
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(_HOOKS))

import bash_write_guard as g  # noqa: E402


def _rels(cmd):
    return {rel for rel, _pat in g.bypass_targets(cmd)}


# --- positive: stealth writes to a guarded path are flagged -------------------

def test_redirect_overwrite_into_guarded_hook_flagged():
    assert "harness/hooks/gate_stage.py" in _rels("echo x > harness/hooks/gate_stage.py")


def test_append_redirect_into_guarded_data_flagged():
    assert "harness/data/team.yaml" in _rels("printf 'r: []' >> harness/data/team.yaml")


def test_tee_into_guarded_data_flagged():
    assert "harness/data/stage-policy.yaml" in _rels(
        "echo policy | tee harness/data/stage-policy.yaml")


def test_tee_append_flag_into_guarded_flagged():
    assert "harness/data/ownership.yaml" in _rels(
        "echo x | tee -a harness/data/ownership.yaml")


def test_sed_inplace_on_guarded_script_flagged():
    assert "harness/scripts/fs_guard.py" in _rels(
        "sed -i 's/a/b/' harness/scripts/fs_guard.py")


def test_python_open_write_on_guarded_flagged():
    assert "harness/data/task-store.yaml" in _rels(
        "python3 -c \"open('harness/data/task-store.yaml','w').write('x')\"")


def test_absolute_path_into_guarded_flagged():
    root = g._root()
    abs_target = str(root / "harness" / "hooks" / "write_guard.py")
    assert "harness/hooks/write_guard.py" in _rels("echo x > %s" % abs_target)


# --- negative: legitimate / non-write shapes stay silent ----------------------

def test_reading_guarded_and_redirecting_elsewhere_not_flagged():
    # the guarded file is the SOURCE; the write lands in /tmp — not a write to it
    assert _rels("cat harness/hooks/gate_stage.py > /tmp/out") == set()


def test_cp_into_guarded_is_blessed_workaround_not_flagged():
    assert _rels("cp /tmp/team.yaml harness/data/team.yaml") == set()


def test_mv_into_guarded_is_blessed_workaround_not_flagged():
    assert _rels("mv /tmp/x.py harness/hooks/gate_stage.py") == set()


def test_redirect_inside_a_quoted_string_not_flagged():
    # a '>' living inside a quoted literal is NOT a redirect — must not false-fire
    assert _rels('echo "note: run foo > harness/data/team.yaml"') == set()
    assert _rels('git commit -m "edit > harness/hooks/gate_stage.py"') == set()
    assert _rels("grep 'a > harness/data/team.yaml' notes.txt") == set()


def test_quoted_then_real_redirect_still_flagged():
    # a quoted arg followed by a REAL unquoted redirect to a guarded path → flag
    assert "harness/data/team.yaml" in _rels(
        'echo "hello world" > harness/data/team.yaml')


def test_clobber_force_redirect_flagged():
    assert "harness/data/team.yaml" in _rels("echo x >| harness/data/team.yaml")


def test_dd_of_into_guarded_flagged():
    assert "harness/data/team.yaml" in _rels(
        "dd if=/dev/zero of=harness/data/team.yaml")


def test_redirect_to_unguarded_path_not_flagged():
    assert _rels("echo x > /tmp/foo.txt") == set()
    assert _rels("echo x > harness/state/scratch.txt") == set()


def test_stderr_redirect_is_not_a_write_target():
    assert _rels("python3 harness/scripts/preflight_deps.py 2>&1 > /tmp/log") == \
        {p for p in _rels("python3 harness/scripts/preflight_deps.py 2>&1 > /tmp/log")
         if p.startswith("harness/data") or p.startswith("harness/hooks")}
    # concretely: nothing guarded is flagged here
    assert _rels("foo 2>&1 | tee /tmp/x") == set()


# --- core() contract: detect → trace + stderr advisory, never blocks ----------

def test_core_writes_advisory_on_bypass(capsys):
    g.core({"tool_name": "Bash",
            "tool_input": {"command": "echo x > harness/hooks/gate_stage.py"}})
    err = capsys.readouterr().err
    assert "gate_stage.py" in err
    assert "git diff" in err or "tracked" in err


def test_core_silent_when_no_bypass(capsys):
    g.core({"tool_name": "Bash", "tool_input": {"command": "ls -la"}})
    assert capsys.readouterr().err == ""


def test_core_ignores_non_bash_tool(capsys):
    g.core({"tool_name": "Write",
            "tool_input": {"file_path": "harness/hooks/gate_stage.py"}})
    assert capsys.readouterr().err == ""


def test_bypass_targets_fail_open_on_junk():
    assert g.bypass_targets("") == []
    assert g.bypass_targets(None) == []
