"""The scalar metric — ONE number per candidate, higher is better.

score = observability_fraction         if inject_clean else 0.0
observability_fraction = (# capability probes passed) / (total probes)

inject_clean is the gate: a substrate that can't inject an agent mid-run and resume cleanly scores
0.0 no matter how observable it is — clean mid-run injection is the capability the domain runtime
exists to provide (DEC-A4). One scalar/trial is exactly what bakeoff_rank.py record --value wants.
"""
from __future__ import annotations

from .port import CAPABILITY_PROBES, ScenarioResult


def observability_fraction(result: ScenarioResult) -> float:
    if not CAPABILITY_PROBES:
        return 0.0
    passed = sum(1 for p in CAPABILITY_PROBES if result.capabilities.get(p))
    return passed / len(CAPABILITY_PROBES)


def score(result: ScenarioResult) -> float:
    return observability_fraction(result) if result.inject_clean else 0.0
