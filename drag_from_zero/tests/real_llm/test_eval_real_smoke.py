"""Phase 6A — the `run_eval --real` path, shape-only. Opt-in (marker=real_llm).

Scores a real local model over trials and asserts the aggregation STRUCTURE (pass_rate in
[0,1], variance computed, N trials) — never a particular score. The number is the signal a
human reads; the test only proves the gauge aggregates real, non-deterministic runs.
"""
import os

import pytest

from dragzero.adapters.llm_local import OpenAICompatLLM
from dragzero.eval import Scenario, run_scenario
from dragzero.eval.scorers import completed, expects_delegation_to

pytestmark = pytest.mark.real_llm


def _factory(_):
    return OpenAICompatLLM(
        base_url=os.environ["OPENAI_BASE_URL"],
        model=os.environ.get("MODEL", "local-model"),
        api_key=os.environ.get("OPENAI_API_KEY", "lm-studio"),
        roles=["coder", "reviewer", "tester"],
    )


def test_real_eval_aggregates_over_trials():
    scn = Scenario(
        name="fix-bug-real",
        task="Fix parse_config and add a test",
        roles=["planner", "coder", "reviewer", "tester"],
        scorers=[expects_delegation_to("coder"), completed()],
        trials=2,
    )
    agg = run_scenario(scn, _factory, trials=2).aggregate()

    assert set(agg) == {"delegates_to:coder", "completed"}
    for name, a in agg.items():
        assert a.n == 2, f"{name} aggregated {a.n} trials, expected 2"
        assert 0.0 <= a.pass_rate <= 1.0
        assert a.variance >= 0.0
        assert a.min <= a.mean <= a.max or a.n == 0
    print("[real_llm eval]", {k: (v.pass_rate, round(v.variance, 3)) for k, v in agg.items()})
