"""Phase 4 — substrate bake-off (Z vs L vs Bu) on a neutral, deterministic rubric.

Z is exercised for real. L/Bu run only when their (optional) deps are installed (pytest.importorskip);
absent, they are simply not candidates and the bake-off REFUSES rather than crowning Z unopposed. The
verdict handoff is the REAL harness bakeoff_rank.py — never a reimplementation. Base `import dragzero`
must not pull langgraph/burr.
"""
import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from dragzero.bakeoff import run_scenario, score, observability_fraction, SubstratePort, CAPABILITY_PROBES
from dragzero.bakeoff.candidate_zerodep import ZeroDepSubstrate
from dragzero.bakeoff.scenario import ScriptedPolicy, INJECT_ROLE
from dragzero.bakeoff import run_bakeoff

REPO = Path(__file__).resolve().parents[2]
RANK = REPO / "harness" / "scripts" / "bakeoff_rank.py"


# --- Z: real, scored honestly on the same rubric --------------------------- #
def test_zerodep_satisfies_port_and_injects_clean():
    z = ZeroDepSubstrate()
    assert isinstance(z, SubstratePort)
    result = run_scenario(z)
    assert result.inject_clean is True            # live mid-run inject, no recompile
    assert result.recomposed is False
    # observability is the genuine probe count, not an auto-1.0; Z passes all four because it really can
    assert observability_fraction(result) == 1.0
    assert all(result.capabilities[p] for p in CAPABILITY_PROBES)
    assert score(result) == 1.0


def test_determinism_spread_zero():
    e1 = run_scenario(ZeroDepSubstrate()).events
    e2 = run_scenario(ZeroDepSubstrate()).events
    assert e1 == e2 and len(e1) > 0  # byte-identical -> spread==0; ranking can be trusted


# --- a bad substrate scores strictly below Z (good != bad) ----------------- #
class _NoParkSubstrate:
    """Mis-routes: never parks on the missing role, so the inject never lands -> inject_clean=0."""
    name = "nopark"
    recomposed = False

    def compose(self, topology, policy):
        self._done = False

    def run_until_idle(self):
        self._done = True

    def waiting_roles(self):
        return []  # never reports the parked role

    def inject(self, role):
        self.recomposed = True

    def is_done(self):
        return self._done

    def events(self):
        return ("ran",)

    def probe(self, name):
        return name == "attribute_action_to_agent"  # 1/4 observability, but it won't matter


def test_bad_substrate_scores_zero_below_z():
    bad = run_scenario(_NoParkSubstrate())
    assert bad.inject_clean is False
    assert score(bad) == 0.0
    assert score(run_scenario(ZeroDepSubstrate())) > score(bad)  # eval discipline: good beats bad


# --- port contract holds for every candidate; missing dep -> skipped ------- #
def test_zerodep_is_port():
    assert isinstance(ZeroDepSubstrate(), SubstratePort)


def test_langgraph_candidate_when_installed():
    pytest.importorskip("langgraph")
    from dragzero.bakeoff.candidate_langgraph import LangGraphSubstrate
    r = run_scenario(LangGraphSubstrate())
    assert r.recomposed is True and r.inject_clean is False  # compile-model: inject forces recompile
    assert isinstance(LangGraphSubstrate(), SubstratePort)


def test_burr_candidate_when_installed():
    pytest.importorskip("burr")
    from dragzero.bakeoff.candidate_burr import BurrSubstrate
    r = run_scenario(BurrSubstrate())
    assert r.recomposed is True and r.inject_clean is False
    assert isinstance(BurrSubstrate(), SubstratePort)


# --- base install stays zero-dep ------------------------------------------- #
def test_base_import_is_zero_dep():
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys, dragzero, dragzero.bakeoff; "
         "assert 'langgraph' not in sys.modules, 'langgraph leaked into base import'; "
         "assert 'burr' not in sys.modules, 'burr leaked into base import'; print('clean')"],
        capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "clean" in out.stdout


# --- REFUSE under 2; rank shape with 2 ------------------------------------- #
def test_under_two_refuses():
    assert run_bakeoff.under_two_reason({"zerodep": 1.0}) is not None
    assert run_bakeoff.under_two_reason({"zerodep": 1.0, "challenger": 0.0}) is None


def test_default_env_scores_only_zerodep_and_refuses():
    """Default posture has no langgraph/burr -> exactly one real candidate -> REFUSE, no crowning."""
    scored, rationale = run_bakeoff.score_candidates(run_bakeoff.available_candidates())
    assert "zerodep" in scored
    if "langgraph" not in scored and "burr" not in scored:
        assert run_bakeoff.under_two_reason(scored) is not None


@pytest.mark.skipif(not RANK.is_file(), reason="harness bakeoff_rank.py not present")
def test_verdict_cli_shape_two_candidates(tmp_path):
    """Drive the REAL bakeoff_rank.py with 2 candidates -> verdict file passes the schema (candidates>=2)."""
    run_id = "bakeoff-test-" + uuid.uuid4().hex[:8]
    # Z scores 1.0; a fake challenger scores lower. higher-is-better, low noise -> 1 trial each.
    for cand, val in (("zerodep", "1.0"), ("challenger", "0.0")):
        subprocess.run([sys.executable, str(RANK), "record", "--run", run_id,
                        "--candidate", cand, "--trial", "0", "--value", val], check=True)
    rc = subprocess.run([sys.executable, str(RANK), "rank", "--run", run_id, "--direction", "higher",
                         "--noise", "low", "--rel-band", "0.05", "--plan-dir", str(tmp_path)],
                        capture_output=True, text=True)
    assert rc.returncode == 0, rc.stderr  # winner
    verdict = json.loads((tmp_path / "bakeoff-verdict.json").read_text())
    schema = json.loads((REPO / "harness" / "schemas" / "artifact-bakeoff-verdict.json").read_text())
    for key in schema["required"]:
        assert key in verdict, f"verdict missing required key {key!r}"
    assert len(verdict["candidates"]) >= 2
    assert verdict["winner"] == "zerodep"
