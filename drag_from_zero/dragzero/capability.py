"""Capability token + attenuation (ADR-1..4) — the THIN authority layer.

A capability is an IMMUTABLE token threaded down the spawn tree. The one law: a child's
capability is a SUBSET of its parent's — `attenuate()` can only narrow, never widen, and any
widen attempt raises. The Gate reads the token, never the agent's words (ADR-4): a tool not in
`capability.tools` is denied at the dispatch chokepoint regardless of what the model asked for.

Two descending budgets bound delegation (ADR-2): `depth` (chain length, decremented one per level
so a chain always terminates) and `spawn_quota` (how many children a node may directly spawn).
Exhaustion is a hard stop, surfaced as an event — never a silent over-run.

Default is permissive (all tools, unbounded): a run with `capability=None` is byte-identical to
no gating. Authority is opt-in narrowing, exactly as the design doc orders it (authz last).
"""
from __future__ import annotations

from dataclasses import dataclass, field


class CapabilityError(ValueError):
    """An attenuation tried to WIDEN a capability — forbidden (ADR-1)."""


@dataclass(frozen=True)
class Capability:
    tools: frozenset = field(default_factory=frozenset)
    can_delegate: bool = True
    depth: int = 8           # remaining delegation levels below this node
    spawn_quota: int = 8     # children this node may directly spawn

    def allows_tool(self, name: str) -> bool:
        return name in self.tools

    def attenuate(self, *, tools=None, can_delegate=None, depth=None, spawn_quota=None) -> "Capability":
        """Return a NEW capability that is a subset of self. `depth` ALWAYS decrements by one
        (even when the child requests the parent's value), so a chain cannot stall the per-level
        budget. Any request that would widen self raises CapabilityError."""
        new_tools = self.tools if tools is None else frozenset(tools)
        if not new_tools <= self.tools:
            raise CapabilityError(f"cannot widen tools: +{sorted(new_tools - self.tools)}")

        new_can = self.can_delegate if can_delegate is None else bool(can_delegate)
        if new_can and not self.can_delegate:
            raise CapabilityError("cannot grant can_delegate a parent does not hold")

        req_depth = self.depth if depth is None else int(depth)
        if req_depth > self.depth:
            raise CapabilityError(f"cannot widen depth {req_depth} > {self.depth}")
        new_depth = min(req_depth, self.depth) - 1  # per-level decrement, equal case still narrows

        req_quota = self.spawn_quota if spawn_quota is None else int(spawn_quota)
        if req_quota > self.spawn_quota:
            raise CapabilityError(f"cannot widen spawn_quota {req_quota} > {self.spawn_quota}")
        new_quota = min(req_quota, self.spawn_quota)

        return Capability(tools=new_tools, can_delegate=new_can, depth=new_depth, spawn_quota=new_quota)


def permissive(tools=()) -> Capability:
    """An explicit all-allowing capability (for tests/topologies that want gating ON but open)."""
    return Capability(tools=frozenset(tools), can_delegate=True, depth=64, spawn_quota=64)
