"""Rigorous audit of roles/ — lens/spec parsing, allowlist enforcement, registry as the single store, round-trip invariants.

Complements tests/test_roles.py (happy-path AC map) and
tests_audit/test_roles_skills_config_integrity.py (bundled-config closure,
duplicate-name rejection, wrong-container types). Here we target the *uncovered*
branches and push adversarial/boundary/property rigor:

  - parse_lens error paths (non-mapping, missing name, missing purpose) and the
    string-coercion branch of roles' _as_tuple / lenses._as_tuple.
  - LensSpec.render determinism + LensRegistry.get-unknown KeyError.
  - Agent enforces *only* the RoleSpec-derived allowlist: a lens or skill that
    names a capability never widens it (forbidden-wins; lens tools never enter).
  - AgentRegistry is one shared store: register/lookup, duplicate, unknown,
    and the single-definition / two-paths guarantee (build_agent vs role_view).
  - Property: any well-formed RoleSpec round-trips spec -> yaml -> parse_role and
    role_view is a faithful narrowing of the same single source.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings, strategies as st

import roles as roles_pkg
import skills as skills_pkg
from roles.agent import Agent
from roles.lenses import LensRegistry, LensSpec, parse_lens
from roles.lenses import _as_tuple as lens_as_tuple
from roles.registry import AgentRegistry
from roles.spec import (
    RoleSpec,
    RoleView,
    parse_role,
)
from roles.spec import TestOwnership as Ownership  # alias dodges pytest Test* collection
from roles.spec import _as_tuple as role_as_tuple
from skills.registry import SkillRegistry
from skills.spec import SkillSpec

ROOT = Path(roles_pkg.__file__).resolve().parent
LIBRARY = ROOT / "library"
LENSES_DIR = LIBRARY / "lenses"
SKILLS_LIBRARY = Path(skills_pkg.__file__).resolve().parent / "library"

# Free text for property tests, minus YAML/`splitlines()` line-separator control chars
# (\n \r \x85 \u2028 \u2029) — those do not survive a yaml dump/load round-trip and
# would split a rendered single line, which is a generator artefact, not a source bug.
_LINE_SEPS = ("\n", "\r", "\x85", "\u2028", "\u2029")


def _safe_text(max_size: int):
    return st.text(
        st.characters(blacklist_categories=("Cs",)), min_size=1, max_size=max_size
    ).filter(lambda s: s.strip() and not any(sep in s for sep in _LINE_SEPS))



# -- shared builders ----------------------------------------------------------
def _make_registry(*, core_tools=frozenset()) -> AgentRegistry:
    skills = SkillRegistry()
    skills.load_dir(SKILLS_LIBRARY)
    lenses = LensRegistry()
    lenses.load_dir(LENSES_DIR)
    reg = AgentRegistry(skills=skills, lenses=lenses, core_tools=core_tools)
    reg.load_dir(LIBRARY)
    return reg


# =============================================================================
# parse_lens -- error & coercion branches (lenses.py 39, 45, 49, 51)
# =============================================================================
@pytest.mark.audit
def test_parse_lens_rejects_non_mapping():
    """A YAML list/scalar instead of a mapping must fail with the source named (line 45)."""
    with pytest.raises(ValueError, match="must be a YAML mapping"):
        parse_lens(["not", "a", "mapping"], source="bad.yaml")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="bad.yaml"):
        parse_lens("scalar", source="bad.yaml")  # type: ignore[arg-type]


@pytest.mark.audit
@pytest.mark.parametrize(
    ("data", "needle"),
    [
        ({"purpose": "p"}, "missing required field 'name'"),       # line 49
        ({"name": "  ", "purpose": "p"}, "name"),                   # blank name -> stripped empty
        ({"name": "lens"}, "missing required field 'purpose'"),     # line 51
        ({"name": "lens", "purpose": "   "}, "purpose"),            # blank purpose
    ],
)
def test_parse_lens_rejects_missing_or_blank_required_fields(data, needle):
    with pytest.raises(ValueError, match=needle):
        parse_lens(data)


@pytest.mark.audit
def test_parse_lens_purpose_error_names_the_lens_not_the_source():
    """When name is present but purpose missing, the message uses the lens name (line 51)."""
    with pytest.raises(ValueError, match="Lens 'security' is missing required field 'purpose'"):
        parse_lens({"name": "security"})


@pytest.mark.audit
def test_parse_lens_scalar_tool_fields_coerce_to_single_tuple():
    """allowed/forbidden given as a bare string take the non-empty-string branch (lenses.py 39)."""
    spec = parse_lens(
        {
            "name": "x",
            "purpose": "p",
            "allowed_tools": "  fs_read  ",   # scalar -> ("fs_read",)
            "forbidden_tools": "",            # blank scalar -> ()
        }
    )
    assert spec.allowed_tools == ("fs_read",)
    assert spec.forbidden_tools == ()


@pytest.mark.audit
def test_parse_lens_strips_and_drops_blank_list_entries():
    spec = parse_lens(
        {"name": "x", "purpose": "p", "allowed_tools": [" a ", "", "  ", "b"]}
    )
    assert spec.allowed_tools == ("a", "b")


@pytest.mark.audit
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ()),
        ("", ()),
        ("   ", ()),
        ("solo", ("solo",)),
        (" pad ", ("pad",)),
        (["a", " b ", "", 3], ("a", "b", "3")),  # non-str coerced via str()
    ],
)
def test_lens_and_role_as_tuple_agree_on_coercion(value, expected):
    """Both _as_tuple helpers (lenses.py 35-40, spec.py 66-71 incl. line 70) coerce identically."""
    assert lens_as_tuple(value) == role_as_tuple(value) == expected


# =============================================================================
# LensSpec.render -- deterministic projection into a prompt
# =============================================================================
@pytest.mark.audit
def test_lens_render_is_deterministic_and_sorts_schema_keys():
    """render() must be order-stable: schema keys sorted, identical across calls (S09.5)."""
    spec = LensSpec(
        name="correctness",
        purpose="Find logic errors.",
        allowed_tools=("fs_read",),
        forbidden_tools=("fs_write",),
        output_schema={"verdict": "string", "issues": "list", "aaa": "x"},
    )
    out1 = spec.render()
    out2 = spec.render()
    assert out1 == out2
    assert out1.splitlines()[0] == "### Lens: correctness"
    assert "allowed: fs_read" in out1
    assert "forbidden: fs_write" in out1
    # keys are sorted regardless of insertion order
    assert "output_schema: {aaa, issues, verdict}" in out1


@pytest.mark.audit
def test_lens_render_omits_empty_optional_blocks():
    """A minimal lens renders just the header + purpose, no stray allowed/forbidden/schema lines."""
    spec = LensSpec(name="bare", purpose="just a purpose")
    out = spec.render()
    assert out == "### Lens: bare\njust a purpose"
    assert "allowed:" not in out and "forbidden:" not in out and "output_schema" not in out


@pytest.mark.audit
@pytest.mark.property
@settings(max_examples=60)
@given(
    name=_safe_text(20),
    purpose=_safe_text(40),
    schema_keys=st.sets(_safe_text(8), max_size=5),
)
def test_lens_render_schema_keys_always_sorted(name, purpose, schema_keys):
    """Property: rendered schema keys are exactly sorted(keys) -- no dict-order leak."""
    schema = {k: "v" for k in schema_keys}
    out = LensSpec(name=name, purpose=purpose, output_schema=schema).render()
    if schema:
        rendered = out.splitlines()[-1]
        assert rendered == "output_schema: {" + ", ".join(sorted(schema)) + "}"
    else:
        assert "output_schema" not in out


# =============================================================================
# LensRegistry.get / render -- unknown name (lenses.py 85-87)
# =============================================================================
@pytest.mark.audit
def test_lens_registry_unknown_name_lists_known():
    """get() of an unknown lens raises KeyError naming the known set (lines 85-87)."""
    reg = LensRegistry()
    reg.register(LensSpec("alpha", "a"))
    reg.register(LensSpec("beta", "b"))
    with pytest.raises(KeyError, match="Unknown lens 'gamma'"):
        reg.get("gamma")
    # known-lens list is sorted and present in the message (render -> get)
    with pytest.raises(KeyError, match="alpha, beta"):
        reg.render("zzz")


@pytest.mark.audit
def test_empty_lens_registry_get_reports_none_known():
    reg = LensRegistry()
    with pytest.raises(KeyError, match=r"Known lenses: \(none\)"):
        reg.get("any")
    assert ("any" in reg) is False


@pytest.mark.audit
def test_lens_registry_load_dir_is_sorted_and_rejects_reload():
    """load_dir over the bundled lenses registers each once; a reload trips the dup guard."""
    reg = LensRegistry()
    loaded = reg.load_dir(LENSES_DIR)
    names = [s.name for s in loaded]
    assert names == sorted(names)  # deterministic order from sorted(glob)
    assert "correctness" in reg and "requirements" in reg
    with pytest.raises(ValueError, match="already registered"):
        reg.load_dir(LENSES_DIR)


# =============================================================================
# parse_role -- non-mapping top-level (spec.py 93) + coercion (spec.py 70)
# =============================================================================
@pytest.mark.audit
def test_parse_role_rejects_non_mapping_top_level():
    """A non-dict role document fails fast naming the source (spec.py line 93)."""
    with pytest.raises(ValueError, match="Role 'roles.yaml' must be a YAML mapping"):
        parse_role(["a", "list"], source="roles.yaml")  # type: ignore[arg-type]


@pytest.mark.audit
def test_parse_role_scalar_sequence_fields_coerce():
    """Scalar allowed_tools/allowed_skills/lenses take the string branch (spec.py line 70)."""
    spec = parse_role(
        {
            "name": "n",
            "role": "r",
            "department": "d",
            "system_prompt": "s",
            "allowed_tools": "fs_read",        # scalar -> ("fs_read",)
            "allowed_skills": "  file_edit ",  # scalar w/ padding -> ("file_edit",)
            "lenses": "correctness",
            "route_permissions": {"may_route_to": "test"},  # nested scalar too
        }
    )
    assert spec.explicit_tools == ("fs_read",)
    assert spec.allowed_skills == ("file_edit",)
    assert spec.lenses == ("correctness",)
    assert spec.may_route_to == ("test",)


@pytest.mark.audit
def test_parse_role_blank_scalar_sequence_fields_become_empty():
    spec = parse_role(
        {
            "name": "n",
            "role": "r",
            "department": "d",
            "system_prompt": "s",
            "allowed_tools": "   ",   # blank scalar -> ()
            "lenses": None,
        }
    )
    assert spec.explicit_tools == ()
    assert spec.lenses == ()


@pytest.mark.audit
def test_parse_role_strips_required_fields():
    """Required fields are .strip()'d into the canonical spec, not stored with whitespace."""
    spec = parse_role(
        {"name": " n ", "role": " r ", "department": " d ", "system_prompt": "  s  "}
    )
    assert (spec.name, spec.role, spec.department, spec.system_prompt) == ("n", "r", "d", "s")


