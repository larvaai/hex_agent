"""Generate TS types from control/ dataclasses (single source of truth). Epic E21 (D2/R4).

The UI must not hand-write TypeScript that mirrors the Python contracts — that drifts
silently. Instead we introspect each ``@dataclass`` in ``control/`` (their field list IS
the contract, the same one ``as_dict`` serialises) and emit ``.d.ts`` interfaces. A field
rename in Python then becomes a TS compile error in the UI.

Two modes (stdlib ``argparse`` only — no JSON-Schema, no extra dependency):
  * default  : (re)write ``ui/control-plane/src/contracts/generated.d.ts``.
  * ``--check``: regenerate into memory, diff against the committed file, exit 1 on drift.
    This is the CI drift-guard — deliberately its own flag, not borrowed from gen_map.py
    (which has no argparse / --check — red-team F10).
"""
from __future__ import annotations

import argparse
import dataclasses
import difflib
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from control.checkpoint import RuntimeCheckpoint  # noqa: E402
from control.commands import CommandAck, IssuedBy, RuntimeCommand  # noqa: E402
from control.events import Actor, RedactionInfo, RuntimeEvent, TraceContext  # noqa: E402
from control.permission import Permission  # noqa: E402
from control.snapshot import AgentView, TaskLoopSnapshot  # noqa: E402

OUTPUT_PATH = ROOT / "ui" / "control-plane" / "src" / "contracts" / "generated.d.ts"
HEADER = "// GENERATED from control/*.py — do not edit; run tools/gen_ts_contracts.py"

# Nested shapes first so each interface's references are already declared above it.
SHAPES = [
    Actor,
    TraceContext,
    RedactionInfo,
    RuntimeEvent,
    IssuedBy,
    RuntimeCommand,
    CommandAck,
    RuntimeCheckpoint,
    Permission,
    AgentView,
    TaskLoopSnapshot,
]
_KNOWN = {cls.__name__ for cls in SHAPES}
_SCALAR = {"str": "string", "int": "number", "float": "number", "bool": "boolean", "Any": "unknown"}


def _annotation(field: dataclasses.Field) -> str:
    """The field's annotation as a string (PEP 563 future-annotations keep them as str)."""
    return field.type if isinstance(field.type, str) else getattr(field.type, "__name__", str(field.type))


def ts_type(ann: str) -> str:
    """Map one Python annotation string to a TypeScript type. Raises on anything outside the
    whitelist — we never emit a blind ``any`` that would hide a contract we forgot to map."""
    ann = ann.strip()
    if "|" in ann:
        parts = [p.strip() for p in ann.split("|")]
        mapped = [ts_type(p) for p in parts if p != "None"]
        if "None" in parts:
            mapped.append("null")
        return " | ".join(mapped)
    m = re.match(r"^(?:tuple|list)\[(.+?)(?:,\s*\.\.\.)?\]$", ann)
    if m:
        return ts_type(m.group(1)) + "[]"
    m = re.match(r"^dict\[\s*(\w+)\s*,\s*(.+)\]$", ann)
    if m:
        return f"Record<{ts_type(m.group(1))}, {ts_type(m.group(2))}>"
    if ann in _SCALAR:
        return _SCALAR[ann]
    if ann in _KNOWN:
        return ann
    raise SystemExit(f"gen_ts_contracts: unmapped type {ann!r} — extend the type map, don't emit any.")


def render_dts() -> str:
    lines = [HEADER, ""]
    for cls in SHAPES:
        lines.append(f"export interface {cls.__name__} {{")
        for field in dataclasses.fields(cls):
            lines.append(f"  {field.name}: {ts_type(_annotation(field))};")
        lines.append("}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate/check TS contracts from control/ dataclasses.")
    ap.add_argument("--check", action="store_true", help="exit 1 if the committed .d.ts has drifted")
    args = ap.parse_args(argv)
    content = render_dts()

    if args.check:
        if not OUTPUT_PATH.exists():
            print(f"{OUTPUT_PATH} missing — run `python tools/gen_ts_contracts.py`", file=sys.stderr)
            return 1
        disk = OUTPUT_PATH.read_text(encoding="utf-8")
        if disk != content:
            diff = difflib.unified_diff(
                disk.splitlines(), content.splitlines(), "committed", "regenerated", lineterm=""
            )
            print("\n".join(diff), file=sys.stderr)
            print("DRIFT: generated.d.ts is stale — run `python tools/gen_ts_contracts.py`", file=sys.stderr)
            return 1
        return 0

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(content, encoding="utf-8")
    print(f"wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
