"""Evidence classification unit tests — acceptance gate. Epic E10/E21 (S21.33)."""
from __future__ import annotations

from supervisor.evidence import EVIDENCE_TYPES, NON_EVIDENCE_KINDS, evidence_type_of


def test_evidence_type_sets_are_disjoint():
    # A kind is either an evidence type or scaffolding, never both.
    assert EVIDENCE_TYPES.isdisjoint(NON_EVIDENCE_KINDS)


def test_tool_result_is_its_own_type():
    assert evidence_type_of({"kind": "tool_result"}) == "tool_result"


def test_delegation_result_maps_to_artifact():
    # A worker's delegation_result is the product wrapper → generic "artifact" evidence.
    assert evidence_type_of({"kind": "delegation_result"}) == "artifact"


def test_typed_agent_artifacts_pass_through():
    assert evidence_type_of({"kind": "diff"}) == "diff"
    assert evidence_type_of({"kind": "test_result"}) == "test_result"
    assert evidence_type_of({"kind": "reviewer_report"}) == "reviewer_report"


def test_scaffolding_kinds_are_not_evidence():
    assert evidence_type_of({"kind": "context_packet"}) is None
    assert evidence_type_of({"kind": "session_plan"}) is None
    assert evidence_type_of({"kind": "ac_report"}) is None


def test_unknown_worker_kind_defaults_to_artifact():
    # trust-worker: an unrecognised worker kind still counts as a product artifact (DEC).
    assert evidence_type_of({"kind": "weird_unknown"}) == "artifact"


def test_missing_or_empty_kind_is_not_evidence():
    # An artifact with no kind is not classifiable → not evidence (defensive, red-team FM-MED).
    assert evidence_type_of({}) is None
    assert evidence_type_of({"kind": ""}) is None