@pytest.mark.audit
def test_parse_role_test_ownership_falsy_handoff_becomes_none():
    """An explicitly FALSY must_handoff_to (None/0/''/[]) collapses to None (spec.py 111)."""
    for falsy in (None, 0, "", []):
        spec = parse_role(
            {
                "name": "n",
                "role": "r",
                "department": "d",
                "system_prompt": "s",
                "test_ownership": {"owns_validation": True, "must_handoff_to": falsy},
            }
        )
        assert spec.test_ownership.must_handoff_to is None


@pytest.mark.audit
def test_parse_role_whitespace_handoff_strips_to_empty_string_not_none():
    """Edge quirk pinned honestly: a WHITESPACE-only must_handoff_to is truthy, so spec.py 111
    takes the .strip() branch and yields '' (NOT None). Both still read as 'no target' at the
    Agent guard, so it is a representation quirk, not an exploitable hole -- we assert the real
    behaviour and prove the Agent still refuses to build such a non-owner role."""
    spec = parse_role(
        {
            "name": "n",
            "role": "r",
            "department": "d",
            "system_prompt": "s",
            "test_ownership": {"owns_validation": False, "must_handoff_to": "   "},
        }
    )
    assert spec.test_ownership.must_handoff_to == ""   # NOT None -- the truthy/.strip() path
    # the empty target is still rejected at construction (separation-of-duties floor holds)
    with pytest.raises(ValueError, match="declares no 'must_handoff_to'"):
        Agent(spec, skills=SkillRegistry(), lenses=LensRegistry())


