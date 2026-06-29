"""test_guard_policy.py — unified off/warn/block posture engine.

Every configurable SDLC guard resolves its enforcement mode through one place:
a preset baseline (strict|balanced|lenient) per guard CATEGORY, with optional
per-guard overrides, and a safety FLOOR that a preset can never lower (only an
explicit, separately-logged override break-glass can).

Pure resolution is exercised by direct import. The `gate()` adapter does IO
(stderr advisory + an append-only trace line), so it is driven in-process with
HARNESS_STATE_DIR / HARNESS_GUARD_POLICY pointed at a tmp dir and the trace
file read back as the real audit contract.
"""
import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import guard_policy  # noqa: E402


# ----------------------------------------------------------------- helpers ---

def _policy(tmp_path, preset="balanced", overrides=None):
    """Write a guard-policy.yaml under tmp_path and return its path."""
    import yaml

    doc = {"schema_version": "1.0", "preset": preset}
    if overrides is not None:
        doc["overrides"] = overrides
    p = tmp_path / "guard-policy.yaml"
    p.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return p


def _trace_events(state_dir):
    """Every trace event dict written under state_dir/trace/."""
    out = []
    d = Path(state_dir) / "trace"
    for f in sorted(d.glob("trace-*.jsonl")) if d.is_dir() else []:
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


# --------------------------------------------------------------- load/parse ---

def test_load_valid(tmp_path):
    cfg = guard_policy.load_guard_policy(_policy(tmp_path, "strict"))
    assert cfg["preset"] == "strict"
    assert cfg["overrides"] == {}


def test_load_missing_file_defaults_balanced(tmp_path):
    # A missing policy file is not fatal: the safe baseline is `balanced`
    # (safety + enforcement still block; only nudges relax).
    cfg = guard_policy.load_guard_policy(tmp_path / "nope.yaml")
    assert cfg["preset"] == "balanced"
    assert cfg["overrides"] == {}


def test_load_bad_preset_raises(tmp_path):
    with pytest.raises(guard_policy.GuardPolicyError):
        guard_policy.load_guard_policy(_policy(tmp_path, "yolo"))


def test_load_bad_override_value_raises(tmp_path):
    with pytest.raises(guard_policy.GuardPolicyError):
        guard_policy.load_guard_policy(
            _policy(tmp_path, "balanced", {"gate_stage": "sometimes"}))


def test_load_unknown_override_key_raises(tmp_path):
    # A typo'd guard id must fail loudly, not silently no-op.
    with pytest.raises(guard_policy.GuardPolicyError):
        guard_policy.load_guard_policy(
            _policy(tmp_path, "balanced", {"no_such_guard": "off"}))


# --------------------------------------------------------------- resolve_mode ---

def test_balanced_preset_table(tmp_path):
    p = _policy(tmp_path, "balanced")
    assert guard_policy.resolve_mode("bash_safety_guard", p) == "block"   # safety
    assert guard_policy.resolve_mode("gate_stage", p) == "block"          # enforcement
    assert guard_policy.resolve_mode("ownership_overlap", p) == "warn"    # advisory


def test_strict_preset_table(tmp_path):
    p = _policy(tmp_path, "strict")
    assert guard_policy.resolve_mode("write_guard", p) == "block"
    assert guard_policy.resolve_mode("standards_strict_gate", p) == "block"
    assert guard_policy.resolve_mode("cook_isolation_nudge", p) == "warn"


def test_lenient_preset_table(tmp_path):
    p = _policy(tmp_path, "lenient")
    # safety floor holds even under lenient...
    assert guard_policy.resolve_mode("privacy_read_guard", p) == "block"
    assert guard_policy.resolve_mode("merge_gate", p) == "block"
    # ...enforcement relaxes to warn, advisory goes silent.
    assert guard_policy.resolve_mode("ownership_guard", p) == "warn"
    assert guard_policy.resolve_mode("ownership_reconcile", p) == "warn"
    assert guard_policy.resolve_mode("memory_gap_hook", p) == "off"


