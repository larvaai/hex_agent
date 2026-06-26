"""Orchestrator — pausable work-queue with a tool loop (Slice 1 → 3a → 4).

Each task is processed by a bounded ReAct loop: the agent may call tools
(observable as ``tool_called`` / ``tool_result`` events) before returning a
terminal decision (solo / delegate). With no tools registered, the loop runs
once and the event stream is identical to Slice 1 — every earlier invariant
holds. Execution order is deterministic (FIFO); state lives only in the log.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from .accept import accept_decomposition
from .agent import Agent, Task
from .budget import AttemptBudget, RootBudget
from .capability import Capability
from .contracts import DelegationMode, TaskStatus
from .events import Event, EventLog, EventType
from .registries import Budget, HookRegistry, RuleRegistry, ToolRegistry
from .roster import Roster
from .tools import ToolResult
from .verifier import DoneWhen, build_done_when, run_checks

K_ATTEMPTS = 3   # leaf attempts before a dwc>1 node decomposes
K_LEAF = 5       # a dwc==1 node can't be split — give it more tries before UNSOLVABLE_LEAF
MAX_DEPTH = 6


def _decomp_sig(children: list) -> str:
    """Order-independent signature of a proposal's criteria — an identical re-proposal is STUCK."""
    per_child = sorted(
        json.dumps({"check": x.get("check"), "params": x.get("params") or {}, "artifact": x.get("artifact")}, sort_keys=True)
        for c in children for x in (c.get("done_when") or [])
    )
    return hashlib.sha256(json.dumps(per_child).encode()).hexdigest()


def _clip(s, n: int = 200) -> str:
    s = str(s)
    return s if len(s) <= n else s[:n] + "…"


@dataclass
class _WorkRec:
    task: Task
    depth: int
    agent: Optional[Agent] = None
    status: str = TaskStatus.PENDING.value
    remaining: int = 0          # child tasks not yet settled
    settled: bool = False       # this task reached a terminal state
    waiting_for: Optional[str] = None  # role this parked task needs
    capability: Optional[Capability] = None  # None = ungated (default passthrough)
    spawns_used: int = 0        # children this node has directly spawned
    activated_at: Optional[float] = None  # gate-freshness floor for a done_when leaf
    decomp_sigs: list = field(default_factory=list)  # proposals seen — identical retry = STUCK