# =============================================================================
# Agent -- allowlist enforcement is RoleSpec-derived ONLY (adversarial)
# =============================================================================
@pytest.mark.audit
@pytest.mark.security
def test_lens_naming_a_tool_does_not_widen_the_agent_allowlist():
    """Adversarial: a lens advertises 'danger_tool' in its allowed_tools, but lenses never
    feed the runtime allowlist -- guard_tool_call must still BLOCK that capability."""
    lenses = LensRegistry()
    lenses.register(
        LensSpec("sneaky", "tries to smuggle a tool", allowed_tools=("danger_tool",))
    )
    spec = RoleSpec(
        "victim",
        "worker",
        "engineering",
        "system",
        explicit_tools=("fs_read",),
        lenses=("sneaky",),
    )
    agent = Agent(spec, skills=SkillRegistry(), lenses=lenses)
    assert agent.is_tool_allowed("danger_tool") is False
    blocker = agent.guard_tool_call("danger_tool")
    assert blocker is not None and blocker["blocked_tool"] == "danger_tool"
    # the lens still renders into the prompt (transparency), but grants no capability
    assert "danger_tool" in agent.build_prompt()
    assert "danger_tool" not in agent.allowed_tools


@pytest.mark.audit
@pytest.mark.security
def test_skill_forbidden_tool_cannot_be_re_granted_by_core_or_explicit():
    """forbidden-wins holds even when the same tool is in core_tools AND explicit_tools."""
    skills = SkillRegistry()
    skills.register(
        SkillSpec("locked", "c", allowed_tools=("safe",), forbidden_tools=("nuke",))
    )
    spec = RoleSpec(
        "r", "w", "e", "s",
        explicit_tools=("nuke", "safe"),
        allowed_skills=("locked",),
    )
    agent = Agent(spec, skills=skills, lenses=LensRegistry(), core_tools=frozenset({"nuke"}))
    assert "nuke" not in agent.allowed_tools           # forbidden beats explicit AND core
    assert agent.guard_tool_call("nuke") is not None
    assert {"safe"} <= agent.allowed_tools


