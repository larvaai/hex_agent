"""Bundled lens catalog loads cleanly and references only real hex tools. Epic E09."""
from __future__ import annotations

from pathlib import Path

import pytest

from roles.lenses import LensRegistry
from toolbox.feature import FEATURE

LENS_DIR = Path(__file__).resolve().parent.parent / "roles" / "library" / "lenses"
KNOWN_TOOLS = set(FEATURE.capabilities)


@pytest.fixture(scope="module")
def loaded():
    registry = LensRegistry()
    specs = registry.load_dir(LENS_DIR)
    return registry, specs


def test_catalog_is_substantial(loaded):
    _, specs = loaded
    assert len(specs) >= 40  # 2 original + ~43 ported viewpoints


def test_all_lens_names_unique(loaded):
    _, specs = loaded
    names = [s.name for s in specs]
    assert len(names) == len(set(names))


def test_every_referenced_tool_exists_in_hex(loaded):
    _, specs = loaded
    unknown: dict[str, set[str]] = {}
    for spec in specs:
        refs = set(spec.allowed_tools) | set(spec.forbidden_tools)
        missing = refs - KNOWN_TOOLS
        if missing:
            unknown[spec.name] = missing
    assert not unknown, f"lenses reference unknown tools: {unknown}"


def test_every_lens_has_purpose_and_renders(loaded):
    registry, specs = loaded
    for spec in specs:
        assert spec.purpose.strip()
        rendered = registry.render(spec.name)
        assert spec.name in rendered


def test_catalog_carries_real_tool_scoping_and_schema(loaded):
    """Guard against filler: most ported lenses must declare tools AND an output schema."""
    _, specs = loaded
    fully_populated = [s for s in specs if s.purpose and s.allowed_tools and s.output_schema]
    assert len(fully_populated) >= 40
