"""TaskLoopSnapshot — the read-model the UI graph/queue actually draws. Epic E21 (B2 · S21.9).

A *pure projection*: fold the canonical ``RuntimeEvent`` stream (optionally enriched by the
Blackboard) into one read-model — never a second state the UI writes into. The UI's
graph-view and queue-panel are pure functions of this snapshot, so "who is running / who is
pending" is derived, not stored twice.

Two safety invariants hold by construction:

- the projection reads each event's ``ui_payload`` (already redacted by the emitter),
  **never** ``payload`` — so a raw secret can't reach the snapshot (S21.7 / B6);
- it is idempotent per ``event_id`` — a duplicated or replayed event can't corrupt the graph.

``build_snapshot`` consumes ANY mix of the fine-grained agent lifecycle events
(``agent.selected``/``before_run``/``after_run``/``failed``) and the coarse supervisor
topics (``loop.team_composed``/``loop.decision``/``loop.turn``/``loop.tool``), so it works
against today's synchronous loop and a future streaming runtime alike.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from control.events import RuntimeEvent

# An agent node's live status. ``pending`` (selected/decided, not started) → ``running`` →
# ``done``/``failed``; ``waiting`` is reserved for a checkpoint pause (B4). Events are applied
# in ``seq`` order, so the last lifecycle event an agent receives is authoritative.
AGENT_STATUSES = ("pending", "waiting", "running", "done", "failed")


@dataclass
class AgentNode:
    agent_id: str
    status: str = "pending"
    role: str = ""
    round_no: int | None = None
    last_output: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "status": self.status,
            "role": self.role,
            "round_no": self.round_no,
            "last_output": self.last_output,
        }


@dataclass(frozen=True)
class TaskLoopSnapshot:
    """The UI-facing read-model. Built once per request from the event stream + Blackboard;
    holds only redacted/primitive data so it is safe to serialize straight to SSE/JSON."""

    session_id: str
    status: str
    round_no: int
    orchestrator: dict[str, Any]                 # {last_decision, reason, round_no}
    agents: tuple[AgentNode, ...] = ()
    pending_agent_calls: tuple[dict[str, Any], ...] = ()
    tool_calls: tuple[dict[str, Any], ...] = ()
    checkpoints: tuple[dict[str, Any], ...] = ()
    acceptance_status: tuple[dict[str, Any], ...] = ()
    last_updated_at: str | None = None
    last_seq: int = 0

    def agent(self, agent_id: str) -> AgentNode | None:
        return next((a for a in self.agents if a.agent_id == agent_id), None)

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "round_no": self.round_no,
            "orchestrator": dict(self.orchestrator),
            "agents": [a.as_dict() for a in self.agents],
            "pending_agent_calls": [dict(c) for c in self.pending_agent_calls],
            "tool_calls": [dict(t) for t in self.tool_calls],
            "checkpoints": [dict(c) for c in self.checkpoints],
            "acceptance_status": [dict(a) for a in self.acceptance_status],
            "last_updated_at": self.last_updated_at,
            "last_seq": self.last_seq,
        }


def _ui(event: RuntimeEvent) -> dict[str, Any]:
    """Read the redacted view only. If an event was never run through the Redactor we treat
    it as empty rather than fall back to raw ``payload`` — the snapshot never sees secrets."""
    return event.ui_payload if event.ui_payload is not None else {}


def _agent_ids(value: Any) -> list[tuple[str, str]]:
    """Normalize a ``selected``/``next_agent_calls`` payload field to ``[(agent_id, objective)]``.
    Accepts a list of bare ids or a list of ``{agent_id, objective}`` dicts."""
    out: list[tuple[str, str]] = []
    for item in value or []:
        if isinstance(item, dict):
            agent_id = str(item.get("agent_id", "")).strip()
            if agent_id:
                out.append((agent_id, str(item.get("objective", ""))))
        elif item:
            out.append((str(item), ""))
    return out


@dataclass
class _Builder:
    session_id: str = ""
    status: str = "running"
    round_no: int = 0
    last_decision: str = ""
    last_reason: str = ""
    decision_round: int = 0
    agents: dict[str, AgentNode] = field(default_factory=dict)
    last_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    checkpoints: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_updated_at: str | None = None
    last_seq: int = 0

    def _node(self, agent_id: str) -> AgentNode:
        node = self.agents.get(agent_id)
        if node is None:
            node = AgentNode(agent_id=agent_id)
            self.agents[agent_id] = node
        return node

    def _set(self, agent_id: str, status: str, **fields: Any) -> None:
        """Authoritative status from a lifecycle event (e.g. after_run → done)."""
        node = self._node(agent_id)
        node.status = status
        self._apply_fields(node, **fields)

    @staticmethod
    def _apply_fields(node: AgentNode, *, role: str = "", round_no: int | None = None, output: str = "") -> None:
        if role:
            node.role = role
        if round_no is not None:
            node.round_no = round_no
        if output:
            node.last_output = output

    def apply(self, event: RuntimeEvent) -> None:
        ui = _ui(event)
        if not self.session_id and event.session_id:
            self.session_id = event.session_id
        if event.seq:
            self.last_seq = max(self.last_seq, event.seq)
        if event.created_at:
            self.last_updated_at = event.created_at
        if event.round_no is not None:
            self.round_no = max(self.round_no, event.round_no)

        handler = _HANDLERS.get(event.event_type)
        if handler is not None:
            handler(self, event, ui)

    # ── per-event handlers ───────────────────────────────────────────────────
    def on_team_composed(self, event: RuntimeEvent, ui: dict[str, Any]) -> None:
        for agent_id, _ in _agent_ids(ui.get("selected")):
            node = self._node(agent_id)  # seed as pending; never downgrade a known node
            self._apply_fields(node)

    def on_agent_selected(self, event: RuntimeEvent, ui: dict[str, Any]) -> None:
        agent_id = str(ui.get("agent_id", "")).strip()
        if agent_id:
            self._node(agent_id)
            self._apply_fields(self.agents[agent_id], role=str(ui.get("role", "")))

    def on_decision(self, event: RuntimeEvent, ui: dict[str, Any]) -> None:
        self.last_decision = str(ui.get("decision", self.last_decision))
        self.last_reason = str(ui.get("reason", ""))
        self.decision_round = int(ui.get("round", self.round_no) or 0)
        calls = _agent_ids(ui.get("next_agent_calls"))
        if calls or "next_agent_calls" in ui:
            self.last_calls = [{"agent_id": a, "objective": o} for a, o in calls]
        # A decided-but-not-yet-started call leaves the node ``pending`` and shows up in
        # ``pending_agent_calls``. ``waiting`` is reserved for a checkpoint pause (B4),
        # so we only seed the node here, never advance its status.
        for agent_id, _ in calls:
            self._node(agent_id)

    def on_before_run(self, event: RuntimeEvent, ui: dict[str, Any]) -> None:
        agent_id = str(ui.get("agent_id", "")).strip()
        if agent_id:
            self._set(agent_id, "running", round_no=ui.get("round_no"), role=str(ui.get("role", "")))

    def on_after_run(self, event: RuntimeEvent, ui: dict[str, Any]) -> None:
        agent_id = str(ui.get("agent_id", "")).strip()
        if agent_id:
            self._set(agent_id, "done", output=str(ui.get("summary", "") or ui.get("outcome", "")))

    def on_failed(self, event: RuntimeEvent, ui: dict[str, Any]) -> None:
        agent_id = str(ui.get("agent_id", "")).strip()
        if agent_id:
            self._set(agent_id, "failed", output=str(ui.get("error", "")))

    def on_turn(self, event: RuntimeEvent, ui: dict[str, Any]) -> None:
        agent_id = str(ui.get("agent_id", "")).strip()
        if not agent_id:
            return
        outcome = str(ui.get("outcome", ""))
        self._set(agent_id, "done" if outcome in ("success", "ok", "done") else "failed", output=outcome)

    def on_tool(self, event: RuntimeEvent, ui: dict[str, Any]) -> None:
        tool = str(ui.get("tool") or ui.get("name") or "")
        if tool:
            self.tool_calls.append({"tool": tool, "ok": ui.get("ok"), "event_id": event.event_id})

    def on_checkpoint(self, event: RuntimeEvent, ui: dict[str, Any]) -> None:
        cid = str(ui.get("checkpoint_id") or event.event_id)
        self.checkpoints[cid] = {
            "checkpoint_id": cid,
            "checkpoint_type": str(ui.get("checkpoint_type", "")),
            "status": str(ui.get("status", "waiting")),
            "risk_level": str(ui.get("risk_level", "")),
        }

    def on_checkpoint_resolved(self, event: RuntimeEvent, ui: dict[str, Any], status: str) -> None:
        cid = str(ui.get("checkpoint_id", ""))
        if cid in self.checkpoints:
            self.checkpoints[cid]["status"] = status

    def on_status(self, event: RuntimeEvent, ui: dict[str, Any], status: str) -> None:
        self.status = status


# Dispatch table keeps ``apply`` flat and the supported vocabulary in one readable place.
_HANDLERS: dict[str, Any] = {
    "loop.team_composed": _Builder.on_team_composed,
    "agent.selected": _Builder.on_agent_selected,
    "loop.decision": _Builder.on_decision,
    "agent.before_run": _Builder.on_before_run,
    "agent.after_run": _Builder.on_after_run,
    "agent.failed": _Builder.on_failed,
    "agent.aborted": _Builder.on_failed,
    "loop.turn": _Builder.on_turn,
    "loop.tool": _Builder.on_tool,
    "tool.after_call": _Builder.on_tool,
    "checkpoint.reached": _Builder.on_checkpoint,
    "approval.requested": _Builder.on_checkpoint,
    "approval.approved": lambda b, e, ui: b.on_checkpoint_resolved(e, ui, "approved"),
    "approval.rejected": lambda b, e, ui: b.on_checkpoint_resolved(e, ui, "rejected"),
    "loop.finished": lambda b, e, ui: b.on_status(e, ui, "finished"),
    "session.finished": lambda b, e, ui: b.on_status(e, ui, "finished"),
    "loop.blocked": lambda b, e, ui: b.on_status(e, ui, "blocked"),
    "loop.failed": lambda b, e, ui: b.on_status(e, ui, "failed"),
    "session.failed": lambda b, e, ui: b.on_status(e, ui, "failed"),
}

# Agents that have already started (or finished) are no longer "pending calls" in the queue.
_NOT_PENDING = frozenset({"running", "done", "failed"})


def build_snapshot(
    events: Iterable[RuntimeEvent],
    *,
    state: Any | None = None,
    session_id: str | None = None,
) -> TaskLoopSnapshot:
    """Fold an event stream (newest-last) into a ``TaskLoopSnapshot``.

    Events are ordered by ``seq`` when present (the canonical per-session order) and
    de-duplicated by ``event_id`` so replay/at-least-once delivery is idempotent. ``state``
    (a ``TaskLoopState``) is optional enrichment: it supplies ``acceptance_status`` and
    backfills overall ``status``/``round_no`` — data not yet carried by any event today.
    """
    seen: set[str] = set()
    ordered = sorted(
        (e for e in events if not (e.event_id in seen or seen.add(e.event_id))),
        key=lambda e: (e.seq, e.created_at),
    )

    builder = _Builder(session_id=session_id or "")
    for event in ordered:
        builder.apply(event)

    # Blackboard enrichment for fields no event carries yet.
    acceptance: tuple[dict[str, Any], ...] = ()
    if state is not None:
        if not builder.session_id:
            builder.session_id = getattr(state, "session_id", "")
        builder.round_no = max(builder.round_no, int(getattr(state, "round_no", 0) or 0))
        acceptance = tuple(c.as_dict() for c in getattr(state, "acceptance_checks", ()) or ())
        # If no terminal loop event was seen, trust the Blackboard's own status.
        if builder.status == "running" and getattr(state, "status", None):
            builder.status = str(state.status)

    pending_calls = tuple(
        call
        for call in builder.last_calls
        if builder.agents.get(call["agent_id"], AgentNode(call["agent_id"])).status not in _NOT_PENDING
    )

    return TaskLoopSnapshot(
        session_id=builder.session_id or (session_id or ""),
        status=builder.status,
        round_no=builder.round_no,
        orchestrator={
            "last_decision": builder.last_decision,
            "reason": builder.last_reason,
            "round_no": builder.decision_round,
        },
        agents=tuple(builder.agents.values()),
        pending_agent_calls=pending_calls,
        tool_calls=tuple(builder.tool_calls),
        checkpoints=tuple(builder.checkpoints.values()),
        acceptance_status=acceptance,
        last_updated_at=builder.last_updated_at,
        last_seq=builder.last_seq,
    )