@pytest.mark.audit
@pytest.mark.security
def test_guard_tool_call_blocker_carries_route_targets_and_role_name():
    spec = RoleSpec(
        "code", "w", "e", "s",
        explicit_tools=("fs_read",),
        may_route_to=("test", "reviewer"),
    )
    agent = Agent(spec, skills=SkillRegistry(), lenses=LensRegistry())
    blocker = agent.guard_tool_call("git_push")
    assert blocker == {
        "finish_reason": "blocker",
        "blocked_tool": "git_push",
        "reason": "Tool 'git_push' is outside role 'code' allowlist.",
        "may_route_to": ["test", "reviewer"],
    }
    # may_route_to is a fresh list -- mutating it must not corrupt the spec's tuple
    blocker["may_route_to"].append("evil")
    assert agent.spec.may_route_to == ("test", "reviewer")


@pytest.mark.audit
def test_agent_in_scope_tool_passes_guard():
    spec = RoleSpec("r", "w", "e", "s", explicit_tools=("fs_read",))
    agent = Agent(spec, skills=SkillRegistry(), lenses=LensRegistry())
    assert agent.guard_tool_call("fs_read") is None


@pytest.mark.audit
def test_agent_rejects_non_owner_without_handoff_target():
    """Construction-time separation-of-duties guard (agent.py 31-34)."""
    spec = RoleSpec(
        "bad", "w", "e", "s",
        test_ownership=Ownership(owns_validation=False, must_handoff_to=None),
    )
    with pytest.raises(ValueError, match="does not own validation but declares no 'must_handoff_to'"):
        Agent(spec, skills=SkillRegistry(), lenses=LensRegistry())


