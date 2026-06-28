"""TaskLoopState — the serializable Blackboard for one multi-agent run. Epic E10.

Round-based, not a live shared transcript: each worker turn appends an AgentTurn
and any artifacts; the next o_decide reads the Blackboard, never the workers' raw
sessions. State holds only primitives so it can be checkpointed (SQLite) in S3.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskLoopStatus(str, Enum):
    CREATED = "created"
    TEAM_SELECTED = "team_selected"
    IN_DISCUSSION = "in_discussion"
    WAITING_TOOL = "waiting_tool"
    REVIEWING_AC = "reviewing_ac"
    FINISHED = "finished"
    BLOCKED = "blocked"
    FAILED = "failed"


TERMINAL = {TaskLoopStatus.FINISHED, TaskLoopStatus.BLOCKED, TaskLoopStatus.FAILED}


@dataclass
class AcceptanceCheck:
    id: str
    text: str
    status: str = "pending"            # pending | passed | failed
    evidence_ids: list[str] = field(default_factory=list)

    @property
    def is_satisfied(self) -> bool:
        return self.status == "passed" and bool(self.evidence_ids)

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "text": self.text, "status": self.status, "evidence_ids": list(self.evidence_ids)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AcceptanceCheck":
        return cls(
            id=str(d["id"]),
            text=str(d.get("text", "")),
            status=str(d.get("status", "pending")),
            evidence_ids=list(d.get("evidence_ids") or []),
        )


@dataclass
class AgentTurn:
    round_no: int
    agent_id: str
    packet_id: str
    output_summary: str = ""
    artifact_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "round_no": self.round_no,
            "agent_id": self.agent_id,
            "packet_id": self.packet_id,
            "output_summary": self.output_summary,
            "artifact_ids": list(self.artifact_ids),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AgentTurn":
        return cls(
            round_no=int(d["round_no"]),
            agent_id=str(d["agent_id"]),
            packet_id=str(d.get("packet_id", "")),
            output_summary=str(d.get("output_summary", "")),
            artifact_ids=list(d.get("artifact_ids") or []),
        )


@dataclass
class TaskLoopState:
    session_id: str
    task_id: str
    status: str = TaskLoopStatus.CREATED.value
    selected_agents: list[str] = field(default_factory=list)
    acceptance_checks: list[AcceptanceCheck] = field(default_factory=list)
    round_no: int = 0
    max_rounds: int = 5
    turns: list[AgentTurn] = field(default_factory=list)
    artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    tool_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    final_output: dict[str, Any] | None = None
    reason: str = ""
    # Control-plane command queue (E21). pending_commands holds O-issued intents
    # waiting for the end-of-round checkpoint; applied_command_keys records the
    # idempotency_keys already applied so a resume never double-applies.
    pending_commands: list[dict[str, Any]] = field(default_factory=list)
    applied_command_keys: list[str] = field(default_factory=list)

    # ── helpers ──────────────────────────────────────────────────────────────
    def add_artifact(self, artifact_id: str, payload: dict[str, Any]) -> None:
        self.artifacts[artifact_id] = payload

    def acceptance_by_id(self, check_id: str) -> AcceptanceCheck | None:
        return next((c for c in self.acceptance_checks if c.id == check_id), None)

    def all_accepted(self) -> bool:
        return bool(self.acceptance_checks) and all(c.is_satisfied for c in self.acceptance_checks)

    @property
    def is_terminal(self) -> bool:
        return TaskLoopStatus(self.status) in TERMINAL

    def acceptance_snapshot(self) -> tuple[tuple[str, str, int], ...]:
        """A comparable snapshot of acceptance progress (for the loop guard)."""
        return tuple((c.id, c.status, len(c.evidence_ids)) for c in self.acceptance_checks)


def encode_taskloop_state(state: TaskLoopState) -> dict[str, Any]:
    return {
        "session_id": state.session_id,
        "task_id": state.task_id,
        "status": state.status,
        "selected_agents": list(state.selected_agents),
        "acceptance_checks": [c.as_dict() for c in state.acceptance_checks],
        "round_no": state.round_no,
        "max_rounds": state.max_rounds,
        "turns": [t.as_dict() for t in state.turns],
        "artifacts": {k: dict(v) for k, v in state.artifacts.items()},
        "tool_results": {k: dict(v) for k, v in state.tool_results.items()},
        "final_output": dict(state.final_output) if state.final_output else None,
        "reason": state.reason,
        "pending_commands": [dict(c) for c in state.pending_commands],
        "applied_command_keys": list(state.applied_command_keys),
    }


def decode_taskloop_state(data: dict[str, Any]) -> TaskLoopState:
    return TaskLoopState(
        session_id=str(data["session_id"]),
        task_id=str(data["task_id"]),
        status=str(data.get("status", TaskLoopStatus.CREATED.value)),
        selected_agents=list(data.get("selected_agents") or []),
        acceptance_checks=[AcceptanceCheck.from_dict(c) for c in data.get("acceptance_checks") or []],
        round_no=int(data.get("round_no", 0)),
        max_rounds=int(data.get("max_rounds", 5)),
        turns=[AgentTurn.from_dict(t) for t in data.get("turns") or []],
        artifacts={k: dict(v) for k, v in (data.get("artifacts") or {}).items()},
        tool_results={k: dict(v) for k, v in (data.get("tool_results") or {}).items()},
        final_output=dict(data["final_output"]) if data.get("final_output") else None,
        reason=str(data.get("reason", "")),
        # .get(..., []) so an old checkpoint that predates these keys decodes
        # to empty queues instead of raising KeyError.
        pending_commands=[dict(c) for c in (data.get("pending_commands") or [])],
        applied_command_keys=list(data.get("applied_command_keys") or []),
    )
