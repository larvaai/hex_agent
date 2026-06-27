"""SubstratePort — the behavioural contract a substrate must satisfy to be bake-off'd.

Deliberately NOT shaped like dragzero's event vocabulary (that would auto-win Z). The probes are
neutral capability questions any orchestration substrate can be asked: can you reconstruct the task
tree? detect a parked task? attribute an action to an agent? observe the roster changing mid-run?
Each candidate — Z included — earns each probe by genuinely answering it, not by emitting "event X".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# Four neutral observability probes. Sign-off rule (DEC-A4): none may be phrased "emits dragzero
# event X" — if a probe can only be satisfied by Z's own vocabulary, it is rigged and must be rewritten.
CAPABILITY_PROBES = (
    "reconstruct_task_tree",        # after a run, can you rebuild the parent->child task tree?
    "detect_parked_task",           # mid-run, can you tell a task is blocked waiting on a missing role?
    "attribute_action_to_agent",    # can you say which agent produced a given action/step?
    "observe_roster_change_midrun", # can you observe an agent being added while the run is in flight?
)


@dataclass
class ScenarioResult:
    """One candidate's outcome on the standard scenario. `inject_clean` is the load-bearing bit:
    injected mid-run AND resumed to child-done WITHOUT recompile/restart."""
    candidate: str
    inject_clean: bool
    capabilities: dict          # {probe_name: bool} over CAPABILITY_PROBES
    events: tuple = field(default_factory=tuple)  # normalized, substrate-agnostic event signature
    recomposed: bool = False    # did injection force a rebuild/recompile? (then inject is not clean)
    note: str = ""


@runtime_checkable
class SubstratePort(Protocol):
    name: str

    def compose(self, topology: dict, policy) -> None:
        """Build a runnable substrate from a topology dict + a substrate-agnostic decision policy."""

    def run_until_idle(self) -> None:
        """Drive work until the substrate is idle (done or parked on a missing role)."""

    def waiting_roles(self) -> list:
        """Roles the substrate is currently parked on (empty when nothing is waiting)."""

    def inject(self, role: str) -> None:
        """Add an agent for `role` and make it runnable. Sets `recomposed=True` if this required
        rebuilding/recompiling the graph (i.e. it was NOT a clean live mutation)."""

    def is_done(self) -> bool:
        ...

    def events(self) -> tuple:
        """A normalized, comparable signature of what happened (for determinism checks)."""

    def probe(self, name: str) -> bool:
        """Answer one neutral capability probe by name. Unknown probe -> False."""
