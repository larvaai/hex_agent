"""test_platform_utils.py — Windows-support platform utilities (B3).

These three utilities are imported by *ported* skill scripts that compute
``CLAUDE_ROOT = Path(__file__).parents[3]`` (the plugin root) and then
``sys.path.insert(0, CLAUDE_ROOT / "scripts")``. So the util must live at
``<plugin>/scripts/<name>.py`` — that is the contract the consumers already
ship. These tests prove the *wiring* (a consumer can import it), not just that
a file exists.

- resolve_env.py  -> consumed by hs-ai/ai-multimodal (4 scripts)
- win_compat.py   -> consumed by hs-devops/devops + hs-stack/databases
- encoding_utils.py -> ALREADY canonical in harness/scripts (must NOT be re-added)
"""
import importlib
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_PLUGINS = _REPO / "harness" / "plugins"
_HS_AI_SCRIPTS = _PLUGINS / "hs-ai" / "scripts"
_HS_DEVOPS_SCRIPTS = _PLUGINS / "hs-devops" / "scripts"
_HS_STACK_SCRIPTS = _PLUGINS / "hs-stack" / "scripts"


def _import_from(dirpath, modname):
    """Import a module from a specific dir, isolating it from sys.modules cache."""
    sys.modules.pop(modname, None)
    sys.path.insert(0, str(dirpath))
    try:
        mod = importlib.import_module(modname)
        return importlib.reload(mod)
    finally:
        try:
            sys.path.remove(str(dirpath))
        except ValueError:
            pass


# ---- resolve_env (hs-ai) ----------------------------------------------------

def test_resolve_env_file_at_consumer_path():
    # the 4 ai-multimodal scripts insert <plugin>/scripts onto sys.path
    assert (_HS_AI_SCRIPTS / "resolve_env.py").is_file(), \
        "resolve_env.py must live where hs-ai consumers look: hs-ai/scripts/"


def test_resolve_env_process_env_wins(monkeypatch):
    monkeypatch.setenv("HS_PLATFORM_TEST_KEY", "from-process-env")
    mod = _import_from(_HS_AI_SCRIPTS, "resolve_env")
    assert mod.resolve_env("HS_PLATFORM_TEST_KEY") == "from-process-env"


def test_resolve_env_default_when_absent(monkeypatch):
    monkeypatch.delenv("HS_DEFINITELY_MISSING_XYZ", raising=False)
    mod = _import_from(_HS_AI_SCRIPTS, "resolve_env")
    assert mod.resolve_env("HS_DEFINITELY_MISSING_XYZ", default="fallback") == "fallback"


def test_resolve_env_exports_get_env_file_paths():
    # gemini_batch_process.py does `from resolve_env import get_env_file_paths`
    mod = _import_from(_HS_AI_SCRIPTS, "resolve_env")
    paths = mod.get_env_file_paths(skill="ai-multimodal")
    assert isinstance(paths, list) and all(len(t) == 2 for t in paths)


# ---- win_compat (hs-devops + hs-stack) --------------------------------------

@pytest.mark.parametrize("scripts_dir", [_HS_DEVOPS_SCRIPTS, _HS_STACK_SCRIPTS])
def test_win_compat_file_at_consumer_path(scripts_dir):
    assert (scripts_dir / "win_compat.py").is_file(), \
        "win_compat.py must live where the consumer looks: <plugin>/scripts/"


def test_win_compat_importable_and_callable():
    mod = _import_from(_HS_DEVOPS_SCRIPTS, "win_compat")
    # no-op on linux; must not raise
    mod.ensure_utf8_stdout()
    mod.safe_print("platform util smoke: ✓ unicode")
    assert callable(mod.ensure_utf8_stdout) and callable(mod.safe_print)


def test_win_compat_no_claudekit_brand():
    text = (_HS_DEVOPS_SCRIPTS / "win_compat.py").read_text(encoding="utf-8")
    assert "ClaudeKit" not in text, "ck-port must drop the ClaudeKit brand"


# ---- encoding_utils (already canonical — guard against re-add) --------------

def test_encoding_utils_stays_canonical_in_harness_scripts():
    canon = _REPO / "harness" / "scripts" / "encoding_utils.py"
    assert canon.is_file()
    body = canon.read_text(encoding="utf-8")
    # the richer HS version (configure_utf8_console + emit_json) must remain
    assert "def configure_utf8_console" in body
    assert "def emit_json" in body, "must not be clobbered by the leaner CK copy"
