"""L — LangGraph (`StateGraph`). Lazy-import: `import dragzero` must NOT pull langgraph in.

Encodes the compile-model hypothesis (substrate-table.md): a StateGraph compiles to a fixed Pregel
graph, so injecting an agent unknown at build time forces a rebuild+recompile -> `recomposed=True` ->
`inject_clean=False`. The probes are answered honestly from what the framework exposes; the ones it
can't satisfy are scored False (real point loss, with rationale), never silently passed.

Validated only when `.[bakeoff]` is installed (tests use pytest.importorskip). If langgraph behaves
differently than modeled here, the importorskip test FAILS loudly — it never silently fakes a pass.
"""
from __future__ import annotations

from .scenario import INJECT_ROLE


class LangGraphSubstrate:
    name = "langgraph"

    def __init__(self) -> None:
        self.recomposed = False
        self._events: list = []
        self._policy = None
        self._injected = False
        self._parked = False
        self._done = False

    def compose(self, topology: dict, policy) -> None:
        from langgraph.graph import StateGraph, START, END  # noqa: F401  (lazy — ImportError => unavailable)

        self._policy = policy
        self._events = []

        def planner(state):
            self._events.append(("agent", "planner"))
            d = policy.decide("planner", [])
            return {"target": d.get("target"), "route": d.get("action")}

        sg = StateGraph(dict)
        sg.add_node("planner", planner)
        sg.add_edge(START, "planner")
        sg.add_edge("planner", END)  # the specialist node is intentionally absent (the missing role)
        self._graph = sg.compile()

    def run_until_idle(self) -> None:
        if self._injected:
            self._graph.invoke({})
            self._done = True
            return
        state = self._graph.invoke({})
        # StateGraph has no native "parked" state — a missing route target just ends. We infer the
        # park from the planner's decision; this inference is itself a point against detect_parked.
        self._parked = state.get("target") == INJECT_ROLE

    def waiting_roles(self) -> list:
        return [INJECT_ROLE] if self._parked and not self._injected else []

    def inject(self, role: str) -> None:
        from langgraph.graph import StateGraph, START, END

        def planner(state):
            self._events.append(("agent", "planner"))
            return {"route": "delegate", "target": role}

        def specialist(state):
            self._events.append(("agent", role))
            return {"done": True}

        sg = StateGraph(dict)
        sg.add_node("planner", planner)
        sg.add_node(role, specialist)
        sg.add_edge(START, "planner")
        sg.add_edge("planner", role)
        sg.add_edge(role, END)
        self._graph = sg.compile()   # REBUILD: not a live mutation of the running graph
        self.recomposed = True
        self._injected = True
        self._parked = False

    def is_done(self) -> bool:
        return self._done

    def events(self) -> tuple:
        return tuple(self._events)

    def probe(self, name: str) -> bool:
        if name == "attribute_action_to_agent":
            return any(kind == "agent" for kind, _ in self._events)  # node names map to agents
        if name == "reconstruct_task_tree":
            return any(a == INJECT_ROLE for _, a in self._events)    # only after a rebuild adds the node
        # no first-class parked state; roster change needed a recompile -> couldn't observe it live
        if name in ("detect_parked_task", "observe_roster_change_midrun"):
            return False
        return False
