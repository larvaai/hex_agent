"""Phase C acceptance: post-move topology invariants for the decomposition.

After the real migration runs, the 38 non-spine skills must live under their themed
sibling plugin (dir + frontmatter name carry the new prefix), the 13 spine skills must
stay in `hs` unchanged, and no shipped file may carry an old-form reference.

This test reads the canonical map and derives the expected names, so it stays valid
through the migration itself (it never hard-codes an `hs:<skill>` literal that the
migrator would rewrite).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness" / "scripts"))
import migrate_decomposition as md  # noqa: E402

MAP = md.load_map(ROOT / "harness/data/decomposition-map.yaml")
SPINE = md.spine_skills(MAP)
NON_SPINE = md.non_spine_skills(MAP)
PLUG = ROOT / "harness/plugins"


def _name_line(skill_md: Path) -> str:
    for line in skill_md.read_text().splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip()
    return ""


def test_non_spine_skills_moved_to_themed_plugins():
    for skill, group in NON_SPINE.items():
        new_dir = PLUG / f"hs-{group}/skills/{skill}"
        old_dir = PLUG / f"hs/skills/{skill}"
        assert new_dir.is_dir(), f"{skill} not moved into hs-{group}"
        assert not old_dir.exists(), f"{skill} still under spine hs/"


def test_non_spine_frontmatter_carries_new_prefix():
    for skill, group in NON_SPINE.items():
        md_file = PLUG / f"hs-{group}/skills/{skill}/SKILL.md"
        assert md_file.is_file(), f"{skill} SKILL.md missing"
        assert _name_line(md_file) == f"hs-{group}:{skill}", \
            f"{skill} frontmatter name not rebranded"


def test_spine_skills_unchanged():
    for skill in SPINE:
        md_file = PLUG / f"hs/skills/{skill}/SKILL.md"
        assert md_file.is_file(), f"spine {skill} missing from hs/"
        assert _name_line(md_file) == f"hs:{skill}", \
            f"spine {skill} frontmatter name should stay hs:{skill}"


def test_no_old_form_refs_remain_in_shipped_tree():
    # --check scans the whole tree (minus manifest, rename-map, plans/) for any
    # surviving slash/bare/path old-form reference to a moved skill.
    assert md.run_migrate(root=ROOT, do_check=True) == 0


def test_every_skill_resolves_to_a_real_dir():
    # Build the live catalog of invoke-name -> dir from every plugin's frontmatter,
    # then assert no shipped skill/rule/agent file references an hs-<group>:<skill>
    # that does not resolve.
    catalog = set()
    for skill_md in PLUG.glob("hs*/skills/*/SKILL.md"):
        name = _name_line(skill_md)
        if name:
            catalog.add(name)
    # references of the form hs-<group>:<token> in the shipped instruction tree
    ref_re = re.compile(r"(?<![\w-])hs-[a-z]+:[a-z][\w-]*")
    scan_roots = [PLUG, ROOT / "harness/rules", ROOT / "harness/agents"]
    unresolved = []
    for base in scan_roots:
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix not in {".md", ".yaml", ".yml"}:
                continue
            for m in ref_re.findall(p.read_text(errors="ignore")):
                if m not in catalog:
                    unresolved.append((p.relative_to(ROOT).as_posix(), m))
    # de-dup; allow known non-skill hs-<group>:<agent> spawn names to be filtered by
    # catalog membership — anything left is a genuinely dangling skill ref.
    assert not unresolved, f"unresolved themed refs: {sorted(set(unresolved))[:20]}"
