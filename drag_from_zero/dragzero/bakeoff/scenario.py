"""The standard bake-off scenario + a deterministic, substrate-agnostic policy.

Scenario: root -> planner -> delegate an EMPTY role ("specialist") -> park -> inject -> resume ->
child done. Every adapter drives the SAME `ScriptedPolicy` (a role->decision table, no LLM), so a
difference in outcome is the substrate's, never the policy's. The scenario is deterministic: run it
twice and the normalized event signature is byte-identical (spread==0), which the bake-off asserts
before trusting any ranking (a non-deterministic challenger can't inflate the noise band into a tie).
"""
from __future__ import annotations

from .port import CAPABILITY_PROBES, ScenarioResult

INJECT_ROLE = "specialist"

# planner only — the specialist agent is intentionally absent so the run parks on it.
SCENARIO_TOPOLOGY = {
    "version": 1,
    "nodes": [{"id": "plan", "type": "agent", "role": "planner", "entry": True}],
    "edges": [],
}
SCENARIO_TASK = "do the thing that needs a specialist"


class ScriptedPolicy:
    """role -> decision, deterministic. The neutral source every substrate interprets."""

    def decide(self, role: str, observations: list) -> dict:
        if role == "planner":
            return {"action": "delegate", "target": INJECT_ROLE}
        return {"action": "solo"}  # the specialist, once injected, finishes immediately


def run_scenario(substrate) -> ScenarioResult:
    """Drive a substrate through compose -> run -> (park) -> inject -> resume and score the probes."""
    substrate.compose(SCENARIO_TOPOLOGY, ScriptedPolicy())
    substrate.run_until_idle()

    inject_clean = False
    parked = substrate.waiting_roles()
    if INJECT_ROLE in parked:
        substrate.inject(INJECT_ROLE)
        substrate.run_until_idle()
        inject_clean = substrate.is_done() and not getattr(substrate, "recomposed", False)

    caps = {p: bool(substrate.probe(p)) for p in CAPABILITY_PROBES}
    return ScenarioResult(
        candidate=substrate.name,
        inject_clean=inject_clean,
        capabilities=caps,
        events=tuple(substrate.events()),
        recomposed=getattr(substrate, "recomposed", False),
    )
