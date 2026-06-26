"""Net-new CHECK_VOCAB predicates + path helpers (slice6b leaves these uncovered)."""
import json

import pytest

from dragzero.verifier import (
    DoneWhen,
    UnsafeArtifactPath,
    assert_safe_relpath,
    resolve_in_workspace,
    run_checks,
)


def _dw(check, artifact=None, **params):
    return DoneWhen(check=check, artifact=artifact, params=params)


# ── file_nonempty_lines ───────────────────────────────────────────────────────
def test_file_nonempty_lines_pass_when_at_or_above_min(tmp_path):
    # blank lines don't count toward the tally
    (tmp_path / "f.txt").write_text("a\n\nb\n   \nc\n")
    v = run_checks([_dw("file_nonempty_lines", "f.txt", min=2)], tmp_path)
    assert v.ok and v.node_verdict == "PASS"


def test_file_nonempty_lines_fail_when_below_min(tmp_path):
    (tmp_path / "f.txt").write_text("a\n\nb\n   \nc\n")  # 3 non-empty lines
    v = run_checks([_dw("file_nonempty_lines", "f.txt", min=5)], tmp_path)
    assert not v.ok
    assert "3 non-empty lines < min 5" in v.results[0].reason


# ── grep_absent ───────────────────────────────────────────────────────────────
def test_grep_absent_fails_when_forbidden_pattern_present(tmp_path):
    (tmp_path / "log.txt").write_text("ok\nFIXME left behind\ndone\n")
    v = run_checks([_dw("grep_absent", "log.txt", pattern="FIXME")], tmp_path)
    assert not v.ok
    assert "forbidden pattern present" in v.results[0].reason


def test_grep_absent_passes_when_pattern_missing(tmp_path):
    (tmp_path / "log.txt").write_text("ok\nall clean\ndone\n")
    v = run_checks([_dw("grep_absent", "log.txt", pattern="FIXME")], tmp_path)
    assert v.ok and v.node_verdict == "PASS"


def test_grep_absent_bad_regex_fails_closed(tmp_path):
    (tmp_path / "log.txt").write_text("anything\n")
    v = run_checks([_dw("grep_absent", "log.txt", pattern="[")], tmp_path)
    assert not v.ok
    assert "bad grep pattern" in v.results[0].reason


# ── json_field_exists ─────────────────────────────────────────────────────────
def test_json_field_exists_pass_for_present_pointer(tmp_path):
    (tmp_path / "d.json").write_text(json.dumps({"a": {"b": 1}}))
    v = run_checks([_dw("json_field_exists", "d.json", ptr="/a/b")], tmp_path)
    assert v.ok and v.node_verdict == "PASS"


def test_json_field_exists_fail_for_missing_pointer(tmp_path):
    (tmp_path / "d.json").write_text(json.dumps({"a": {"b": 1}}))
    v = run_checks([_dw("json_field_exists", "d.json", ptr="/a/c")], tmp_path)
    assert not v.ok
    assert "missing/invalid" in v.results[0].reason


# ── json_field_equals ─────────────────────────────────────────────────────────
def test_json_field_equals_pass_on_match(tmp_path):
    (tmp_path / "d.json").write_text(json.dumps({"status": "green"}))
    v = run_checks([_dw("json_field_equals", "d.json", ptr="/status", value="green")], tmp_path)
    assert v.ok and v.node_verdict == "PASS"


def test_json_field_equals_fail_on_mismatch(tmp_path):
    (tmp_path / "d.json").write_text(json.dumps({"status": "red"}))
    v = run_checks([_dw("json_field_equals", "d.json", ptr="/status", value="green")], tmp_path)
    assert not v.ok
    assert "'red' != 'green'" in v.results[0].reason


# ── json_field_in_range ───────────────────────────────────────────────────────
def test_json_field_in_range_pass_when_inside(tmp_path):
    (tmp_path / "d.json").write_text(json.dumps({"cov": 87}))
    v = run_checks([_dw("json_field_in_range", "d.json", ptr="/cov", min=80, max=100)], tmp_path)
    assert v.ok and v.node_verdict == "PASS"


def test_json_field_in_range_fail_when_outside(tmp_path):
    (tmp_path / "d.json").write_text(json.dumps({"cov": 50}))
    v = run_checks([_dw("json_field_in_range", "d.json", ptr="/cov", min=80, max=100)], tmp_path)
    assert not v.ok
    assert "not in [80.0,100.0]" in v.results[0].reason


def test_json_field_in_range_fail_when_value_not_a_number(tmp_path):
    (tmp_path / "d.json").write_text(json.dumps({"cov": "lots"}))
    v = run_checks([_dw("json_field_in_range", "d.json", ptr="/cov", min=80, max=100)], tmp_path)
    assert not v.ok
    assert "not a number in range" in v.results[0].reason


# ── assert_safe_relpath (direct unit) ─────────────────────────────────────────
def test_assert_safe_relpath_rejects_absolute():
    with pytest.raises(ValueError):
        assert_safe_relpath("/etc/x")


def test_assert_safe_relpath_rejects_home_expansion():
    with pytest.raises(ValueError):
        assert_safe_relpath("~/x")


def test_assert_safe_relpath_rejects_parent_escape():
    with pytest.raises(ValueError):
        assert_safe_relpath("a/../b")


def test_assert_safe_relpath_returns_clean_relpath():
    assert assert_safe_relpath("a/b.txt") == "a/b.txt"


# ── resolve_in_workspace path jail ────────────────────────────────────────────
def test_resolve_in_workspace_rejects_escape(tmp_path):
    with pytest.raises(UnsafeArtifactPath):
        resolve_in_workspace(tmp_path, "../escape")
