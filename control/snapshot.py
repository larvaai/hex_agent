"""TaskLoopSnapshot read-model — the shape the UI Graph/Inspector render. Epic E21 (S21.9).

This is a *projection*, not state: ``build_snapshot`` folds the ``loop.*`` events the
supervisor already emits (``loop.team_composed`` / ``decision`` / ``turn`` / ``tool`` /
``finished`` …) into one view the UI can draw. Two deliberate choices, both from the plan's
red-team:

* **Fold ``loop.*``, never ``agent.*``** (F1). Nobody emits ``agent.*`` yet, so folding
  those would give an empty graph the moment we wire the real backend. ``loop.*`` is what
  the supervisor publishes today (``supervisor/graph.py``), so the same fold lights up live.
* **Read the redacted ``ui_payload``, never the raw ``payload``** for any free-form field
  (F2 / S21.9). A snapshot must never carry a secret. We also whitelist the scalar fields we
  copy, so even a non-redacted event cannot leak a secret key into the view.

The optional ``AgentView`` fields (permission / allowed_tools / context_packet) stay empty
until an event actually carries them (F6) — the Inspector shows "—" rather than guessing.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from control.errors import ControlContractError
from control.events import RuntimeEvent

# An agent node's lifecycle in the graph. pending → running → done (or waiting at a gate).
AGENT_STATUSES = frozenset({"pending", "waiting", "running", "done", "failed"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AgentView:
    """One node in the Agent Graph + the body of the Inspector (S21.18 / S21.20).

    ``role`` / ``last_output_summary`` come from loop events; ``allowed_tools`` /
    ``context_packet`` / ``permission`` are optional and filled only when an event carries
    them (red-team F6 — no permission→agent binding exists in the backend yet).
    """

    agent_id: str
    role: str = ""
    status: str = "pending"
    round_no: int = 0
    allowed_tools: tuple[str, ...] = ()
    last_output_summary: str = ""
    context_packet: dict[str, Any] = field(default_factory=dict)
    permission: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.agent_id:
            raise ControlContractError("AgentView.agent_id is required and must be non-empty.")
        if self.status not in AGENT_STATUSES:
            raise ControlContractError(
                f"AgentView.status must be one of {sorted(AGENT_STATUSES)}, got {self.status!r}."
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "status": self.status,
            "round_no": self.round_no,
            "allowed_tools": list(self.allowed_tools),
            "last_output_summary": self.last_output_summary,
            "context_packet": dict(self.context_packet),
            "permission": (dict(self.permission) if self.permission is not None else None),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AgentView":
        return cls(
            agent_id=str(d.get("agent_id", "")),
            role=str(d.get("role", "")),
            status=str(d.get("status", "pending")),
            round_no=int(d.get("round_no", 0)),
            allowed_tools=tuple(str(t) for t in (d.get("allowed_tools") or ())),
            last_output_summary=str(d.get("last_output_summary", "")),
            context_packet=dict(d.get("context_packet") or {}),
            permission=(dict(d["permission"]) if d.get("permission") is not None else None),
        )


@dataclass(frozen=True)
class TaskLoopSnapshot:
    """The whole read-model the UI renders for one session (S21.9)."""

    session_id: str
    status: str = "created"
    round_no: int = 0
    orchestrator: dict[str, str] = field(default_factory=lambda: {"last_decision": "", "reason": ""})
    agents: tuple[AgentView, ...] = ()
    pending_agent_calls: tuple[dict[str, Any], ...] = ()
    tool_calls: tuple[dict[str, Any], ...] = ()
    checkpoints: tuple[dict[str, Any], ...] = ()
    acceptance_status: tuple[dict[str, Any], ...] = ()
    last_updated_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not self.session_id:
            raise ControlContractError("TaskLoopSnapshot.session_id is required and must be non-empty.")

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "round_no": self.round_no,
            "orchestrator": dict(self.orchestrator),
            "agents": [a.as_dict() for a in self.agents],
            "pending_agent_calls": [dict(c) for c in self.pending_agent_calls],
            "tool_calls": [dict(c) for c in self.tool_calls],
            "checkpoints": [dict(c) for c in self.checkpoints],
            "acceptance_status": [dict(c) for c in self.acceptance_status],
            "last_updated_at": self.last_updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TaskLoopSnapshot":
        return cls(
            session_id=str(d.get("session_id", "")),
            status=str(d.get("status", "created")),
            round_no=int(d.get("round_no", 0)),
            orchestrator={str(k): str(v) for k, v in (d.get("orchestrator") or {}).items()},
            agents=tuple(AgentView.from_dict(a) for a in (d.get("agents") or ())),
            pending_agent_calls=tuple(dict(c) for c in (d.get("pending_agent_calls") or ())),
            tool_calls=tuple(dict(c) for c in (d.get("tool_calls") or ())),
            checkpoints=tuple(dict(c) for c in (d.get("checkpoints") or ())),
            acceptance_status=tuple(dict(c) for c in (d.get("acceptance_status") or ())),
            last_updated_at=str(d.get("last_updated_at", "")) or _utc_now(),
        )


# ── folding helpers ───────────────────────────────────────────────────────────
# A loop event → which session status it implies. Terminal events win; otherwise the
# last lifecycle marker seen sticks.
_STATUS_BY_EVENT = {
    "loop.team_composed": "team_selected",
    "loop.decision": "in_discussion",
    "loop.turn": "in_discussion",
    "loop.tool": "waiting_tool",
    "loop.finished": "finished",
    "loop.blocked": "blocked",
    "loop.failed": "failed",
}
_TERMINAL_STATUS = {"finished", "blocked", "failed"}


def _fields(ev: RuntimeEvent | dict[str, Any]) -> tuple[str, dict, dict | None, str | None, int | None]:
    """Normalise an event (RuntimeEvent or plain dict from a JSONL fixture) into
    (event_type, view, redacted_view, created_at, round_no). ``view`` prefers the redacted
    ``ui_payload`` and falls back to the raw payload only for whitelisted scalar reads;
    ``redacted_view`` is the ui_payload alone (None if the event was never redacted) and is
    the ONLY source we copy free-form dicts from."""
    if isinstance(ev, RuntimeEvent):
        et, up, pl, created, rn = ev.event_type, ev.ui_payload, ev.payload, ev.created_at, ev.round_no
    else:
        et = str(ev.get("event_type", ""))
        up = ev.get("ui_payload")
        pl = ev.get("payload") or {}
        created = ev.get("created_at")
        rn = ev.get("round_no")
    view = up if up is not None else (pl or {})
    return et, view, up, created, rn


def _tool_status(view: dict[str, Any]) -> str:
    if "status" in view:
        return str(view["status"])
    ok = view.get("ok")
    if ok is True:
        return "ok"
    if ok is False:
        return "failed"
    return ""


def _norm_call(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_id": str(c.get("agent_id", "")),
        "objective": str(c.get("objective", "")),
        "target_kind": str(c.get("target_kind", "agent")),
    }


def build_snapshot(
    events: Iterable[RuntimeEvent | dict[str, Any]], *, session_id: str
) -> TaskLoopSnapshot:
    """Fold a sequence of loop.* events into a TaskLoopSnapshot (S21.9).

    Status derivation per the plan: an agent is ``done`` once it has a ``loop.turn``,
    ``running`` if it is in the most-recent decision's ``next_agent_calls`` and has no turn
    yet, ``waiting`` if a checkpoint references it, else ``pending``. The fold is linear and
    order-sensitive, exactly like the real event stream.
    """
    order: list[str] = []
    meta: dict[str, dict[str, Any]] = {}
    turned: set[str] = set()
    waiting: set[str] = set()
    latest_calls: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    checkpoints: list[dict[str, Any]] = []
    acceptance: list[dict[str, Any]] = []
    orchestrator = {"last_decision": "", "reason": ""}
    status = "created"
    round_no = 0
    last_updated = ""

    def see(agent_id: str) -> None:
        if agent_id and agent_id not in meta:
            meta[agent_id] = {
                "role": "",
                "last_output_summary": "",
                "context_packet": {},
                "permission": None,
                "allowed_tools": (),
                "round_no": 0,
            }
            order.append(agent_id)

    for ev in events:
        et, view, redacted, created, rn = _fields(ev)
        if created:
            last_updated = str(created)
        if rn is not None:
            round_no = max(round_no, int(rn))
        # session status: never let a terminal status be overwritten by a later marker.
        if status not in _TERMINAL_STATUS and et in _STATUS_BY_EVENT:
            status = _STATUS_BY_EVENT[et]

        if et == "loop.team_composed":
            for aid in view.get("selected") or []:
                see(str(aid))

        elif et == "loop.decision":
            orchestrator = {
                "last_decision": str(view.get("decision", "")),
                "reason": str(view.get("reason", "")),
            }
            if view.get("round") is not None:
                round_no = max(round_no, int(view["round"]))
            calls = [c for c in (view.get("next_agent_calls") or []) if isinstance(c, dict)]
            latest_calls = [_norm_call(c) for c in calls]
            for c in latest_calls:
                see(c["agent_id"])
            # C1: whitelist the acceptance fields — never copy an arbitrary dict that could
            # carry a secret key. Prefer the redacted ui_payload as the source.
            acc_src = redacted.get("acceptance_status") if isinstance(redacted, dict) else view.get("acceptance_status")
            if isinstance(acc_src, list):
                acceptance = [
                    {k: a[k] for k in ("id", "text", "status") if k in a}
                    for a in acc_src
                    if isinstance(a, dict)
                ]

        elif et == "loop.turn":
            aid = str(view.get("agent_id", ""))
            see(aid)
            if aid:
                turned.add(aid)
                meta[aid]["last_output_summary"] = str(view.get("outcome", view.get("output_summary", "")))
                if rn is not None:
                    meta[aid]["round_no"] = int(rn)
                # Free-form fields come ONLY from the redacted ui_payload (never raw).
                if isinstance(redacted, dict):
                    cp = redacted.get("context_packet")
                    if isinstance(cp, dict):
                        meta[aid]["context_packet"] = dict(cp)
                    if redacted.get("permission") is not None:
                        meta[aid]["permission"] = dict(redacted["permission"])
                    if redacted.get("allowed_tools"):
                        meta[aid]["allowed_tools"] = tuple(str(t) for t in redacted["allowed_tools"])
                    if redacted.get("role"):
                        meta[aid]["role"] = str(redacted["role"])

        elif et == "permission.changed":
            # F6: the only event that binds a permission to an agent today. Read from the
            # redacted ui_payload only; light up AgentView.permission/allowed_tools.
            aid = str(view.get("agent_id", ""))
            see(aid)
            if aid and isinstance(redacted, dict):
                perm = redacted.get("permission")
                if isinstance(perm, dict):
                    meta[aid]["permission"] = dict(perm)
                    if perm.get("allowed_tools"):
                        meta[aid]["allowed_tools"] = tuple(str(t) for t in perm["allowed_tools"])
                if redacted.get("allowed_tools"):
                    meta[aid]["allowed_tools"] = tuple(str(t) for t in redacted["allowed_tools"])

        elif et == "loop.tool":
            tool_calls.append(
                {
                    "tool": str(view.get("tool", "")),
                    "status": _tool_status(view),
                    "risk_level": view.get("risk_level"),
                }
            )

        elif et == "checkpoint.reached":
            # C1: never copy the raw payload dict — whitelist scalar fields, and include any
            # free-form checkpoint payload ONLY from the redacted ui_payload (secrets masked).
            src = redacted if isinstance(redacted, dict) else view
            entry = {
                k: src.get(k)
                for k in ("checkpoint_id", "checkpoint_type", "risk_level", "status",
                          "agent_id", "created_at", "resolved_at")
                if k in src
            }
            if isinstance(redacted, dict) and isinstance(redacted.get("payload"), dict):
                entry["payload"] = dict(redacted["payload"])
            checkpoints.append(entry)
            aid = str(entry.get("agent_id") or "")
            if aid:
                see(aid)
                waiting.add(aid)

    running = {c["agent_id"] for c in latest_calls} - turned
    agents = tuple(
        AgentView(
            agent_id=aid,
            role=meta[aid]["role"],
            status=("done" if aid in turned else "waiting" if aid in waiting else "running" if aid in running else "pending"),
            round_no=meta[aid]["round_no"],
            allowed_tools=meta[aid]["allowed_tools"],
            last_output_summary=meta[aid]["last_output_summary"],
            context_packet=meta[aid]["context_packet"],
            permission=meta[aid]["permission"],
        )
        for aid in order
    )

    return TaskLoopSnapshot(
        session_id=session_id,
        status=status,
        round_no=round_no,
        orchestrator=orchestrator,
        agents=agents,
        pending_agent_calls=tuple(latest_calls),
        tool_calls=tuple(tool_calls),
        checkpoints=tuple(checkpoints),
        acceptance_status=tuple(acceptance),
        last_updated_at=last_updated or _utc_now(),
    )
