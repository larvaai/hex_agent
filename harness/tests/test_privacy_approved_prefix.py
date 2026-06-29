"""test_privacy_approved_prefix.py — APPROVED: override for the privacy read gate (B9).

Flow: Read ".env" is BLOCKED; the human approves; the agent retries Read "APPROVED:.env"
which the gate ALLOWS (and audit-logs). Sensitivity must still be detected WITH the
prefix (so the override is recognized as an override, not a non-secret), and the prefix
is stripped from the input that actually reaches the Read tool.
"""
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1] / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

import privacy_read_guard as prg  # noqa: E402


def _read(path):
    return {"tool_name": "Read", "tool_input": {"file_path": path}}


def test_has_and_strip_prefix():
    assert prg._has_approval("APPROVED:.env")
    assert not prg._has_approval(".env")
    assert prg._strip_approval("APPROVED:/p/.env") == "/p/.env"
    assert prg._strip_approval(".env") == ".env"


def test_sensitivity_detected_with_prefix():
    assert prg._is_sensitive("APPROVED:.env")
    assert prg._is_sensitive(".env")
    assert not prg._is_sensitive("APPROVED:app.py")
    assert not prg._is_sensitive("app.py")


def test_core_blocks_unapproved_secret():
    reason = prg.core(_read(".env"))
    assert isinstance(reason, str) and "approval" in reason.lower()


def test_core_allows_approved_secret():
    assert prg.core(_read("APPROVED:.env")) is None


def test_core_allows_normal_file():
    assert prg.core(_read("app.py")) is None


def test_allow_payload_strips_prefix():
    out = prg._allow_stripped_output(_read("APPROVED:/p/.env"))
    inp = out["hookSpecificOutput"]["updatedInput"]
    assert inp["file_path"] == "/p/.env"
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