def test_override_wins_over_preset(tmp_path):
    # lenient would silence an advisory guard; an explicit override re-arms it.
    p = _policy(tmp_path, "lenient", {"ownership_overlap": "block"})
    assert guard_policy.resolve_mode("ownership_overlap", p) == "block"


def test_floor_breach_override_is_honored(tmp_path):
    # The floor stops a PRESET from lowering safety; an explicit per-guard
    # override is the break-glass and IS honored (logged at write time).
    p = _policy(tmp_path, "balanced", {"bash_safety_guard": "off"})
    assert guard_policy.resolve_mode("bash_safety_guard", p) == "off"


def test_unknown_guard_id_raises(tmp_path):
    with pytest.raises(guard_policy.GuardPolicyError):
        guard_policy.resolve_mode("ghost_guard", _policy(tmp_path))


def test_is_floor_breach(tmp_path):
    assert guard_policy.is_floor_breach("bash_safety_guard", "off") is True
    assert guard_policy.is_floor_breach("bash_safety_guard", "block") is False
    assert guard_policy.is_floor_breach("ownership_reconcile", "off") is False


# --------------------------------------------------------------- fingerprint ---

def test_fingerprint_stable_and_changes(tmp_path):
    p = _policy(tmp_path, "balanced")
    fp1 = guard_policy.policy_fingerprint(p)
    assert fp1.startswith("sha256:") and len(fp1) == len("sha256:") + 12
    assert guard_policy.policy_fingerprint(p) == fp1  # deterministic
    _policy(tmp_path, "strict")  # rewrite same path, different content
    assert guard_policy.policy_fingerprint(p) != fp1


# --------------------------------------------------------------- gate() ---

def _gate_env(monkeypatch, tmp_path, policy_path):
    monkeypatch.setenv("HARNESS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HARNESS_GUARD_POLICY", str(policy_path))
    monkeypatch.setenv("HARNESS_USER", "tester@x.com")
    guard_policy._reset_emit_state()


def test_gate_block_returns_reason_and_traces(tmp_path, monkeypatch, capsys):
    p = _policy(tmp_path, "balanced")
    _gate_env(monkeypatch, tmp_path, p)
    out = guard_policy.gate("gate_stage", "missing verification", hook="t")
    assert out == "missing verification"
    events = {e["event"] for e in _trace_events(tmp_path / "state")}
    assert "guard_block" in events


def test_gate_warn_downgrades_and_advises(tmp_path, monkeypatch, capsys):
    p = _policy(tmp_path, "lenient")  # enforcement -> warn
    _gate_env(monkeypatch, tmp_path, p)
    out = guard_policy.gate("ownership_reconcile", "file X owned by nobody",
                            hook="ownership_gate")
    assert out is None  # downgraded: caller must NOT block
    err = capsys.readouterr().err
    assert "[advisory]" in err and "file X owned by nobody" in err
    events = {e["event"] for e in _trace_events(tmp_path / "state")}
    assert "guard_warn" in events


def test_gate_off_is_silent_pass(tmp_path, monkeypatch, capsys):
    p = _policy(tmp_path, "lenient")  # advisory -> off
    _gate_env(monkeypatch, tmp_path, p)
    out = guard_policy.gate("ownership_overlap", "lanes collide", hook="ownership_gate")
    assert out is None
    events = {e["event"] for e in _trace_events(tmp_path / "state")}
    assert "guard_skip" in events


def test_gate_emits_loaded_fingerprint_once(tmp_path, monkeypatch, capsys):
    p = _policy(tmp_path, "balanced")
    _gate_env(monkeypatch, tmp_path, p)
    guard_policy.gate("gate_stage", "r1", hook="t")
    guard_policy.gate("gate_stage", "r2", hook="t")
    loaded = [e for e in _trace_events(tmp_path / "state")
              if e["event"] == "guard_policy_loaded"]
    assert len(loaded) == 1
    assert loaded[0]["note"].startswith("sha256:")
