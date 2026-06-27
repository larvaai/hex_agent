"""Z — the zero-dep baseline. A thin adapter that REUSES the Orchestrator (never copies core).

It scores on the SAME neutral rubric as L/Bu — no exemption, no auto-1.0. It happens to pass all
four probes because the event-sourced design genuinely supports them (the tree is a projection of the
log, parked tasks are observable, every event carries an agent, and a join is itself a logged event),
not because the probes were written in its vocabulary. Each probe below is a real check over the log.
"""
from __future__ import annotations

import tempfile

from ..adapters.tools_fs import FsSandbox, default_tool_catalog
from ..agent import Agent
from ..events import EventType
from ..llm import FakeLLM
from ..read_model import reduce
from ..topology import Topology
from ..wiring import build_runtime
from .scenario import SCENARIO_TASK


def _responder_from_policy(policy):
    def responder(ctx):
        d = policy.decide(ctx["role"], ctx["observations"])
        if d.get("action") == "delegate":
            return {"plan": {"steps": [], "next": None},
                    "decision": {"mode": "delegate", "target": d["target"], "subtask": "specialist work"}}
        return {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}}
    return responder


class ZeroDepSubstrate:
    name = "zerodep"

    def __init__(self) -> None:
        self.recomposed = False
        self._orch = None
        self._responder = None

    def compose(self, topology: dict, policy) -> None:
        self._responder = _responder_from_policy(policy)
        sandbox = FsSandbox(tempfile.mkdtemp(prefix="dz_bakeoff_"))
        rt = build_runtime(Topology.from_dict(topology), FakeLLM(self._responder),
                           tool_catalog=default_tool_catalog(), sandbox=sandbox)
        self._orch, entry = rt.orchestrator, rt.entry
        self._orch.start(SCENARIO_TASK, agent=entry)

    def run_until_idle(self) -> None:
        self._orch.run_until_idle()

    def waiting_roles(self) -> list:
        return [self._orch._recs[tid].waiting_for for tid in self._orch._waiting]

    def inject(self, role: str) -> None:
        # live mutation: add to the running Roster + re-route the parked task. No rebuild -> clean.
        self._orch.join_agent(Agent(role, role, FakeLLM(self._responder)), resume=False)

    def is_done(self) -> bool:
        return not self._orch._ready and not self._orch._waiting

    def events(self) -> tuple:
        return tuple(e.type.value for e in self._orch.log.events())

    def probe(self, name: str) -> bool:
        log = self._orch.log.events()
        if name == "reconstruct_task_tree":
            root, nodes = reduce(log)
            return root is not None and len(nodes) >= 2
        if name == "detect_parked_task":
            return any(e.type == EventType.TASK_WAITING for e in log)
        if name == "attribute_action_to_agent":
            return any(e.agent_id for e in log
                       if e.type in (EventType.TASK_STARTED, EventType.TASK_COMPLETED))
        if name == "observe_roster_change_midrun":
            return any(e.type == EventType.AGENT_JOINED for e in log)
        return False
