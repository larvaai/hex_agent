"""test_ownership_gate.py — declared-file-ownership engine + CLI.

The harness already owns the prose convention (each work-unit declares the
file globs it may touch, no editing overlap; an ownership violation must STOP).
This gate gives that convention deterministic teeth in two layers:

  * overlap   — pairwise advisory report (two units declare colliding files).
                Humans keep the scheduling call, so it never blocks by default.
  * reconcile — aggregate fail-closed check: every changed file must be covered
                by some unit's declared globs. An unowned changed file is
                under-declaration → exit 2 with an actionable reason.

Pure functions are exercised by direct import; exit-code/trace paths run the
CLI as a subprocess so the assertion is the real process contract.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import ownership_gate  # noqa: E402


# ----------------------------------------------------------------- helpers ---

def _write_manifest(tmp_path, units):
    """Write a work-ownership.yaml under tmp_path and return its path."""
    import yaml

    p = tmp_path / "work-ownership.yaml"
    p.write_text(yaml.safe_dump({"units": units}), encoding="utf-8")
    return p


def _touch(root, rel):
    """Create an empty file at root/rel (parents as needed)."""
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("", encoding="utf-8")
    return p


def _trace_text(state_dir):
    trace = Path(state_dir) / "trace"
    if not trace.is_dir():
        return ""
    return "".join(p.read_text(encoding="utf-8")
                   for p in sorted(trace.glob("trace-*.jsonl")))


def _guard_policy(tmp_path, *, preset="balanced", reconcile=None):
    """Write a hermetic guard-policy.yaml (quoted scalars so `off` stays a
    string) and return its path. `reconcile` overrides ownership_reconcile so a
    test can pin the gate to warn/off without depending on the shipped file."""
    lines = ['schema_version: "1.0"', 'preset: "%s"' % preset]
    if reconcile is not None:
        lines += ["overrides:", '  ownership_reconcile: "%s"' % reconcile]
    else:
        lines.append("overrides: {}")
    p = tmp_path / "guard-policy.yaml"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


# ------------------------------------------------------------ load_ownership ---

class TestLoadOwnership:
    def test_valid_manifest_parses(self, tmp_path):
        p = _write_manifest(tmp_path, [
            {"id": "dev-auth", "role": "developer",
             "globs": ["harness/scripts/auth_*.py"]},
            {"id": "dev-store", "globs": ["harness/scripts/store_*.py"]},
        ])
        cfg = ownership_gate.load_ownership(p)
        ids = [u["id"] for u in cfg["units"]]
        assert ids == ["dev-auth", "dev-store"]
        assert cfg["units"][0]["globs"] == ["harness/scripts/auth_*.py"]

    def test_missing_file_names_path(self, tmp_path):
        missing = tmp_path / "nope.yaml"
        with pytest.raises(ownership_gate.OwnershipConfigError) as ei:
            ownership_gate.load_ownership(missing)
        assert str(missing) in str(ei.value)

    def test_non_mapping_document_rejected(self, tmp_path):
        p = tmp_path / "work-ownership.yaml"
        p.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(ownership_gate.OwnershipConfigError):
            ownership_gate.load_ownership(p)

    def test_units_not_a_list_rejected(self, tmp_path):
        p = tmp_path / "work-ownership.yaml"
        p.write_text("units: not-a-list\n", encoding="utf-8")
        with pytest.raises(ownership_gate.OwnershipConfigError) as ei:
            ownership_gate.load_ownership(p)
        assert "units" in str(ei.value)

    def test_unit_missing_globs_names_key(self, tmp_path):
        p = _write_manifest(tmp_path, [{"id": "dev-auth"}])
        with pytest.raises(ownership_gate.OwnershipConfigError) as ei:
            ownership_gate.load_ownership(p)
        assert "globs" in str(ei.value)

    def test_unit_missing_id_rejected(self, tmp_path):
        p = _write_manifest(tmp_path, [{"globs": ["a/*.py"]}])
        with pytest.raises(ownership_gate.OwnershipConfigError) as ei:
            ownership_gate.load_ownership(p)
        assert "id" in str(ei.value)

    def test_duplicate_id_rejected(self, tmp_path):
        p = _write_manifest(tmp_path, [
            {"id": "dup", "globs": ["a/*.py"]},
            {"id": "dup", "globs": ["b/*.py"]},
        ])
        with pytest.raises(ownership_gate.OwnershipConfigError) as ei:
            ownership_gate.load_ownership(p)
        assert "dup" in str(ei.value)


# ---------------------------------------------------------------- match_any ---

class TestMatchAny:
    def test_direct_match(self):
        assert ownership_gate.match_any(
            "harness/scripts/a.py", ["harness/scripts/*"]) is True

    def test_non_match_other_dir(self):
        assert ownership_gate.match_any(
            "harness/hooks/a.py", ["harness/scripts/*"]) is False

    def test_star_spans_slash_owns_subtree(self):
        # Documented fnmatch semantics: * spans '/', so dir/* owns the subtree.
        assert ownership_gate.match_any(
            "harness/scripts/sub/a.py", ["harness/scripts/*"]) is True

    def test_no_globs_never_matches(self):
        assert ownership_gate.match_any("any/path.py", []) is False


# ----------------------------------------------------------- compute_overlap ---

class TestComputeOverlap:
    def test_shared_real_file_flagged(self, tmp_path):
        _touch(tmp_path, "pkg/shared.py")
        _touch(tmp_path, "pkg/only_a.py")
        units = [
            {"id": "a", "globs": ["pkg/shared.py", "pkg/only_a.py"]},
            {"id": "b", "globs": ["pkg/shared.py"]},
        ]
        overlaps = ownership_gate.compute_overlap(units, tmp_path)
        assert len(overlaps) == 1
        o = overlaps[0]
        assert {o["a"], o["b"]} == {"a", "b"}
        assert "pkg/shared.py" in o["shared"]
        assert "pkg/only_a.py" not in o["shared"]

    def test_disjoint_units_no_overlap(self, tmp_path):
        _touch(tmp_path, "pkg/a.py")
        _touch(tmp_path, "pkg/b.py")
        units = [
            {"id": "a", "globs": ["pkg/a.py"]},
            {"id": "b", "globs": ["pkg/b.py"]},
        ]
        assert ownership_gate.compute_overlap(units, tmp_path) == []

    def test_same_raw_glob_no_file_still_flagged(self, tmp_path):
        # Neither glob matches a real file, but the identical pattern is a
        # declared collision and must surface.
        units = [
            {"id": "a", "globs": ["pkg/future_*.py"]},
            {"id": "b", "globs": ["pkg/future_*.py"]},
        ]
        overlaps = ownership_gate.compute_overlap(units, tmp_path)
        assert len(overlaps) == 1
        assert "pkg/future_*.py" in overlaps[0]["shared_globs"]


# --------------------------------------------------------------- reconcile ---

class TestReconcile:
    def test_all_changed_declared_returns_none(self):
        units = [{"id": "a", "globs": ["harness/scripts/auth_*.py"]}]
        assert ownership_gate.reconcile(
            ["harness/scripts/auth_login.py"], units) is None

    def test_unowned_change_returns_reason_naming_file(self):
        units = [{"id": "a", "globs": ["harness/scripts/auth_*.py"]}]
        reason = ownership_gate.reconcile(
            ["harness/scripts/auth_login.py",
             "harness/scripts/intruder.py"], units)
        assert reason is not None
        assert "intruder.py" in reason
        assert "auth_login.py" not in reason


# --------------------------------------------------------- reconcile_actor ---

class TestReconcileActor:
    _UNITS = [
        {"id": "auth", "owner": "user:alice",
         "globs": ["harness/scripts/auth_*.py"]},
        {"id": "ui", "owner": "user:bob", "globs": ["harness/ui/*.py"]},
    ]

    def test_owner_touching_own_lane_ok(self):
        assert ownership_gate.reconcile_actor(
            ["harness/scripts/auth_login.py"], self._UNITS, "user:alice") is None

    def test_owner_poaching_other_lane_blocks(self):
        reason = ownership_gate.reconcile_actor(
            ["harness/ui/panel.py"], self._UNITS, "user:alice")
        assert reason is not None
        assert "panel.py" in reason
        assert "user:bob" in reason

    def test_agent_persona_collapses_to_owning_user(self):
        # alice acting through an agent persona still owns alice's lane.
        assert ownership_gate.reconcile_actor(
            ["harness/scripts/auth_login.py"], self._UNITS,
            "user:alice/agent:developer") is None

    def test_ungoverned_actor_returns_none(self):
        # carol owns no unit → not policed (a fresh repo with no owners stays open).
        assert ownership_gate.reconcile_actor(
            ["harness/ui/panel.py"], self._UNITS, "user:carol") is None

    def test_undeclared_file_is_not_a_poach(self):
        # a file in nobody's lane is reconcile()'s under-declaration job.
        assert ownership_gate.reconcile_actor(
            ["docs/readme.md"], self._UNITS, "user:alice") is None

    def test_units_without_owner_are_ignored(self):
        units = [{"id": "x", "globs": ["a/*.py"]}]
        assert ownership_gate.reconcile_actor(
            ["a/b.py"], units, "user:alice") is None

    def test_load_ownership_carries_owner(self, tmp_path):
        import yaml
        p = tmp_path / "work-ownership.yaml"
        p.write_text(yaml.safe_dump({"units": [
            {"id": "auth", "owner": "user:alice",
             "globs": ["harness/scripts/auth_*.py"]}]}), encoding="utf-8")
        cfg = ownership_gate.load_ownership(p)
        assert cfg["units"][0]["owner"] == "user:alice"


# --------------------------------------------------------------------- CLI ---

class TestCLI:
    def _run(self, args, env_extra=None):
        env = dict(os.environ)
        env["HARNESS_USER"] = "tester@local"
        env.pop("CI", None)
        env.pop("GITHUB_ACTIONS", None)
        env.pop("GITLAB_CI", None)
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            [sys.executable, str(_SCRIPTS / "ownership_gate.py")] + args,
            capture_output=True, text=True, env=env, timeout=30)

    def test_reconcile_blocks_unowned_with_reason(self, tmp_path):
        p = _write_manifest(tmp_path, [
            {"id": "a", "globs": ["harness/scripts/auth_*.py"]}])
        out = self._run([
            "reconcile", "--manifest", str(p),
            "--changed", "harness/scripts/intruder.py"],
            env_extra={"HARNESS_GUARD_POLICY": str(_guard_policy(tmp_path))})
        assert out.returncode == 2, out.stderr
        assert "intruder.py" in out.stderr

    def test_reconcile_warn_downgrades_to_advisory_exit_zero(self, tmp_path):
        # ownership_reconcile=warn: the same unowned file no longer blocks; the
        # reason is emitted as an advisory and the process exits 0.
        p = _write_manifest(tmp_path, [
            {"id": "a", "globs": ["harness/scripts/auth_*.py"]}])
        out = self._run([
            "reconcile", "--manifest", str(p),
            "--changed", "harness/scripts/intruder.py"],
            env_extra={"HARNESS_GUARD_POLICY":
                       str(_guard_policy(tmp_path, reconcile="warn"))})
        assert out.returncode == 0, out.stderr
        assert "[advisory]" in out.stderr
        assert "intruder.py" in out.stderr

    def test_reconcile_off_is_silent_exit_zero(self, tmp_path):
        p = _write_manifest(tmp_path, [
            {"id": "a", "globs": ["harness/scripts/auth_*.py"]}])
        out = self._run([
            "reconcile", "--manifest", str(p),
            "--changed", "harness/scripts/intruder.py"],
            env_extra={"HARNESS_GUARD_POLICY":
                       str(_guard_policy(tmp_path, reconcile="off"))})
        assert out.returncode == 0, out.stderr
        assert "intruder.py" not in out.stderr

    def test_reconcile_passes_when_declared(self, tmp_path):
        p = _write_manifest(tmp_path, [
            {"id": "a", "globs": ["harness/scripts/auth_*.py"]}])
        out = self._run([
            "reconcile", "--manifest", str(p),
            "--changed", "harness/scripts/auth_login.py"])
        assert out.returncode == 0, out.stderr

    def test_reconcile_block_emits_trace_with_actor(self, tmp_path):
        state = tmp_path / "state"
        p = _write_manifest(tmp_path, [
            {"id": "a", "globs": ["harness/scripts/auth_*.py"]}])
        out = self._run([
            "reconcile", "--manifest", str(p),
            "--changed", "harness/scripts/intruder.py"],
            env_extra={"HARNESS_STATE_DIR": str(state),
                       "HARNESS_GUARD_POLICY": str(_guard_policy(tmp_path))})
        assert out.returncode == 2
        text = _trace_text(state)
        assert "reconcile_block" in text
        line = [json.loads(l) for l in text.splitlines()
                if "reconcile_block" in l][0]
        assert line["actor"]

    def test_overlap_advisory_exit_zero(self, tmp_path):
        p = _write_manifest(tmp_path, [
            {"id": "a", "globs": ["pkg/future_*.py"]},
            {"id": "b", "globs": ["pkg/future_*.py"]},
        ])
        out = self._run(["overlap", "--manifest", str(p), "--root", str(tmp_path)])
        assert out.returncode == 0, out.stderr
        report = json.loads(out.stdout)
        assert report["overlaps"]

    def test_overlap_strict_exits_two_on_collision(self, tmp_path):
        p = _write_manifest(tmp_path, [
            {"id": "a", "globs": ["pkg/future_*.py"]},
            {"id": "b", "globs": ["pkg/future_*.py"]},
        ])
        out = self._run([
            "overlap", "--manifest", str(p), "--root", str(tmp_path), "--strict"])
        assert out.returncode == 2, out.stderr

    def test_overlap_strict_clean_exits_zero(self, tmp_path):
        p = _write_manifest(tmp_path, [
            {"id": "a", "globs": ["pkg/a_*.py"]},
            {"id": "b", "globs": ["pkg/b_*.py"]},
        ])
        out = self._run([
            "overlap", "--manifest", str(p), "--root", str(tmp_path), "--strict"])
        assert out.returncode == 0, out.stderr


def test_expand_skips_symlink_escaped_files(tmp_path):
    """A symlinked dir pointing OUTSIDE root must not have its files attributed
    to an in-repo owned glob — expand() reasons only over files physically in
    the repo (containment)."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "real.py").write_text("x = 1\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "evil.py").write_text("secret = 1\n", encoding="utf-8")
    try:
        os.symlink(outside, root / "link")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unsupported on this platform")
    got = ownership_gate.expand(["**/*.py"], root)
    assert "real.py" in got
    assert all("evil" not in p for p in got), got
    assert "link/evil.py" not in got
