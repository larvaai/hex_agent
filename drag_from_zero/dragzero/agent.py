"""Agent actor — runs a bounded ReAct loop, then emits a terminal decision.

Each step the agent either asks to call a tool (an observable action) or returns
a terminal DelegationDecision (solo / delegate). The orchestrator drives the
loop: it runs tools, feeds results back as observations, and stops on the
terminal step. A response with only ``decision`` (no ``action``) is a one-shot
terminal step — exactly the Slice 1 behaviour.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .contracts import DelegationDecision, PlanSpec, ToolCall, TriageResult


@dataclass
class Task:
    id: str
    description: str
    parent_id: Optional[str] = None
    assigned_agent: Optional[str] = None
    done_when: Optional[list] = None  # Gap 2: present => code-gated leaf (verify→retry-K→decompose)


@dataclass
class AgentStep:
    kind: str  # "tool" | "terminal"
    tool_call: Optional[ToolCall] = None
    plan: Optional[PlanSpec] = None
    decision: Optional[DelegationDecision] = None


@dataclass
class Agent:
    id: str
    role: str
    llm: object
    he: Optional[str] = None  # multi-lens hệ: enabled binding ⇒ CODE mandates its combo (keyword default = additive)

    def step(self, task: Task, depth: int, observations: list, step_idx: int, tools: Optional[list] = None) -> AgentStep:
        ctx = {
            "agent_id": self.id,
            "role": self.role,
            "task": task.description,
            "depth": depth,
            "step": step_idx,
            "observations": list(observations),
            "tools": list(tools or []),
        }
        resp = self.llm.complete(ctx)
        action = resp.get("action") if isinstance(resp, dict) else None
        if isinstance(action, dict) and action.get("type") == "tool":
            return AgentStep(kind="tool", tool_call=ToolCall.from_dict(action))
        return AgentStep(
            kind="terminal",
            plan=PlanSpec.from_dict(resp.get("plan", {})),
            decision=DelegationDecision.from_dict(resp["decision"]),
        )

    def triage(self, raw_input: str) -> TriageResult:
        """Classify raw user input: a plain question (answer) vs a task (goal + proposed done_when).
        The worker PROPOSES — it never adjudicates; CODE validates the done_when in the orchestrator
        (Slice D2). Branches on ctx['request'] like decompose, so the step/decompose paths are untouched."""
        ctx = {
            "agent_id": self.id,
            "role": self.role,
            "input": raw_input,
            "request": "triage",                # the responder branches on this
        }
        resp = self.llm.complete(ctx)
        payload = resp.get("triage") if isinstance(resp, dict) and "triage" in resp else (resp or {})
        return TriageResult.from_dict(payload if isinstance(payload, dict) else {})

    def decompose(self, task: Task, depth: int, evidence: Optional[list] = None) -> list:
        """Ask the worker to PROPOSE child nodes after K leaf attempts failed. Returns the raw
        children list (each {id, goal, done_when, depends_on?}); CODE validates it via Gate-2.
        The worker proposes structure + criteria — never a verdict."""
        ctx = {
            "agent_id": self.id,
            "role": self.role,
            "task": task.description,
            "depth": depth,
            "request": "decompose",            # the responder branches on this
            "done_when": list(task.done_when or []),
            "evidence": list(evidence or []),
        }
        resp = self.llm.complete(ctx)
        dec = resp.get("decompose") if isinstance(resp, dict) else None
        if isinstance(dec, dict):
            return list(dec.get("children") or [])
        return list((resp or {}).get("children") or [])