@pytest.mark.audit
def test_guard_finish_forces_handoff_for_non_owner_validation_claim():
    spec = RoleSpec(
        "code", "w", "e", "s",
        test_ownership=Ownership(owns_validation=False, must_handoff_to="test"),
    )
    agent = Agent(spec, skills=SkillRegistry(), lenses=LensRegistry())
    out = agent.guard_finish(claim_validated=True)
    assert out == {
        "finish_reason": "blocker",
        "reason": "Role 'code' does not own validation; must hand off to 'test'.",
        "handoff_to": "test",
    }
    # finishing WITHOUT a validation claim is permitted
    assert agent.guard_finish(claim_validated=False) is None


@pytest.mark.audit
def test_guard_finish_owner_may_self_validate():
    spec = RoleSpec("test", "w", "e", "s", test_ownership=Ownership(owns_validation=True))
    agent = Agent(spec, skills=SkillRegistry(), lenses=LensRegistry())
    assert agent.guard_finish(claim_validated=True) is None


@pytest.mark.audit
def test_agent_prompt_zero_tools_renders_explicit_none_and_no_leak():
    """An allowlist-free role prints '- (none)' and no tool catalog (S09.5)."""
    spec = RoleSpec("ba", "analyst", "product", "SYS")
    agent = Agent(spec, skills=SkillRegistry(), lenses=LensRegistry())
    prompt = agent.build_prompt()
    assert agent.allowed_tools == frozenset()
    assert "## Allowed tools\n- (none)" in prompt
    assert prompt.startswith("SYS\n")
    assert prompt.endswith("\n")


@pytest.mark.audit
def test_agent_prompt_injects_skill_contract_not_full_steps():
    """build_prompt appends each allowed skill's CONTRACT block (agent.py 82-83) — but the
    skill's Steps/Report stay withheld (progressive disclosure: contract mode only)."""
    skills = SkillRegistry()
    skills.register(
        SkillSpec(
            "file_edit",
            "edit files carefully",
            allowed_tools=("fs_write",),
            steps_md="DO NOT LEAK THESE STEPS",
            report_md="DO NOT LEAK THIS REPORT",
        )
    )
    spec = RoleSpec("code", "w", "e", "SYS", allowed_skills=("file_edit",))
    prompt = Agent(spec, skills=skills, lenses=LensRegistry()).build_prompt()
    assert "## file_edit" in prompt and "edit files carefully" in prompt
    assert "DO NOT LEAK THESE STEPS" not in prompt
    assert "DO NOT LEAK THIS REPORT" not in prompt


@pytest.mark.audit
def test_agent_prompt_lists_tools_sorted():
    spec = RoleSpec("r", "w", "e", "s", explicit_tools=("z_tool", "a_tool", "m_tool"))
    agent = Agent(spec, skills=SkillRegistry(), lenses=LensRegistry())
    block = agent.build_prompt()
    idx = block.index("## Allowed tools")
    tail = block[idx:]
    assert tail.index("- a_tool") < tail.index("- m_tool") < tail.index("- z_tool")


# =============================================================================
# AgentRegistry -- the single shared store
# =============================================================================
@pytest.mark.audit
def test_registry_register_lookup_and_membership():
    reg = AgentRegistry(skills=SkillRegistry(), lenses=LensRegistry())
    spec = RoleSpec("solo", "w", "e", "s")
    assert reg.register(spec) is spec
    assert reg.get("solo") is spec
    assert "solo" in reg
    assert reg.names() == ("solo",)


@pytest.mark.audit
def test_registry_rejects_duplicate_role_id():
    reg = AgentRegistry(skills=SkillRegistry(), lenses=LensRegistry())
    first = RoleSpec("dup", "w", "e", "first")
    reg.register(first)
    with pytest.raises(ValueError, match="Role 'dup' is already registered"):
        reg.register(RoleSpec("dup", "w", "e", "second"))
    # original definition is untouched (no silent overwrite)
    assert reg.get("dup") is first


@pytest.mark.audit
def test_registry_unknown_role_lists_known_sorted():
    reg = AgentRegistry(skills=SkillRegistry(), lenses=LensRegistry())
    reg.register(RoleSpec("beta", "w", "e", "s"))
    reg.register(RoleSpec("alpha", "w", "e", "s"))
    with pytest.raises(KeyError, match="Unknown role 'ghost'"):
        reg.get("ghost")
    with pytest.raises(KeyError, match="alpha, beta"):  # names() is sorted
        reg.get("ghost")


