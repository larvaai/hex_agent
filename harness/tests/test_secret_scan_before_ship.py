"""test_secret_scan_before_ship.py — pre-ship secret leak gate (compliance, fail-closed).

The gate fires only at the leak boundary (push/pr/ship/deploy), scans the diff of the
commits about to leave the machine, and BLOCKS when a real secret pattern appears in an
added line of a non-excluded file. Test/fixture/docs paths are excluded so the gate never
self-blocks on its own fake-secret fixtures and avoids the common false positive.
"""
import subprocess
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1] / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

import secret_scan_before_ship as ss  # noqa: E402

# fake secrets assembled at runtime so this very test file does not ship a literal match
_AWS = "AKIA" + "1234567890ABCDEF"          # AKIA + 16
_PEM = "-----BEGIN RSA PRIVATE KEY-----"


def test_scan_detects_aws_key():
    assert ss.scan_text("aws = %s" % _AWS)


def test_scan_detects_private_key_pem():
    assert ss.scan_text("key:\n%s\n..." % _PEM)


def test_scan_detects_generic_api_key_assignment():
    assert ss.scan_text('api_key = "abcd1234efgh5678ij"')


def test_scan_clean_text_is_empty():
    assert ss.scan_text("just some normal code, no secrets here = 42") == []


def test_added_lines_skip_excluded_paths():
    diff = (
        "+++ b/src/config.py\n"
        "+api_key = \"abcd1234efgh5678ij\"\n"
        "+++ b/tests/test_thing.py\n"
        "+api_key = \"zzzz1111yyyy2222ww\"\n"
    )
    scannable = ss.scannable_added_lines(diff)
    assert "src/config.py" not in scannable  # header lines are not content
    assert "abcd1234efgh5678ij" in scannable        # real source file kept
    assert "zzzz1111yyyy2222ww" not in scannable     # test file excluded


# ---- end-to-end on a real temp repo ----------------------------------------

def _git(repo, *a):
    subprocess.run(["git", "-C", str(repo)] + list(a), capture_output=True, text=True, check=True)


def _repo(tmp_path, content):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "app.py").write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "x")
    return repo


def test_gate_blocks_push_with_secret(tmp_path):
    repo = _repo(tmp_path, "AWS = '%s'\n" % _AWS)
    reason = ss.gate_reason("git push origin main", str(repo))
    assert reason and "secret" in reason.lower()


def test_gate_allows_clean_push(tmp_path):
    repo = _repo(tmp_path, "def f():\n    return 42\n")
    assert ss.gate_reason("git push origin main", str(repo)) is None


def test_gate_ignores_non_ship_command(tmp_path):
    repo = _repo(tmp_path, "AWS = '%s'\n" % _AWS)
    # a non-ship Bash command is not gated even with a secret present
    assert ss.gate_reason("ls -la", str(repo)) is None


def test_added_content_starting_with_plusplus_is_scanned():
    # An added line whose CONTENT starts with '++' renders in a unified diff as
    # '+++<content>' (one '+' for "added" + the '++' of the content). The header
    # check must not mistake it for a '+++ b/path' file header and skip it —
    # otherwise a secret on such a line evades the gate.
    token = "ghp_" + "A" * 30
    diff = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -0,0 +1 @@\n"
        '+++token = "%s"\n' % token
    )
    body = ss.scannable_added_lines(diff)
    assert "ghp_" in body, "++-prefixed added content was dropped: %r" % body
    assert ss.scan_text(body), "secret on a ++-prefixed added line evaded the scan"
