"""Supervisor nodes — compose_team / o_decide / run_round / judge / tool. Epic E10.

Each node operates on the Blackboard (TaskLoopState) plus a SupervisorContext of
runtime deps, mutating state in place. The plain-Python driver in ``loop.py`` wires
them; the same node signatures are ready to lift onto a compiled LangGraph +
SQLite checkpoint in S3 (which is also when resume / S10.10 lands).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from control import Actor, EventEmitter, TraceContext
from core.schemas import DelegationPolicy
from core.session import KernelSession
from discipline import Budget, JsonGateError
from supervisor.broker import BrokerPort
from supervisor.contracts import (
    AgentAssignment,
    OrchestratorDecision,
    SessionPlan,
    parse_decision,
    parse_session_plan,
)
from supervisor.evidence import evidence_type_of
from supervisor.orchestrator import OrchestratorPort
from supervisor.state import AcceptanceCheck, AgentTurn, TaskLoopState, TaskLoopStatus

# A store-slice provider hands the Broker the artifacts it may ground a briefing in.
StoreSliceProvider = Callable[[AgentAssignment, TaskLoopState], list[dict[str, Any]]]


def default_store_slice(assignment: AgentAssignment, state: TaskLoopState) -> list[dict[str, Any]]:
    """By default the Broker may ground in everything currently on the Blackboard."""
    return [{"id": k, "text": str(v)} for k, v in state.artifacts.items()]


@dataclass
class SupervisorContext:
    supervisor_session: KernelSession
    delegation_service: Any            # DelegationServicePort
    orchestrator: OrchestratorPort
    broker: BrokerPort
    agent_registry: Any | None = None  # E09 AgentRegistry (for the role catalog)
    store_slice_provider: StoreSliceProvider = default_store_slice
    checkpoint: Callable[[TaskLoopState], None] | None = None  # SQLite save (S10.10)
    emitter: EventEmitter | None = None  # E21 B1: route events through the RuntimeEvent envelope
    trace: TraceContext | None = None    # root trace for this session's events (lazily created)

    def role_catalog(self) -> tuple[dict[str, Any], ...]:
        if self.agent_registry is None:
            return ()
        return tuple({"agent_id": v.agent_id, "role": v.role} for v in self.agent_registry.list_roles())

    def emit(self, topic: str, payload: dict[str, Any]) -> None:
        # E21 B1: when an emitter is wired, every supervisor event flows through the
        # canonical envelope (registry-validated, seq-stamped, redacted). Otherwise keep
        # the legacy raw-dict publish so existing callers/tests are unaffected.
        if self.emitter is not None:
            if self.trace is None:
                self.trace = TraceContext.new_root()
            identity = self.supervisor_session.identity
            self.emitter.emit(
                topic,
                session_id=identity.session_id,
                actor=Actor(type="runtime", id="supervisor"),
                trace=self.trace,
                payload=dict(payload),
                task_id=identity.task_id,
            )
            return
        self.supervisor_session.kernel.events.publish(
            topic, {**self.supervisor_session.call_context().event_fields(), **payload}
        )

    def save(self, state: TaskLoopState) -> None:
        if self.checkpoint is not None:
            self.checkpoint(state)


def _next_id(prefix: str, state: TaskLoopState) -> str:
    return f"{prefix}-{len(state.artifacts):04d}"


# ── compose_team (S10.1) ─────────────────────────────────────────────────────
def compose_team(state: TaskLoopState, ctx: SupervisorContext, *, task: str) -> SessionPlan:
    plan = parse_session_plan(ctx.orchestrator.compose_team(task=task, available_roles=ctx.role_catalog()))
    ids = plan.agent_ids()
    # Validate against the role catalog before mutating the Blackboard.
    duplicates = sorted({a for a in ids if ids.count(a) > 1})
    if duplicates:
        raise ValueError(f"Team composition selected duplicate agents: {duplicates}")
    catalog = {row["agent_id"] for row in ctx.role_catalog()}
    if catalog:
        unknown = sorted(a for a in ids if a not in catalog)
        if unknown:
            raise ValueError(f"Team composition selected unknown agents: {unknown}")
    state.selected_agents = list(ids)
    art_id = _next_id("session_plan", state)
    state.add_artifact(art_id, {"kind": "session_plan", **plan.as_dict()})
    state.status = TaskLoopStatus.TEAM_SELECTED.value
    ctx.emit("loop.team_composed", {"selected": list(state.selected_agents)})
    return plan


# ── o_decide (S10.8) ─────────────────────────────────────────────────────────
def o_decide(state: TaskLoopState, ctx: SupervisorContext, *, budget: Budget) -> OrchestratorDecision | None:
    """Parse one O decision, repairing/re-prompting on bad JSON. Returns None when
    the parse-error budget is exhausted (driver routes that to `failed`)."""
    while True:
        raw = ctx.orchestrator.decide(state_view=_state_view(state))
        try:
            decision = parse_decision(raw)
        except JsonGateError:
            budget.record_parse_error()
            ctx.emit("loop.parse_error", {"round": state.round_no, "count": budget.parse_errors})
            if budget.parse_exceeded():
                return None
            continue
        budget.record_parse_success()  # O recovered — clear the consecutive-fumble streak
        ctx.emit("loop.decision", {"round": state.round_no, "decision": decision.decision})
        return decision


def _state_view(state: TaskLoopState) -> dict[str, Any]:
    return {
        "round_no": state.round_no,
        "selected_agents": list(state.selected_agents),
        "acceptance": [c.as_dict() for c in state.acceptance_checks],
        "recent_turns": [t.as_dict() for t in state.turns[-len(state.selected_agents or [1]) :]],
        "artifact_ids": list(state.artifacts),
    }


# ── run_round (S10.2/S10.3/S10.5/S10.14) ─────────────────────────────────────
def run_round(state: TaskLoopState, ctx: SupervisorContext, decision: OrchestratorDecision) -> None:
    """Delegate to each assigned agent exactly once; merge results into the board.

    On resume, an agent that already produced a turn this round is skipped — a
    completed worker turn is never re-run (S10.10)."""
    # Authority check first: every assignment must target an agent the composition
    # selected. Validate the whole batch before any packet/delegation side effect.
    selected = set(state.selected_agents)
    for assignment in decision.next_agent_calls:
        if assignment.agent_id not in selected:
            raise PermissionError(
                f"Assignment targets agent '{assignment.agent_id}' that was not selected by composition."
            )

    done_this_round = {t.agent_id for t in state.turns if t.round_no == state.round_no}
    for assignment in decision.next_agent_calls:
        if assignment.agent_id in done_this_round:
            continue
        store_slice = ctx.store_slice_provider(assignment, state)
        packet = ctx.broker.write_packet(assignment=assignment, store_slice=store_slice)
        # The Broker shapes context only; it can never redirect a turn to another agent.
        if packet.target_agent_id != assignment.agent_id:
            raise PermissionError(
                f"Broker packet target '{packet.target_agent_id}' does not match "
                f"assigned agent '{assignment.agent_id}'."
            )
        packet_id = _next_id("context_packet", state)
        state.add_artifact(
            packet_id,
            {
                "kind": "context_packet",
                "target": packet.target_agent_id,
                "objective": packet.objective,
                "briefing": packet.briefing,
                "source_ids": list(packet.source_ids),
            },
        )

        # Scope comes ONLY from O's assignment — never from the Broker (S10.14).
        policy = DelegationPolicy(allowed_capabilities=frozenset(assignment.allowed_capabilities))
        result = ctx.delegation_service.delegate(
            ctx.supervisor_session, assignment.agent_id, packet.to_spec(), policy
        )

        artifact_ids: list[str] = []
        for art in result.artifacts:
            state.add_artifact(
                art.artifact_id,
                {"kind": art.kind, "agent_id": assignment.agent_id, **art.payload},
            )
            artifact_ids.append(art.artifact_id)
        result_id = _next_id("delegation_result", state)
        state.add_artifact(
            result_id,
            {
                "kind": "delegation_result",
                "agent_id": assignment.agent_id,
                "outcome": result.outcome,
                "summary": dict(result.summary),
                "error": result.error,
            },
        )
        artifact_ids.append(result_id)
        state.turns.append(
            AgentTurn(
                round_no=state.round_no,
                agent_id=assignment.agent_id,
                packet_id=packet_id,
                output_summary=result.outcome,
                artifact_ids=artifact_ids,
            )
        )
        ctx.emit("loop.turn", {"agent_id": assignment.agent_id, "outcome": result.outcome})
        ctx.save(state)  # checkpoint after each completed turn (S10.10)
    state.status = TaskLoopStatus.IN_DISCUSSION.value


# ── tool via the kernel chokepoint (S10.9) ───────────────────────────────────
def run_tool(state: TaskLoopState, ctx: SupervisorContext, decision: OrchestratorDecision) -> None:
    for req in decision.tool_requests:
        tool = str(req.get("tool") or req.get("name") or "")
        args = dict(req.get("args") or {})
        envelope = ctx.supervisor_session.execute_tool(tool, args)  # crosses execute_tool
        art_id = _next_id("tool_result", state)
        state.tool_results[art_id] = envelope
        state.add_artifact(
            art_id,
            {"kind": "tool_result", "tool": tool, "ok": envelope.get("ok"), "data": envelope.get("data")},
        )
        ctx.emit("loop.tool", {"tool": tool, "ok": envelope.get("ok")})
    state.status = TaskLoopStatus.WAITING_TOOL.value


# ── acceptance gate (S10.6) ──────────────────────────────────────────────────
def judge_acceptance(state: TaskLoopState, ctx: SupervisorContext, decision: OrchestratorDecision) -> None:
    """Apply O's reported acceptance status. 'passed' is honoured only when every
    cited id resolves on the Blackboard AND at least one is a real evidence type —
    scaffolding alone (session_plan/context_packet/ac_report) no longer satisfies an
    AC (S21.33). ≥1 valid, not all-valid: O may attach one scaffolding id alongside
    real evidence without being wrongly blocked."""
    for row in decision.acceptance_status:
        check: AcceptanceCheck | None = state.acceptance_by_id(str(row.get("id", "")))
        if check is None:
            continue
        claimed = str(row.get("status", "pending"))
        evidence = [str(e) for e in (row.get("evidence_ids") or [])]
        if (
            claimed == "passed"
            and evidence
            and all(e in state.artifacts for e in evidence)
            and any(evidence_type_of(state.artifacts[e]) is not None for e in evidence)
        ):
            check.status = "passed"
            check.evidence_ids = evidence
        elif claimed == "failed":
            check.status = "failed"
            check.evidence_ids = evidence
        else:
            check.status = "pending"
    state.status = TaskLoopStatus.REVIEWING_AC.value
