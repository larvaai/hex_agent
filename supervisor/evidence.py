"""Evidence classification for the acceptance gate. Epic E10/E21 (S21.33).

The acceptance gate may only honour a `passed` AC when it is backed by real
evidence on the Blackboard — not by the scaffolding artifacts the loop mints for
its own bookkeeping (session_plan / context_packet / ac_report). This module is
the single place that decides, from an artifact's `kind`, whether it counts.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from supervisor.state import TaskLoopState

# The S21.33 evidence vocabulary — an artifact whose kind is one of these IS evidence.
EVIDENCE_TYPES = frozenset({"artifact", "tool_result", "reviewer_report", "diff", "test_result"})

# Strong evidence: a typed product, not the generic `artifact` fallback. An AC backed only by
# generic artifacts still passes, but the overall verdict flags it (passed_with_risk).
STRONG_EVIDENCE_TYPES = EVIDENCE_TYPES - {"artifact"}

# Scaffolding/meta the loop produces about itself — never counts as evidence.
NON_EVIDENCE_KINDS = frozenset({"session_plan", "context_packet", "ac_report"})


def evidence_type_of(artifact: dict[str, Any]) -> str | None:
    """Classify a Blackboard artifact into its S21.33 evidence type, or None.

    None means "not valid evidence": the artifact is scaffolding, or carries no
    kind at all. Any other worker-produced kind is trusted as a generic product
    `artifact` (trust-worker — the threat model is O mis-citing scaffolding, not a
    hostile worker; see DEC in docs/decisions.md).
    """
    kind = str(artifact.get("kind", ""))
    if kind == "" or kind in NON_EVIDENCE_KINDS:
        return None
    if kind in EVIDENCE_TYPES:
        return kind
    # delegation_result + any unrecognised worker kind → generic product evidence.
    return "artifact"


def _overall_verdict(checks: list[dict[str, Any]]) -> str:
    """Annotate an ac_report with one overall verdict — read-model only, NOT a gate.

    Policy (in code, not config): ``pending`` if any AC is not passed; ``passed_with_risk`` if
    every AC passed but at least one rests solely on generic ``artifact`` evidence (no strong
    type); ``passed`` if every AC has ≥1 strong evidence type. The FINISHED decision is
    unchanged — it is still ``all_accepted`` (supervisor/state.py); this only labels the report.
    """
    if any(c.get("status") != "passed" for c in checks):
        return "pending"
    for c in checks:
        types = [t for t in c.get("evidence_types", []) if t]
        if not any(t in STRONG_EVIDENCE_TYPES for t in types):
            return "passed_with_risk"
    return "passed"


def record_ac_report(state: "TaskLoopState") -> str:
    """Snapshot every AC's status + evidence onto the Blackboard as one ac_report.

    Called once the loop reaches FINISHED, before terminate persists state. The id is
    keyed on session_id so a resume that re-calls this overwrites in place rather than
    minting a duplicate (AC6), and a worker can't accidentally squat the bare key. The
    report is itself in NON_EVIDENCE_KINDS, so it can never be cited as evidence (AC5).
    """
    report_id = f"ac_report-{state.session_id}"
    checks = [
        {
            "id": c.id,
            "text": c.text,
            "status": c.status,
            "evidence_ids": list(c.evidence_ids),
            "evidence_types": [
                evidence_type_of(state.artifacts[e]) for e in c.evidence_ids if e in state.artifacts
            ],
        }
        for c in state.acceptance_checks
    ]
    payload = {
        "kind": "ac_report",
        "session_id": state.session_id,
        "task_id": state.task_id,
        "checks": checks,
        "verdict": _overall_verdict(checks),
    }
    state.add_artifact(report_id, payload)
    return report_id
