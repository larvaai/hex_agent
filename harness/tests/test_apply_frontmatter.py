"""test_apply_frontmatter.py — additive frontmatter rollout (P3a).

apply_frontmatter fills the missing SKILL.md frontmatter fields the schema declares
(category, license, keywords, when_to_use, argument-hint) WITHOUT overwriting anything
already authored and WITHOUT touching allowed-tools (deferred — restricting tools is a
breakage risk handled separately). Derived fields come from the skill's OWN already-authored
name + description (no fabricated content). Insertion is textual, after the `description:`
line, so an existing `metadata:` block and exact formatting survive untouched. Idempotent.
"""
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO / "harness" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import apply_frontmatter as af  # noqa: E402
import yaml  # noqa: E402


# ---- derivation (from the skill's own content) ------------------------------

def test_derive_keywords_from_name_and_description():
    kws = af.derive_keywords("hs:cook", "Execute an approved plan phase by phase via TDD.")
    assert isinstance(kws, list) and 1 <= len(kws) <= 8
    assert all(isinstance(k, str) and k for k in kws)
    # stopwords must not appear
    assert "an" not in kws and "by" not in kws


def test_derive_when_to_use_prefers_trigger_clause():
    wtu = af.derive_when_to_use("Brainstorm solutions. Use before committing to an approach.")
    assert "Use before committing" in wtu


def test_derive_when_to_use_falls_back_to_first_sentence():
    wtu = af.derive_when_to_use("Stage and commit changes with conventional commits.")
    assert wtu  # non-empty even without an explicit trigger clause


# ---- compute_missing: only fills gaps, never allowed-tools ------------------

def test_native_gets_agpl_and_group_category():
    fm = {"name": "hs:cook", "description": "Execute a plan. Use when ready."}
    add = af.compute_missing(fm, is_native=True, group="hs", plugin="hs")
    assert add["license"] == "AGPL-3.0"
    assert add["category"] == "core"           # spine group "hs" -> "core"
    assert "keywords" in add and "when_to_use" in add
    assert "allowed-tools" not in add          # deferred, never auto-set here


def test_ckport_gets_mit_and_plugin_category():
    fm = {"name": "hs-viz:diagram", "description": "Draw diagrams. Use for charts."}
    add = af.compute_missing(fm, is_native=False, group=None, plugin="hs-viz")
    assert add["license"] == "MIT"
    assert add["category"]                      # some non-empty functional label


def test_does_not_overwrite_existing_fields():
    fm = {"name": "hs:x", "description": "Do. Use when.",
          "category": "custom", "license": "MIT", "keywords": ["kept"]}
    add = af.compute_missing(fm, is_native=True, group="think", plugin="hs-think")
    assert "category" not in add and "license" not in add and "keywords" not in add


# ---- textual insertion preserves the rest of the frontmatter ----------------

_SKILL = """---
name: hs:demo
description: Demo skill. Use when demoing.
user-invocable: true
metadata:
  owner: harness
  compliance-tier: workflow
---

# body
"""


def test_insert_after_description_keeps_metadata_valid(tmp_path):
    add = {"category": "core", "license": "AGPL-3.0", "keywords": ["demo"],
           "when_to_use": "Use when demoing."}
    out = af.insert_after_description(_SKILL, add)
    # frontmatter still parses and metadata block survived as a nested mapping
    fm = yaml.safe_load(out.split("---", 2)[1])
    assert fm["category"] == "core" and fm["license"] == "AGPL-3.0"
    assert fm["metadata"]["owner"] == "harness"   # not clobbered / not re-nested
    assert fm["name"] == "hs:demo"


_FOLDED = """---
name: hs-meta:demo
description: >-
  Manage the context budget — check limits, optimize tokens.
  Use when context is nearly full.
user-invocable: true
metadata:
  owner: harness
---

# body
"""


def test_insert_handles_folded_multiline_description():
    # the new keys must land AFTER the whole folded scalar, not split it
    add = {"category": "meta", "license": "AGPL-3.0", "keywords": ["context"]}
    out = af.insert_after_description(_FOLDED, add)
    fm = yaml.safe_load(out.split("---", 2)[1])
    assert fm["category"] == "meta"
    assert "Manage the context budget" in fm["description"]
    assert "Use when context is nearly full" in fm["description"]
    assert fm["metadata"]["owner"] == "harness"


def test_apply_is_idempotent(tmp_path):
    p = tmp_path / "SKILL.md"
    p.write_text(_SKILL, encoding="utf-8")
    af.apply_to_file(p, is_native=True, group="hs", plugin="hs")
    first = p.read_text(encoding="utf-8")
    af.apply_to_file(p, is_native=True, group="hs", plugin="hs")
    assert p.read_text(encoding="utf-8") == first  # second run is a no-op
