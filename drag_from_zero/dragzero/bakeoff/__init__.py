"""Substrate bake-off (Phase 4) — answer "ever swap the zero-dep orchestrator?" by measurement.

Base `import dragzero` stays zero-dep: langgraph/burr are lazy-imported ONLY inside candidate_*; they
are an optional extra (`drag_from_zero[bakeoff]`). Importing this package pulls only the port/scenario/
score/Z pieces, never a heavy framework. The verdict is computed by the harness's bakeoff_rank.py — this
package never reimplements it.
"""
from .port import CAPABILITY_PROBES, ScenarioResult, SubstratePort
from .scenario import ScriptedPolicy, run_scenario
from .score import observability_fraction, score

__all__ = [
    "CAPABILITY_PROBES",
    "ScenarioResult",
    "SubstratePort",
    "ScriptedPolicy",
    "run_scenario",
    "observability_fraction",
    "score",
]
