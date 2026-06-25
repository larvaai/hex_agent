"""Evidence classification for the acceptance gate. Epic E10/E21 (S21.33).

The acceptance gate may only honour a `passed` AC when it is backed by real
evidence on the Blackboard — not by the scaffolding artifacts the loop mints for
its own bookkeeping (session_plan / context_packet / ac_report). This module is
the single place that decides, from an artifact's `kind`, whether it counts.
"""
from __future__ import annotations

from typing import Any

# The S21.33 evidence vocabulary — an artifact whose kind is one of these IS evidence.
EVIDENCE_TYPES = frozenset({"artifact", "tool_result", "reviewer_report", "diff", "test_result"})

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
