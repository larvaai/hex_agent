"""Generate the T1 demo fixture through the REAL event pipeline. Epic E21 (DEC-6, F2/F3/F6).

The fixture is NOT hand-written JSON — that would let it drift from the contract. Each line is a
real ``RuntimeEvent`` pushed through a real ``EventEmitter``, so it is registry-validated, seq is
stamped monotonically via ``SessionSeq`` (F3 — not the default 0, or Last-Event-ID is meaningless),
and ``ui_payload`` is filled by the real ``Redactor`` (F2 — one event carries an api_key to prove
redaction is reachable, not a dead path). Output: fixtures/control_plane/t1_scenario.events.jsonl.

Scenario (uses the loop.* events the supervisor actually emits — F1): team [A,B,C] composed → A
turns → O routes to B → a high-risk tool → a waiting checkpoint → B's permission set (F6) →
approval → B turns → finished.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from control.emitter import EventEmitter  # noqa: E402
from control.events import Actor, RuntimeEvent, TraceContext  # noqa: E402
from control.permission import Permission  # noqa: E402

OUTPUT_PATH = ROOT / "fixtures" / "control_plane" / "t1_scenario.events.jsonl"
SESSION_ID = "t1_demo"


class _Collect:
    """An EventSinkPort that just records each finalized (seq-stamped, redacted) event."""

    def __init__(self) -> None:
        self.events: list[RuntimeEvent] = []

    def emit(self, event: RuntimeEvent) -> None:
        self.events.append(event)


def build_events(session_id: str = SESSION_ID) -> list[dict]:
    sink = _Collect()
    emitter = EventEmitter([sink])  # real registry + Redactor + SessionSeq
    actor = Actor(type="runtime", id="supervisor")
    trace = TraceContext.new_root()

    def emit(event_type: str, payload: dict, *, round_no: int | None = None) -> None:
        emitter.emit(
            event_type, session_id=session_id, actor=actor, trace=trace, payload=payload, round_no=round_no
        )

    perm = Permission(allowed_tools=("read_file", "search_code"), can_write_artifacts=True)

    emit("loop.team_composed", {"selected": ["A", "B", "C"]}, round_no=0)
    emit("loop.turn", {"agent_id": "A", "outcome": "drafted the plan"}, round_no=1)
    emit(
        "loop.decision",
        {
            "round": 1,
            "decision": "continue",
            "reason": "A done — route the build to B",
            "next_agent_calls": [{"agent_id": "B", "objective": "build the module"}],
        },
        round_no=1,
    )
    # high-risk tool carrying a secret — proves redaction is on a reachable path (F2)
    emit("loop.tool", {"tool": "http_get", "ok": True, "risk_level": "high", "api_key": "sk-DEMO-LEAK"}, round_no=1)
    emit(
        "checkpoint.reached",
        {
            "checkpoint_type": "before_tool_call",
            "risk_level": "high",
            "status": "waiting",
            "agent_id": "B",
            "checkpoint_id": "cp_demo_1",
        },
        round_no=1,
    )
    emit("permission.changed", {"agent_id": "B", "permission": perm.as_dict()}, round_no=1)  # F6
    emit("approval.approved", {"checkpoint_id": "cp_demo_1", "agent_id": "B"}, round_no=1)
    emit("loop.turn", {"agent_id": "B", "outcome": "built the module"}, round_no=2)
    emit("loop.finished", {"summary": "all acceptance checks satisfied"}, round_no=2)

    return [e.as_dict() for e in sink.events]


def main(argv: list[str] | None = None) -> int:
    events = build_events()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
    print(f"wrote {len(events)} events to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
