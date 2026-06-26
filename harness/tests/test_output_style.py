"""test_output_style.py — the output_style audience-adaptation axis.

output_style (0..5) is a NEW knob distinct from the terminal-voice knobs: it adapts the
deliverable itself — prose AND code (comment density, verbosity, analogies) — to the
reader's coding expertise (0=absolute beginner … 5=expert). Unlike terminal_voice_level
and the other terminal-voice knobs it is deliberately NOT scope-fenced. Default is off
(None) so existing behavior is unchanged until a project opts in.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "harness" / "scripts"
_HOOKS = _ROOT / "harness" / "hooks"
for p in (_SCRIPTS, _HOOKS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import voice_prefs  # noqa: E402
import voice_inject  # noqa: E402

_STYLE_DIR = _ROOT / "harness" / "data" / "output-styles"
_LEVELS = {0: "eli5", 1: "junior", 2: "mid", 3: "senior", 4: "lead", 5: "god"}


def test_six_profiles_present_and_brand_clean():
    import re
    banned = re.compile(r"/ck:|\.claude/" + r"(?:skills|hooks)/|ClaudeKit|claudekit", re.I)
    for lvl, name in _LEVELS.items():
        f = _STYLE_DIR / ("coding-level-%d-%s.md" % (lvl, name))
        assert f.is_file(), "missing profile %s" % f
        assert not banned.search(f.read_text(encoding="utf-8")), "brand leak in %s" % f


def test_default_is_off():
    assert voice_prefs.DEFAULTS.get("output_style") is None


def test_valid_levels_and_none_accepted():
    enum = voice_prefs.ENUMS["output_style"]
    assert None in enum
    for lvl in range(0, 6):
        assert lvl in enum
    assert 7 not in enum


def test_names_cover_all_levels():
    for lvl, name in _LEVELS.items():
        assert voice_prefs.OUTPUT_STYLE_NAMES[lvl] == name


def test_profile_resolver():
    prof = voice_prefs.output_style_profile(3)
    assert prof is not None
    assert prof["name"] == "senior"
    assert Path(prof["file"]).is_file()
    assert voice_prefs.output_style_profile(None) is None


def test_injection_includes_block_when_set():
    prefs = dict(voice_prefs.DEFAULTS)
    prefs["output_style"] = 0
    ctx = voice_inject.build_context(prefs)
    assert "output style" in ctx.lower()
    assert "eli5" in ctx.lower()
    # it must declare that this axis DOES shape the deliverable (not scope-fenced)
    assert "harness/data/output-styles/" in ctx


def test_injection_omits_block_when_off():
    prefs = dict(voice_prefs.DEFAULTS)  # output_style None
    ctx = voice_inject.build_context(prefs)
    assert "output-styles/" not in ctx


def test_cli_set_output_style(tmp_path):
    import os
    import subprocess
    vp = _ROOT / "harness" / "scripts" / "voice_prefs.py"
    cfg = tmp_path / "terminal-voice.yaml"
    env = {**os.environ, "HARNESS_TERMINAL_VOICE": str(cfg)}
    # set an integer level
    r = subprocess.run([sys.executable, str(vp), "--set", "output_style=2"],
                       env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert voice_prefs.load(cfg)["output_style"] == 2
    # turn it back off
    r = subprocess.run([sys.executable, str(vp), "--set", "output_style=off"],
                       env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert voice_prefs.load(cfg)["output_style"] is None
