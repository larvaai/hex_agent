"""Tests for scaffold.py — deterministic plan/report skeletons from templates.

scaffold renders the template files under harness/templates/ with {{TOKEN}}
substitution, stamps the harness provenance frontmatter via artifact_stamp
(so a new plan never carries a stale kit_digest), and writes into plans/ only —
a slug that tries to climb out (../, a slash) is rejected before any write.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[2]
_SCRIPTS = _ROOT / "harness" / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import scaffold  # noqa: E402


class TestRender:
    def test_substitutes_known_tokens(self):
        out = scaffold.render("a {{TITLE}} b {{ID}}", {"TITLE": "X", "ID": "42"})
        assert out == "a X b 42"

    def test_repeated_token_all_replaced(self):
        out = scaffold.render("{{S}}-{{S}}", {"S": "z"})
        assert out == "z-z"

    def test_unfilled_tokens_reported(self):
        text = "{{A}} kept {{B}}"
        assert scaffold.unfilled_tokens(scaffold.render(text, {"A": "x"})) == ["B"]

    def test_no_tokens_left_after_full_fill(self):
        out = scaffold.render("{{A}}{{B}}", {"A": "1", "B": "2"})
        assert scaffold.unfilled_tokens(out) == []


class TestSlugGuard:
    @pytest.mark.parametrize("bad", ["../evil", "a/b", "Up", "has space", "", "-x", "x-"])
    def test_bad_slug_rejected(self, bad):
        with pytest.raises(ValueError):
            scaffold.validate_slug(bad)

    @pytest.mark.parametrize("ok", ["plan", "a-b-c", "feat-123", "x1"])
    def test_good_slug_ok(self, ok):
        assert scaffold.validate_slug(ok) == ok


class TestScaffoldPlan:
    def _call(self, root, **kw):
        kw.setdefault("plan_id", "260618-2251")
        kw.setdefault("slug", "demo-plan")
        kw.setdefault("title", "Demo Plan")
        kw.setdefault("mode", "hard")
        kw.setdefault("tdd", True)
        kw.setdefault("phases", ["scout", "build"])
        return scaffold.scaffold_plan(root=root, **kw)

    def test_creates_dir_and_files(self, tmp_path):
        # templates live in the real repo; copy them under the tmp root
        _seed_templates(tmp_path)
        d = self._call(tmp_path)
        assert d == tmp_path / "plans" / "260618-2251-demo-plan"
        assert (d / "plan.md").is_file()
        # one phase file per phase, numbered
        assert (d / "phase-1-scout.md").is_file()
        assert (d / "phase-2-build.md").is_file()

    def test_plan_frontmatter_stamped_and_filled(self, tmp_path):
        _seed_templates(tmp_path)
        d = self._call(tmp_path)
        text = (d / "plan.md").read_text(encoding="utf-8")
        assert "title: \"Demo Plan\"" in text
        assert "id: 260618-2251-demo-plan" in text
        # the machine-stamped provenance keys are present (reused artifact_stamp)
        assert "harness_version:" in text
        assert "harness_kit_digest:" in text
        assert "harness_schema_version:" in text
        # no unfilled placeholders leaked into the artifact
        assert scaffold.unfilled_tokens(text) == [], scaffold.unfilled_tokens(text)

    def test_phase_files_named_and_filled(self, tmp_path):
        _seed_templates(tmp_path)
        d = self._call(tmp_path)
        p1 = (d / "phase-1-scout.md").read_text(encoding="utf-8")
        assert "phase: 1" in p1
        assert scaffold.unfilled_tokens(p1) == []

    def test_refuses_clobber_without_force(self, tmp_path):
        _seed_templates(tmp_path)
        self._call(tmp_path)
        with pytest.raises(FileExistsError):
            self._call(tmp_path)

    def test_force_overwrites(self, tmp_path):
        _seed_templates(tmp_path)
        self._call(tmp_path)
        d = self._call(tmp_path, force=True)  # no raise
        assert (d / "plan.md").is_file()

    def test_bad_slug_no_write(self, tmp_path):
        _seed_templates(tmp_path)
        with pytest.raises(ValueError):
            self._call(tmp_path, slug="../escape")
        assert not (tmp_path / "plans").exists() or not any(
            (tmp_path / "plans").iterdir())


class TestScaffoldReport:
    def test_creates_report_path(self, tmp_path):
        _seed_templates(tmp_path)
        p = scaffold.scaffold_report(
            root=tmp_path, report_id="260618-2251", slug="findings",
            rtype="research", title="Findings")
        assert p == (tmp_path / "plans" / "reports"
                     / "research-260618-2251-findings-report.md")
        assert p.is_file()
        text = p.read_text(encoding="utf-8")
        assert "harness_version:" in text
        assert scaffold.unfilled_tokens(text) == []


class TestCLI:
    def test_print_writes_nothing(self, tmp_path):
        _seed_templates(tmp_path)
        proc = subprocess.run(
            [sys.executable, str(_SCRIPTS / "scaffold.py"), "plan",
             "--slug", "cli-demo", "--title", "CLI Demo", "--id", "260618-2251",
             "--root", str(tmp_path), "--print"],
            capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        assert "title:" in proc.stdout
        assert not (tmp_path / "plans").exists()


def _seed_templates(root: Path) -> None:
    """Copy the shipped templates into a tmp root so scaffold reads them there."""
    src = _ROOT / "harness" / "templates"
    dst = root / "harness" / "templates"
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.glob("*.md"):
        (dst / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    # scaffold stamps via artifact_stamp -> harness_release.read_release, which
    # reads the manifest for the kit_digest; a tmp root has none, so it falls
    # back to the dev digest. Provide a minimal release marker is unnecessary.
