"""test_output_config.py — loader for harness/data/output.yaml.

The output config governs the language of harness-GENERATED prose (reports,
docs) and whether the humanizer rule is applied. Instruction files are English;
this setting picks the OUTPUT language (default Vietnamese for this harness).

One shared loader, mirroring team_config: no env override (the setting is
tracked config, a change is a git-visible diff), loud on missing/malformed,
language constrained to the en/vi enum.
"""
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from output_config import (  # noqa: E402
    OutputConfigError,
    language,
    load_output,
)


def _write(tmp_path, text):
    p = tmp_path / "output.yaml"
    p.write_text(text, encoding="utf-8")
    return p


class TestLoadOutput:
    def test_valid_file_parses(self, tmp_path):
        p = _write(tmp_path, "language: vi\nhumanize: true\n")
        cfg = load_output(path=str(p))
        assert cfg == {"language": "vi", "humanize": True}

    def test_english_is_valid(self, tmp_path):
        p = _write(tmp_path, "language: en\nhumanize: false\n")
        cfg = load_output(path=str(p))
        assert cfg["language"] == "en"
        assert cfg["humanize"] is False

    def test_humanize_defaults_true_when_absent(self, tmp_path):
        p = _write(tmp_path, "language: vi\n")
        assert load_output(path=str(p))["humanize"] is True

    def test_invalid_language_rejected(self, tmp_path):
        p = _write(tmp_path, "language: fr\n")
        with pytest.raises(OutputConfigError, match="language"):
            load_output(path=str(p))

    def test_non_bool_humanize_rejected(self, tmp_path):
        p = _write(tmp_path, "language: vi\nhumanize: maybe\n")
        with pytest.raises(OutputConfigError, match="humanize"):
            load_output(path=str(p))

    def test_missing_file_is_actionable(self, tmp_path):
        with pytest.raises(OutputConfigError, match="output.yaml|output config"):
            load_output(path=str(tmp_path / "nope.yaml"))

    def test_non_mapping_rejected(self, tmp_path):
        p = _write(tmp_path, "- just\n- a\n- list\n")
        with pytest.raises(OutputConfigError, match="mapping"):
            load_output(path=str(p))


class TestLanguageConvenience:
    def test_language_returns_string(self, tmp_path):
        p = _write(tmp_path, "language: en\n")
        assert language(path=str(p)) == "en"

    def test_shipped_default_is_vietnamese(self):
        # The tracked harness/data/output.yaml defaults the harness to Vietnamese
        # output — instructions are English, generated prose is Vietnamese.
        assert language() == "vi"