@pytest.mark.audit
def test_registry_names_sorted_regardless_of_insertion_order():
    reg = AgentRegistry(skills=SkillRegistry(), lenses=LensRegistry())
    for n in ("m", "z", "a", "k"):
        reg.register(RoleSpec(n, "w", "e", "s"))
    assert reg.names() == ("a", "k", "m", "z")


@pytest.mark.audit
def test_registry_single_definition_two_paths_agree():
    """build_agent (single) and role_view/list_roles (multi) read the SAME RoleSpec (S09.6)."""
    reg = _make_registry(core_tools=frozenset({"fs_read"}))
    agent = reg.build_agent("code")
    view = reg.role_view("code")
    assert isinstance(view, RoleView)
    assert view.default_scope == agent.allowed_tools     # one derivation, two callers
    assert view.agent_id == reg.get("code").name == "code"
    assert view.role == reg.get("code").role
    assert view.system_prompt == reg.get("code").system_prompt
    # list_roles projects every role exactly once, in names() order
    listed = reg.list_roles()
    assert tuple(v.agent_id for v in listed) == reg.names()


@pytest.mark.audit
def test_registry_build_agent_unknown_role_raises_keyerror():
    reg = AgentRegistry(skills=SkillRegistry(), lenses=LensRegistry())
    with pytest.raises(KeyError, match="Unknown role"):
        reg.build_agent("missing")


@pytest.mark.audit
def test_registry_load_dir_is_non_recursive_and_skips_lenses_subdir():
    """load_dir(LIBRARY) must load only top-level role yamls, NOT the lenses/ subdir."""
    reg = _make_registry()
    assert set(reg.names()) == {"business_analyst", "code", "reviewer", "test"}
    # a lens name must never have been mistaken for a role
    assert "correctness" not in reg and "requirements" not in reg


@pytest.mark.audit
def test_registry_load_file_duplicate_from_disk_raises():
    """Loading the same role file twice trips the single-store duplicate guard."""
    role_yaml = LIBRARY / "code.yaml"
    reg = AgentRegistry(skills=SkillRegistry(), lenses=LensRegistry())
    reg.load_file(role_yaml)
    with pytest.raises(ValueError, match="already registered"):
        reg.load_file(role_yaml)


# =============================================================================
# Bundled-library behavioural pins (beyond config-integrity closure)
# =============================================================================
@pytest.mark.audit
def test_bundled_code_role_allowlist_and_separation():
    reg = _make_registry()
    agent = reg.build_agent("code")
    # file_edit skill adds fs_* and forbids terminal_run; explicit fs_* union'd.
    assert agent.allowed_tools == {"fs_read", "fs_write", "fs_list"}
    assert "terminal_run" not in agent.allowed_tools
    # code does not own validation -> must hand off to test
    assert agent.guard_finish(claim_validated=True)["handoff_to"] == "test"


@pytest.mark.audit
def test_bundled_business_analyst_has_zero_tools():
    agent = _make_registry().build_agent("business_analyst")
    assert agent.allowed_tools == frozenset()
    assert agent.guard_tool_call("fs_read") is not None  # everything blocked


# =============================================================================
# Property: well-formed RoleSpec round-trips spec -> yaml -> parse_role -> spec
# =============================================================================
_TOKEN = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_."),
    min_size=1,
    max_size=12,
).filter(lambda s: s.strip())

_TOKENS = st.lists(_TOKEN, max_size=5, unique=True).map(tuple)


@st.composite
def _well_formed_role(draw) -> RoleSpec:
    owns = draw(st.booleans())
    handoff = None if owns else draw(_TOKEN)
    return RoleSpec(
        name=draw(_TOKEN),
        role=draw(_safe_text(30)),
        department=draw(_TOKEN),
        system_prompt=draw(_safe_text(40)),
        explicit_tools=draw(_TOKENS),
        allowed_skills=draw(_TOKENS),
        may_route_to=draw(_TOKENS),
        test_ownership=Ownership(owns_validation=owns, must_handoff_to=handoff),
        lenses=draw(_TOKENS),
    )