class Orchestrator:
    def __init__(
        self,
        roster: Roster,
        log: Optional[EventLog] = None,
        hooks: Optional[HookRegistry] = None,
        budget: Optional[Budget] = None,
        rules: Optional[RuleRegistry] = None,
        tools: Optional[ToolRegistry] = None,
        sandbox: object = None,
        max_tool_steps: int = 8,
        capability: Optional[Capability] = None,
        k_attempts: int = K_ATTEMPTS,
        max_depth: int = MAX_DEPTH,
        step_budget: int = 200,
    ) -> None:
        self.roster = roster
        self.log = log if log is not None else EventLog()  # NOT `log or ...`: empty EventLog is falsy (__len__)
        self.hooks = hooks or HookRegistry()
        self.budget = budget or Budget()
        self.rules = rules or RuleRegistry()
        self.tools = tools or ToolRegistry()
        self.sandbox = sandbox
        self.max_tool_steps = max_tool_steps
        self.capability = capability  # root capability; None = no gating (byte-identical to before)
        self.k_attempts = k_attempts
        self.max_depth = max_depth
        self._steps = RootBudget(max_steps=step_budget)  # decompose-path backstop (D10)
        self._task_seq = 0
        self._halted = False
        self._ready: deque[str] = deque()
        self._waiting: list[str] = []
        self._recs: dict[str, _WorkRec] = {}

    # --- mid-session roster injection (safe mid-run) ---
    def join_agent(self, agent: Agent, resume: bool = False) -> None:
        self.roster.add(agent)
        self.log.append(Event(EventType.AGENT_JOINED, agent_id=agent.id, payload={"role": agent.role}))
        self._wake_waiting()
        if resume:
            self.run_until_idle()

    def leave_agent(self, agent_id: str) -> None:
        self.roster.remove(agent_id)
        self.log.append(Event(EventType.AGENT_LEFT, agent_id=agent_id))

    def _wake_waiting(self) -> None:
        if self._halted:
            return
        for tid in list(self._waiting):
            rec = self._recs[tid]
            target = self._route(rec.task, prefer=rec.waiting_for)
            if target is not None:
                rec.agent = target
                rec.waiting_for = None
                self._waiting.remove(tid)
                self._ready.append(tid)

    # --- routing ---
    def _route(self, task: Task, prefer: Optional[str] = None) -> Optional[Agent]:
        aid = self.rules.route(task)
        if aid:
            routed = self.roster.by_role_or_id(aid)  # rules may return a role or an id
            if routed:
                return routed
        if prefer:
            return self.roster.by_role_or_id(prefer)  # None -> park until injected
        return self.roster.first()

    def _new_task_id(self) -> str:
        self._task_seq += 1
        return f"t{self._task_seq}"

    # --- lifecycle ---
    def start(self, description: str, agent: Optional[Agent] = None, done_when: Optional[list] = None) -> str:
        root = Task(id=self._new_task_id(), description=description, done_when=done_when)
        self.log.append(Event(EventType.ROOT_TASK_CREATED, task_id=root.id,
                              payload={"description": description, "done_when": done_when or []}))
        self._recs[root.id] = _WorkRec(task=root, depth=0, agent=agent or self._route(root), capability=self.capability)
        self._ready.append(root.id)
        return root.id

    def run_until_idle(self) -> EventLog:
        while self._ready and not self._halted:
            self._process_one(self._ready.popleft())
        return self.log

    def run(self, description: str, agent: Optional[Agent] = None) -> EventLog:
        self.start(description, agent=agent)
        return self.run_until_idle()

    def waiting_count(self) -> int:
        return len(self._waiting)

    def ready_count(self) -> int:
        return len(self._ready)

    def is_idle(self) -> bool:
        return not self._ready

    # --- tools ---
    def _run_tool(self, tool_call) -> ToolResult:
        tool = self.tools.get(tool_call.tool)
        if tool is None:
            return ToolResult(False, "", f"unknown tool: {tool_call.tool}")
        if self.sandbox is None:
            return ToolResult(False, "", "no sandbox configured")
        try:
            return tool.run(tool_call.args, self.sandbox)
        except Exception as exc:
            return ToolResult(False, "", f"{type(exc).__name__}: {exc}")

    # --- one unit of work ---
    def _halt(self, task_id: str) -> None:
        self.log.append(Event(
            EventType.BUDGET_EXCEEDED,
            task_id=task_id,
            payload={"used": self.budget.used, "limit": self.budget.limit},
        ))
        self._halted = True
        self._ready.clear()
        self._waiting.clear()

    def _process_one(self, task_id: str) -> None:
        rec = self._recs[task_id]
        agent = rec.agent

        if agent is None:
            self.log.append(Event(EventType.TASK_FAILED, task_id=task_id, payload={"error": "no agent available"}))
            self._terminal(rec, TaskStatus.FAILED.value)
            return

        # budget gate — one charge per LLM call; the first charge gates start
        if not self.budget.charge():
            self._halt(task_id)
            return

        rec.task.assigned_agent = agent.id
        rec.status = TaskStatus.RUNNING.value
        self.log.append(Event(EventType.TASK_STARTED, task_id=task_id, agent_id=agent.id))

        blocked = self.hooks.check("pre_plan", {"task": rec.task, "agent": agent})
        if blocked:
            self.log.append(Event(EventType.HOOK_BLOCKED, task_id=task_id, payload={"phase": "pre_plan", "reason": blocked}))
            self.log.append(Event(EventType.TASK_FAILED, task_id=task_id, agent_id=agent.id, payload={"error": blocked}))
            self._terminal(rec, TaskStatus.FAILED.value)
            return

        if rec.task.done_when:  # Gap 2: code-gated leaf — verify→retry-K→decompose
            self._solve_gated(rec, agent)
            return

        observations: list = []
        step = self._react_until_terminal(rec, agent, observations)
        if step is not None:
            self._handle_terminal(rec, agent, step)

    def _react_until_terminal(self, rec: _WorkRec, agent: Agent, observations: list):
        """Run the agent's bounded tool loop; return the terminal AgentStep, or None if the task
        already reached a terminal log state (max_tool_steps fail / budget halt)."""
        task_id = rec.task.id
        step_idx = 0
        while True:
            step = agent.step(rec.task, rec.depth, observations, step_idx, self.tools.names())
            if step.kind != "tool":
                return step
            tc = step.tool_call
            self.log.append(Event(EventType.TOOL_CALLED, task_id=task_id, agent_id=agent.id, payload={"tool": tc.tool, "args": tc.args}))
            # Gate reads the capability token, NEVER the agent's words (ADR-4). A tool outside the
            # grant is denied at the single tool-dispatch site — observable, never a crash.
            if rec.capability is not None and not rec.capability.allows_tool(tc.tool):
                self.log.append(Event(EventType.TOOL_DENIED, task_id=task_id, agent_id=agent.id, payload={"tool": tc.tool, "reason": "not in capability"}))
                result = ToolResult(False, "", f"tool {tc.tool!r} denied by capability")
            else:
                result = self._run_tool(tc)
            self.log.append(Event(
                EventType.TOOL_RESULT, task_id=task_id, agent_id=agent.id,
                payload={"tool": tc.tool, "ok": result.ok, "output": _clip(result.output), "error": result.error},
            ))
            observations.append({"tool": tc.tool, "ok": result.ok, "output": result.output, "error": result.error})
            step_idx += 1
            if step_idx >= self.max_tool_steps:
                self.log.append(Event(EventType.TASK_FAILED, task_id=task_id, agent_id=agent.id, payload={"error": "max_tool_steps exceeded"}))
                self._terminal(rec, TaskStatus.FAILED.value)
                return None
            if not self.budget.charge():  # the next step is another LLM call
                self._halt(task_id)
                return None

    def _handle_terminal(self, rec: _WorkRec, agent: Agent, step) -> None:
        task_id = rec.task.id
        plan, decision = step.plan, step.decision
        self.log.append(Event(EventType.PLAN_PRODUCED, task_id=task_id, agent_id=agent.id, payload={"plan": plan.to_dict()}))
        self.log.append(Event(EventType.DELEGATION_DECIDED, task_id=task_id, agent_id=agent.id, payload={"decision": decision.to_dict()}))

        if decision.mode == DelegationMode.DELEGATE:
            blocked = self.hooks.check("pre_delegate", {"task": rec.task, "agent": agent, "decision": decision})
            if blocked:
                self.log.append(Event(EventType.HOOK_BLOCKED, task_id=task_id, payload={"phase": "pre_delegate", "reason": blocked}))
                self._complete(task_id, "solo-fallback")
                return
            denial = self._spawn_denied(rec)  # capability budget gate (ADR-2): depth/quota/can_delegate
            if denial is not None:
                self.log.append(Event(EventType.CAPABILITY_EXHAUSTED, task_id=task_id, agent_id=agent.id, payload={"reason": denial}))
                self._complete(task_id, "capability-fallback")  # exhaustion is a hard stop → solo-close
                return
            self._spawn(rec, decision)
        else:
            self._complete(task_id, "solo")  # SOLO, or DECOMPOSE on an ungated task (no measure to shrink)

    def _spawn_denied(self, rec: _WorkRec) -> Optional[str]:
        """A reason the capability forbids this spawn, or None. None capability = ungated."""
        cap = rec.capability
        if cap is None:
            return None
        if not cap.can_delegate:
            return "delegation not permitted by capability"
        if cap.depth <= 0:
            return "max delegation depth reached"
        if rec.spawns_used >= cap.spawn_quota:
            return f"spawn quota exhausted ({cap.spawn_quota})"
        return None

    def _spawn(self, parent_rec: _WorkRec, decision) -> None:
        parent_id = parent_rec.task.id
        child = Task(
            id=self._new_task_id(),
            description=decision.subtask or parent_rec.task.description,
            parent_id=parent_id,
        )
        target = self._route(child, prefer=decision.target)
        child_cap = parent_rec.capability.attenuate() if parent_rec.capability is not None else None
        self._recs[child.id] = _WorkRec(task=child, depth=parent_rec.depth + 1, agent=target, capability=child_cap)
        parent_rec.spawns_used += 1  # counts against this node's spawn_quota
        parent_rec.remaining += 1
        parent_rec.status = TaskStatus.DELEGATED.value
        self.log.append(Event(
            EventType.SUBTASK_SPAWNED,
            task_id=child.id,
            agent_id=target.id if target else None,
            payload={"parent": parent_id, "target": decision.target, "subtask": child.description},
        ))
        if target is None:
            self._recs[child.id].waiting_for = decision.target
            self._recs[child.id].status = TaskStatus.WAITING.value
            self._waiting.append(child.id)
            self.log.append(Event(EventType.TASK_WAITING, task_id=child.id, payload={"target": decision.target}))
        else:
            self._ready.append(child.id)

    # --- Gap 2: decompose-until-trivial (code-owned verify→retry-K→decompose) ---
    def _solve_gated(self, rec: _WorkRec, agent: Agent) -> None:
        """A task with authored done_when. CODE is the verdict: K leaf attempts (each a ReAct pass
        + run_checks over the sandbox), then — if dwc>1 — ask the worker to PROPOSE children and
        accept only a strictly-smaller, covering split. Leaf-ness is discovered by exhausting K."""
        task_id = rec.task.id
        done_when = self._typed_done_when(rec.task.done_when)
        if done_when is None:  # authored criteria are forged/malformed → never silently pass
            self._block_leaf(rec, "INVALID_DONE_WHEN")
            return
        rec.activated_at = time.time()  # artifacts written from here on count as FRESH
        workspace = self.sandbox.root if self.sandbox is not None else "."
        attempts = AttemptBudget(k=K_LEAF if len(done_when) == 1 else self.k_attempts)

        while not attempts.exhausted():
            if self._steps.step_exceeded():
                self._block_leaf(rec, "STEP_BUDGET")
                return
            observations: list = []
            step = self._react_until_terminal(rec, agent, observations)
            if step is None:
                return  # halted / failed inside the react loop
            if step.decision is not None and step.decision.mode == DelegationMode.DECOMPOSE:
                self._handle_decomposition(rec, agent, list(step.decision.children), done_when)  # worker volunteered
                return
            attempts.record_attempt()
            self._steps.record_step()
            verdict = run_checks(done_when, workspace, node_id=task_id, activated_at=rec.activated_at)
            self.log.append(Event(EventType.LEAF_VERIFIED, task_id=task_id, agent_id=agent.id,
                                  payload={"verdict": verdict.node_verdict, "reasons": list(verdict.reasons)}))
            if verdict.ok:
                self._complete(task_id, "verified")
                return
            # FAIL → another attempt

        if len(done_when) == 1:  # an atomic criterion can't be split
            self._block_leaf(rec, "UNSOLVABLE_LEAF")
            return
        children = agent.decompose(rec.task, rec.depth, evidence=self._recent_failures(rec))
        self._handle_decomposition(rec, agent, children, done_when)

    def _handle_decomposition(self, rec: _WorkRec, agent: Agent, children: list, parent_done_when) -> None:
        task_id = rec.task.id
        self._steps.record_step()  # every decompose() costs a step (F3)
        if self._steps.step_exceeded():
            self._block_leaf(rec, "STEP_BUDGET")
            return
        if rec.depth >= self.max_depth:
            self._block_leaf(rec, "MAX_DEPTH")
            return
        self.log.append(Event(EventType.DECOMPOSITION_PROPOSED, task_id=task_id, agent_id=agent.id,
                              payload={"children": [c.get("id") for c in children]}))
        sig = _decomp_sig(children)
        if sig in rec.decomp_sigs:  # identical re-proposal — no spin (D4)
            self._block_leaf(rec, "STUCK_DECOMP")
            return
        rec.decomp_sigs.append(sig)
        verdict = accept_decomposition(parent_done_when, children, parent_id=task_id)  # Gate-2: pure, pre-mutation
        if not verdict.ok:
            self.log.append(Event(EventType.DECOMPOSITION_REJECTED, task_id=task_id, payload={"reasons": list(verdict.reasons)}))
            self._block_leaf(rec, "DECOMPOSE_REJECTED")  # forged/under-covering/non-shrinking → freeze, never degrade
            return
        self.log.append(Event(EventType.DECOMPOSITION_ACCEPTED, task_id=task_id,
                              payload={"children": [c.get("id") for c in verdict.children]}))
        for spec in verdict.children:  # topo-sorted; enqueued in order
            self._spawn_decomp_child(rec, spec)
        rec.status = TaskStatus.DELEGATED.value  # decomposed; closes via compose when children settle

    def _spawn_decomp_child(self, parent_rec: _WorkRec, spec: dict) -> None:
        parent_id = parent_rec.task.id
        cid = str(spec.get("id"))
        if cid in self._recs:  # never collide with an existing node id
            cid = f"{parent_id}.{cid}"
        child = Task(id=cid, description=spec.get("goal") or spec.get("title") or cid,
                     parent_id=parent_id, done_when=list(spec.get("done_when") or []))
        target = parent_rec.agent  # a decomposed child runs under the same worker
        child_cap = parent_rec.capability.attenuate() if parent_rec.capability is not None else None
        self._recs[cid] = _WorkRec(task=child, depth=parent_rec.depth + 1, agent=target, capability=child_cap)
        parent_rec.remaining += 1
        self.log.append(Event(EventType.SUBTASK_SPAWNED, task_id=cid, agent_id=target.id if target else None,
                              payload={"parent": parent_id, "subtask": child.description, "done_when": child.done_when}))
        self._ready.append(cid)

    def _block_leaf(self, rec: _WorkRec, reason: str) -> None:
        self.log.append(Event(EventType.TASK_FAILED, task_id=rec.task.id,
                              agent_id=rec.agent.id if rec.agent else None, payload={"error": reason}))
        self._terminal(rec, TaskStatus.FAILED.value)

    def _typed_done_when(self, raw):
        try:
            return build_done_when(raw or [])  # forgery/path-jail rejected at construction
        except ValueError:
            return None

    def _recent_failures(self, rec: _WorkRec) -> list:
        out: list = []
        for e in self.log.events():
            if e.type == EventType.LEAF_VERIFIED and e.task_id == rec.task.id:
                out = list(e.payload.get("reasons") or [])
        return out

    def _complete(self, task_id: str, result: str) -> None:
        rec = self._recs[task_id]
        self.log.append(Event(
            EventType.TASK_COMPLETED,
            task_id=task_id,
            agent_id=rec.agent.id if rec.agent else None,
            payload={"result": result},
        ))
        self._terminal(rec, TaskStatus.DONE.value)

    def _terminal(self, rec: _WorkRec, status: str) -> None:
        rec.status = status
        rec.settled = True
        self._settle(rec.task.id)

    def _settle(self, task_id: str) -> None:
        cur = self._recs[task_id].task.parent_id
        while cur is not None and not self._halted:
            prec = self._recs[cur]
            prec.remaining -= 1
            if prec.remaining != 0 or prec.settled:
                break
            self.log.append(Event(
                EventType.TASK_COMPLETED,
                task_id=cur,
                agent_id=prec.agent.id if prec.agent else None,
                payload={"result": "delegated"},
            ))
            prec.status = TaskStatus.DONE.value
            prec.settled = True
            cur = prec.task.parent_id
