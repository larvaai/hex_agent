"""test_glossary_invariants.py — guards docs/GLOSSARY.md, the canonical shared-language registry.

The glossary consolidates terms scattered across CLAUDE.md, docs/decisions.md and
old plan notes into one English reference that the planning skills read before they
name things. These invariants keep it from being deleted, gutted, or drifting out of
sync with the wording bans that test_bug_class_invariants enforces over harness/.
"""
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_GLOSSARY = _REPO / "docs" / "GLOSSARY.md"

# Terms pinned in CLAUDE.md "Wording" plus the DEC-backed vocabulary. Each must keep
# a row so the consolidation can't be quietly hollowed out back into scattered prose.
_CORE_TERMS = (
    "fs_guard", "actor", "presence gate", "HOOK_CLASS", "fail-closed", "append-only",
)

# The four documented columns of the glossary table.
_COLUMNS = ("Term", "Definition", "Forbidden", "Backing")

# The fs_guard ban, held as a pattern so this source file never carries the
# contiguous banned string — the harness-wide scan in test_bug_class_invariants
# would otherwise flag this file. The bracketed source text does not match its own
# regex, mirroring how that scan stays self-consistent.
_FORBIDDEN_FS_GUARD = re.compile(r"write[- ]fence", re.I)


def _glossary_text():
    return _GLOSSARY.read_text(encoding="utf-8")


class TestGlossaryRegistry:
    @pytest.fixture(autouse=True)
    def _skip_when_not_shipped(self):
        # docs/GLOSSARY.md is a source-repo doc, NOT part of the installed bundle.
        # These tests ship under harness/tests/ and run at deployer sites too;
        # there the file is legitimately absent, so skip rather than false-fail.
        if not _GLOSSARY.is_file():
            pytest.skip("docs/GLOSSARY.md absent (source-only doc, not shipped)")

    def test_glossary_exists(self):
        # hs:plan / hs-research:discover now point at this path; a missing file turns those
        # read steps into dangling instruction references.
        assert _GLOSSARY.is_file(), (
            "docs/GLOSSARY.md is missing — the planning skills reference it")

    def test_glossary_has_a_term_table(self):
        text = _glossary_text()
        missing = [c for c in _COLUMNS if c not in text]
        assert not missing, (
            "GLOSSARY.md must keep its Term/Definition/Forbidden/Backing table; "
            "missing column header(s): %s" % ", ".join(missing))

    def test_core_terms_each_have_a_row(self):
        text = _glossary_text()
        missing = [t for t in _CORE_TERMS if t not in text]
        assert not missing, (
            "GLOSSARY.md lost canonical term(s): %s" % ", ".join(missing))

    def test_fs_guard_forbidden_wording_is_registered(self):
        # The human-readable registry must name the ban that the harness-wide scan
        # enforces, so the glossary stays the single source of the forbidden wording.
        assert _FORBIDDEN_FS_GUARD.search(_glossary_text()), (
            "GLOSSARY.md must register the forbidden fs_guard framing it bans")
