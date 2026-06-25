"""Strict parser, registry and bundled-config integrity checks for roles/skills."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from hypothesis import given, strategies as st

from roles.agent import Agent
from roles.lenses import LensRegistry, LensSpec, parse_lens
from roles.registry import AgentRegistry
from roles.spec import RoleSpec, TestOwnership as Ownership, parse_role
from skills.registry import SkillRegistry
from skills.spec import SkillSpec, parse_skill


ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills" / "library"
ROLES_DIR = ROOT / "roles" / "library"
LENSES_DIR = ROLES_DIR / "lenses"


def _libraries():
    skills = SkillRegistry()
    skills.load_dir(SKILLS_DIR)
    lenses = LensRegistry()
    lenses.load_dir(LENSES_DIR)
    roles = AgentRegistry(
        skills=skills,
        lenses=lenses,
        core_tools=frozenset({"fs_read"}),
    )
    roles.load_dir(ROLES_DIR)
    return skills, lenses, roles


@pytest.mark.audit
@pytest.mark.property
@given(
    triggers=st.lists(
        st.text(st.characters(blacklist_categories=("Cs",)), min_size=1, max_size=30).filter(
            lambda value: value.strip()
            and not any(separator in value for separator in ("\n", "\r", "\x85", "\u2028", "\u2029"))
        ),
        unique=True,
        max_size=10,
    )
)
def test_skill_trigger_list_roundtrips_without_loss(triggers):
    frontmatter = yaml.safe_dump(
        {"name": "property", "description": "property skill", "triggers": triggers},
        allow_unicode=True,
        sort_keys=False,
    )
    text = f"---\n{frontmatter}---\n\n## Allowed tools\n- fs_read\n"

    spec = parse_skill(text)

    assert spec.triggers == tuple(item.strip() for item in triggers)


@pytest.mark.audit
def test_skill_parser_accepts_real_utf8_bom():
    text = "\ufeff---\nname: bom\ndescription: bom-safe\n---\n"
    assert parse_skill(text).name == "bom"


@pytest.mark.audit
@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("name: no-frontmatter", "frontmatter"),
        ("---\n- list\n---\n", "mapping"),
        ("---\ndescription: missing name\n---\n", "name"),
        ("---\nname: missing-description\n---\n", "description"),
    ],
)
def test_skill_parser_rejects_each_malformed_schema(text, message):
    with pytest.raises(ValueError, match=message):
        parse_skill(text)


@pytest.mark.audit
def test_skill_registry_rejects_duplicate_names_instead_of_silent_overwrite():
    registry = SkillRegistry()
    registry.register(SkillSpec("same", "first"))
    with pytest.raises(ValueError, match="same"):
        registry.register(SkillSpec("same", "second"))
    assert registry.get("same").description == "first"


@pytest.mark.audit
def test_lens_and_role_registries_reject_duplicate_names():
    lenses = LensRegistry()
    lenses.register(LensSpec("same", "first"))
    with pytest.raises(ValueError, match="same"):
        lenses.register(LensSpec("same", "second"))

    roles = AgentRegistry(skills=SkillRegistry(), lenses=lenses)
    first = RoleSpec("same", "role", "dept", "first")
    roles.register(first)
    with pytest.raises(ValueError, match="same"):
        roles.register(RoleSpec("same", "role", "dept", "second"))
    assert roles.get("same") is first


@pytest.mark.audit
@pytest.mark.parametrize("field", ["name", "role", "department", "system_prompt"])
def test_role_parser_rejects_every_missing_required_field(field):
    data = {"name": "n", "role": "r", "department": "d", "system_prompt": "s"}
    data[field] = "  "
    with pytest.raises(ValueError, match=field):
        parse_role(data, source="audit.yaml")


@pytest.mark.audit
@pytest.mark.parametrize(
    "bad",
    [
        {"route_permissions": "not-a-mapping"},
        {"test_ownership": ["not", "a", "mapping"]},
        {"lenses": 42},
        {"allowed_skills": {"not": "a sequence"}},
    ],
)
def test_role_parser_returns_domain_value_error_for_wrong_container_types(bad):
    data = {"name": "n", "role": "r", "department": "d", "system_prompt": "s", **bad}
    with pytest.raises(ValueError, match="Role.*audit.yaml"):
        parse_role(data, source="audit.yaml")


@pytest.mark.audit
def test_lens_parser_rejects_non_mapping_output_schema():
    with pytest.raises(ValueError, match="output_schema"):
        parse_lens({"name": "lens", "purpose": "p", "output_schema": ["wrong"]})


@pytest.mark.audit
@pytest.mark.security
def test_role_allowlist_is_union_minus_forbidden_with_forbidden_winning():
    skills = SkillRegistry()
    skills.register(
        SkillSpec(
            "restricted",
            "contract",
            allowed_tools=("from_skill", "blocked", "core"),
            forbidden_tools=("blocked", "core"),
        )
    )
    spec = RoleSpec(
        "role",
        "worker",
        "engineering",
        "system",
        explicit_tools=("explicit", "blocked"),
        allowed_skills=("restricted",),
    )

    allowed = spec.allowed_tools(skills, frozenset({"core", "core_only"}))

    assert allowed == frozenset({"explicit", "from_skill", "core_only"})


@pytest.mark.audit
def test_agent_prompt_uses_contract_disclosure_not_skill_procedure():
    skills = SkillRegistry()
    skills.register(
        SkillSpec(
            "skill",
            "description",
            allowed_tools=("read",),
            steps_md="SECRET FULL STEPS",
            report_md="SECRET REPORT FORMAT",
        )
    )
    lenses = LensRegistry()
    lenses.register(LensSpec("correctness", "Find correctness issues."))
    spec = RoleSpec(
        "role",
        "worker",
        "engineering",
        "SYSTEM SENTINEL",
        allowed_skills=("skill",),
        lenses=("correctness",),
    )

    prompt = Agent(spec, skills=skills, lenses=lenses).build_prompt()

    assert prompt.startswith("SYSTEM SENTINEL\n")
    assert "### Lens: correctness" in prompt
    assert "## Allowed tools\n- read" in prompt
    assert "## skill" in prompt and "description" in prompt
    assert "SECRET FULL STEPS" not in prompt
    assert "SECRET REPORT FORMAT" not in prompt


@pytest.mark.audit
def test_separation_of_duties_requires_concrete_handoff_target():
    spec = RoleSpec(
        "unsafe",
        "coder",
        "engineering",
        "system",
        test_ownership=Ownership(owns_validation=False, must_handoff_to=None),
    )
    with pytest.raises(ValueError, match="must_handoff_to"):
        Agent(spec, skills=SkillRegistry(), lenses=LensRegistry())


@pytest.mark.audit
def test_bundled_role_skill_lens_references_and_routes_are_closed_world():
    skills, lenses, roles = _libraries()
    errors = []
    for role_name in roles.names():
        spec = roles.get(role_name)
        errors.extend(f"{role_name}: missing skill {name}" for name in spec.allowed_skills if name not in skills)
        errors.extend(f"{role_name}: missing lens {name}" for name in spec.lenses if name not in lenses)
        errors.extend(f"{role_name}: missing route target {name}" for name in spec.may_route_to if name not in roles)
        if not spec.test_ownership.owns_validation:
            target = spec.test_ownership.must_handoff_to
            if not target:
                errors.append(f"{role_name}: validation handoff target is empty")
            elif target not in roles:
                errors.append(f"{role_name}: missing validation handoff target {target}")
            elif target not in spec.may_route_to:
                errors.append(f"{role_name}: validation target {target} is not routable")

    assert errors == []


@pytest.mark.audit
def test_bundled_skill_tool_names_are_known_to_runtime():
    skills, _, _ = _libraries()
    known = {"fs_read", "fs_write", "fs_list", "terminal_run", "echo", "llm.chat"}
    assert skills.lint(known.__contains__) == {}