def _to_yaml_dict(spec: RoleSpec) -> dict:
    """Serialize a RoleSpec back into the YAML shape parse_role consumes."""
    return {
        "name": spec.name,
        "role": spec.role,
        "department": spec.department,
        "system_prompt": spec.system_prompt,
        "allowed_tools": list(spec.explicit_tools),
        "allowed_skills": list(spec.allowed_skills),
        "lenses": list(spec.lenses),
        "route_permissions": {"may_route_to": list(spec.may_route_to)},
        "test_ownership": {
            "owns_validation": spec.test_ownership.owns_validation,
            "must_handoff_to": spec.test_ownership.must_handoff_to,
        },
    }


@pytest.mark.audit
@pytest.mark.property
@given(spec=_well_formed_role())
@settings(max_examples=80)
def test_rolespec_roundtrips_through_yaml_and_parse_role(spec):
    """spec -> dict -> YAML text -> parse_role(...) reconstructs the canonical fields.

    Goes through a real yaml.safe_dump/safe_load to catch any serialization drift.
    """
    text = yaml.safe_dump(_to_yaml_dict(spec), allow_unicode=True, sort_keys=False)
    reparsed = parse_role(yaml.safe_load(text), source="roundtrip.yaml")

    # parse_role canonicalises required string fields via .strip() (spec.py 102-105),
    # so the round-trip target is the STRIPPED form — that normalisation is the contract.
    assert reparsed.name == spec.name.strip()
    assert reparsed.role == spec.role.strip()
    assert reparsed.department == spec.department.strip()
    assert reparsed.system_prompt == spec.system_prompt.strip()
    assert reparsed.explicit_tools == spec.explicit_tools
    assert reparsed.allowed_skills == spec.allowed_skills
    assert reparsed.may_route_to == spec.may_route_to
    assert reparsed.lenses == spec.lenses
    assert reparsed.test_ownership.owns_validation == spec.test_ownership.owns_validation
    assert reparsed.test_ownership.must_handoff_to == spec.test_ownership.must_handoff_to


@pytest.mark.audit
@pytest.mark.property
@given(spec=_well_formed_role())
@settings(max_examples=80)
def test_role_view_projection_preserves_identity_and_scope(spec):
    """Property: role_view is a faithful narrowing -- agent_id/role/system_prompt are copied
    verbatim and default_scope equals the spec's own allowlist derivation (single source)."""
    import dataclasses
    spec = dataclasses.replace(spec, allowed_skills=())  # no skills registered here
    skills = SkillRegistry()
    reg = AgentRegistry(skills=skills, lenses=LensRegistry(), core_tools=frozenset({"core_x"}))
    reg.register(spec)
    view = reg.role_view(spec.name)
    assert view.agent_id == spec.name
    assert view.role == spec.role
    assert view.system_prompt == spec.system_prompt
    # default_scope == spec.allowed_tools(...) (skills empty here -> explicit | core)
    assert view.default_scope == spec.allowed_tools(skills, frozenset({"core_x"}))
    assert view.default_scope == frozenset(spec.explicit_tools) | {"core_x"}


@pytest.mark.audit
@pytest.mark.property
@given(
    explicit=_TOKENS,
    core=_TOKENS,
    skill_allowed=_TOKENS,
    skill_forbidden=_TOKENS,
)
@settings(max_examples=100)
def test_allowlist_derivation_invariants(explicit, core, skill_allowed, skill_forbidden):
    """Property: allowed_tools == (explicit | core | skill_allowed) - skill_forbidden,
    and forbidden ALWAYS wins (no forbidden tool ever survives)."""
    skills = SkillRegistry()
    skills.register(
        SkillSpec("s", "c", allowed_tools=skill_allowed, forbidden_tools=skill_forbidden)
    )
    spec = RoleSpec("r", "w", "e", "p", explicit_tools=explicit, allowed_skills=("s",))
    resolved = spec.allowed_tools(skills, frozenset(core))

    expected = (set(explicit) | set(core) | set(skill_allowed)) - set(skill_forbidden)
    assert resolved == frozenset(expected)
    # invariant: nothing forbidden survives, regardless of how it was granted
    assert resolved.isdisjoint(set(skill_forbidden))
