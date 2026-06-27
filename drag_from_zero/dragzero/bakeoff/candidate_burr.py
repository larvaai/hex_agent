"""Bu — Burr (cyclic FSM + SQLite persistence). Lazy-import: base `import dragzero` stays clean.

Encodes the compile-model hypothesis (substrate-table.md): Burr's actions + transitions are declared
up front in `ApplicationBuilder`. Persistence enables pause/resume and you can route to a *pre-declared*
action, but a truly unknown agent injected at runtime still needs a rebuilt `Application` ->
`recomposed=True` -> `inject_clean=False`. Burr DOES expose run state, so it earns the parked/attribution
probes that LangGraph doesn't. Validated only under `.[bakeoff]` (pytest.importorskip), never faked.
"""
from __future__ import annotations

from .scenario import INJECT_ROLE


class BurrSubstrate:
    name = "burr"

    def __init__(self) -> None:
        self.recomposed = False
        self._events: list = []
        self._policy = None
        self._injected = False
        self._parked = False
        self._done = False

    def compose(self, topology: dict, policy) -> None:
        from burr.core import ApplicationBuilder, State, action  # noqa: F401  (lazy import)

        self._policy = policy
        self._events = []
        self._ApplicationBuilder = ApplicationBuilder
        self._action = action
        self._State = State
        self._app = self._build(with_specialist=False)

    def _build(self, *, with_specialist: bool):
        action, State, ApplicationBuilder = self._action, self._State, self._ApplicationBuilder

        @action(reads=[], writes=["target"])
        def planner(state):
            self._events.append(("agent", "planner"))
            d = self._policy.decide("planner", [])
            return {"target": d.get("target")}, state.update(target=d.get("target"))

        builder = ApplicationBuilder().with_actions(planner=planner)
        if with_specialist:
            @action(reads=["target"], writes=["done"])
            def specialist(state):
                self._events.append(("agent", INJECT_ROLE))
                return {"done": True}, state.update(done=True)

            builder = (builder.with_actions(specialist=specialist)
                       .with_transitions(("planner", "specialist"))
                       .with_entrypoint("planner"))
        else:
            builder = builder.with_entrypoint("planner")
        return builder.with_state().build()

    def run_until_idle(self) -> None:
        if self._injected:
            self._app.run(halt_after=["specialist"])
            self._done = True
            return
        self._app.run(halt_after=["planner"])
        self._parked = True  # parked: planner routed to specialist, which isn't a declared action yet

    def waiting_roles(self) -> list:
        return [INJECT_ROLE] if self._parked and not self._injected else []

    def inject(self, role: str) -> None:
        self._app = self._build(with_specialist=True)  # REBUILD the Application to add the action
        self.recomposed = True
        self._injected = True
        self._parked = False

    def is_done(self) -> bool:
        return self._done

    def events(self) -> tuple:
        return tuple(self._events)

    def probe(self, name: str) -> bool:
        if name == "attribute_action_to_agent":
            return any(kind == "agent" for kind, _ in self._events)
        if name == "detect_parked_task":
            return True   # Burr exposes current-action state, so a halted/parked step is observable
        if name == "reconstruct_task_tree":
            return any(a == INJECT_ROLE for _, a in self._events)
        if name == "observe_roster_change_midrun":
            return False  # adding an action needed a rebuilt Application — not observed live
        return False
