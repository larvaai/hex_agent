"""test_harness_paths.py — ROOT + state-dir resolution seams.

Resolution order for root(): HARNESS_ROOT env > upward marker walk from CWD
(harness/manifest.json post-install, or harness/hooks/ pre-manifest bootstrap)
> CWD as-is. state_dir(): HARNESS_STATE_DIR env > <root>/harness/state.
Pure resolution — no mkdir side effects; writers own their mkdir.
"""
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import harness_paths  # noqa: E402


class TestRoot:
    def test_env_override_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HARNESS_ROOT", str(tmp_path))
        assert harness_paths.root() == tmp_path.resolve()

    def test_marker_manifest_found_from_nested_cwd(self, monkeypatch, tmp_path):
        repo = tmp_path / "repo"
        (repo / "harness").mkdir(parents=True)
        (repo / "harness" / "manifest.json").write_text("{}", encoding="utf-8")
        deep = repo / "a" / "b"
        deep.mkdir(parents=True)
        monkeypatch.delenv("HARNESS_ROOT", raising=False)
        monkeypatch.chdir(deep)
        assert harness_paths.root() == repo.resolve()

    def test_marker_hooks_dir_serves_pre_manifest_bootstrap(self, monkeypatch, tmp_path):
        # Before the first build_manifest run there is no manifest.json yet;
        # the committed harness/hooks/ dir is the bootstrap marker.
        repo = tmp_path / "repo"
        (repo / "harness" / "hooks").mkdir(parents=True)
        deep = repo / "sub"
        deep.mkdir()
        monkeypatch.delenv("HARNESS_ROOT", raising=False)
        monkeypatch.chdir(deep)
        assert harness_paths.root() == repo.resolve()

    def test_no_marker_falls_back_to_cwd(self, monkeypatch, tmp_path):
        monkeypatch.delenv("HARNESS_ROOT", raising=False)
        monkeypatch.chdir(tmp_path)
        assert harness_paths.root() == tmp_path.resolve()


class TestStateDirs:
    def test_state_env_override_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HARNESS_STATE_DIR", str(tmp_path / "st"))
        assert harness_paths.state_dir() == tmp_path / "st"

    def test_state_defaults_under_root(self, monkeypatch, tmp_path):
        monkeypatch.delenv("HARNESS_STATE_DIR", raising=False)
        monkeypatch.setenv("HARNESS_ROOT", str(tmp_path))
        assert harness_paths.state_dir() == tmp_path.resolve() / "harness" / "state"

    def test_trace_and_telemetry_nest_under_state(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HARNESS_STATE_DIR", str(tmp_path / "st"))
        assert harness_paths.trace_dir() == tmp_path / "st" / "trace"
        assert harness_paths.telemetry_dir() == tmp_path / "st" / "telemetry"

    def test_resolution_is_pure_no_mkdir(self, monkeypatch, tmp_path):
        # Calling the resolvers must not create directories — writers mkdir.
        monkeypatch.setenv("HARNESS_ROOT", str(tmp_path))
        monkeypatch.delenv("HARNESS_STATE_DIR", raising=False)
        harness_paths.state_dir()
        harness_paths.trace_dir()
        harness_paths.telemetry_dir()
        assert not (tmp_path / "harness").exists()
