"""E21 Phase 2 — TS contract generator + drift-guard tests. Maps to plan D2 / R4.

The generator is the single source of truth bridge: TypeScript types are *derived* from
the ``control/`` dataclasses, never hand-written, so a field rename in Python surfaces as a
TS compile error (not a silent UI drift). ``--check`` is the CI-facing drift guard: exit 0
when the committed ``.d.ts`` matches a fresh render, exit 1 when it has drifted.
"""
from __future__ import annotations

import importlib.util
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "gen_ts_contracts", ROOT / "tools" / "gen_ts_contracts.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _interface_block(text: str, name: str) -> str:
    m = re.search(rf"export interface {name} \{{(.*?)\}}", text, re.S)
    assert m, f"interface {name} not found in generated output"
    return m.group(1)


def test_generated_has_all_five_shapes():
    out = _load().render_dts()
    for name in (
        "Actor",
        "TraceContext",
        "RedactionInfo",
        "RuntimeEvent",
        "IssuedBy",
        "RuntimeCommand",
        "CommandAck",
        "RuntimeCheckpoint",
        "Permission",
        "AgentView",
        "TaskLoopSnapshot",
    ):
        assert f"export interface {name} {{" in out
    # header marks it generated so nobody hand-edits it
    assert "do not edit" in out.lower()


def test_field_names_match_as_dict():
    from control import RuntimeCheckpoint

    cp = RuntimeCheckpoint(checkpoint_type="before_tool_call", session_id="s", risk_level="high")
    expected = set(cp.as_dict().keys())

    block = _interface_block(_load().render_dts(), "RuntimeCheckpoint")
    ts_fields = set(re.findall(r"^\s*(\w+):", block, re.M))
    assert ts_fields == expected


def test_type_mapping_is_explicit_not_any():
    out = _load().render_dts()
    # X | None -> X | null ; dict -> Record ; tuple/list -> T[] ; nested dataclass -> ref
    assert "resolved_at: string | null;" in out  # RuntimeCheckpoint optional
    assert "payload: Record<string, unknown>;" in out
    assert "redacted_fields: string[];" in out  # RedactionInfo tuple[str, ...]
    assert "actor: Actor;" in out  # nested dataclass ref
    assert "agents: AgentView[];" in out  # tuple[AgentView, ...]
    # no blind `any` leaked anywhere
    assert ": any" not in out


def test_check_flag_exit_code():
    gen = _load()
    # write the file, then a fresh --check must be clean (exit 0)
    assert gen.main([]) == 0
    assert gen.main(["--check"]) == 0
    original = gen.OUTPUT_PATH.read_text(encoding="utf-8")
    try:
        # simulate drift: a stray extra line on disk
        gen.OUTPUT_PATH.write_text(
            original + "\nexport interface Drift { x: string; }\n", encoding="utf-8"
        )
        assert gen.main(["--check"]) == 1
    finally:
        gen.OUTPUT_PATH.write_text(original, encoding="utf-8")
    assert gen.main(["--check"]) == 0
