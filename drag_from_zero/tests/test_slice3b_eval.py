"""Slice 3b — the eval machinery, tested deterministically.

We score *known* FakeLLM behaviours and assert the scorers discriminate good from
bad, that trials aggregate (pass-rate, variance), and that an LLM-judge scorer
works with a fake judge. No real weights, no non-determinism here — that lives in
`run_eval.py --real`.
"""
from dragzero import FakeLLM
from dragzero.adapters.llm_local import RecordedLLM
from dragzero.eval import Scenario, render_report, run_scenario
from dragzero.eval.scorers import (
    completed,
    expects_delegation_to,
    expects_solo,
    llm_judge,
    max_plan_calls,
    no_fallback,
    reached_role,
)


def _delegate(target, subtask):
    return {"plan": {"steps": [], "next": None}, "decision": {"mode": "delegate", "target": target, "subtask": subtask}}


def _solo():
    return {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}}


def good_factory(_):
    return FakeLLM(lambda ctx: _delegate("coder", "patch parse_config") if ctx["role"] == "planner" else _solo())


def bad_factory(_):
    return FakeLLM(lambda ctx: _solo())  # never delegates


FIX = Scenario(
    name="fix-bug",
    task="Fix parse_config and add a test",
    roles=["planner", "coder"],
    scorers=[expects_delegation_to("coder"), reached_role("coder"), completed()],
)


def test_good_behaviour_scores_high():
    agg = run_scenario(FIX, good_factory, trials=3).aggregate()
    assert agg["delegates_to:coder"].pass_rate == 1.0
    assert agg["reached:coder"].pass_rate == 1.0
    assert agg["completed"].pass_rate == 1.0


def test_bad_behaviour_scores_low_but_still_completes():
    agg = run_scenario(FIX, bad_factory, trials=3).aggregate()
    assert agg["delegates_to:coder"].pass_rate == 0.0  # never delegated to coder
    assert agg["reached:coder"].pass_rate == 0.0
    assert agg["completed"].pass_rate == 1.0  # solo still finishes


def test_scorer_discriminates_solo_expectation():
    answer = Scenario("trivia", "What is 2+2?", ["planner", "coder"], [expects_solo()])
    assert run_scenario(answer, good_factory, trials=1).aggregate()["solves_solo"].pass_rate == 0.0
    assert run_scenario(answer, bad_factory, trials=1).aggregate()["solves_solo"].pass_rate == 1.0


def test_flaky_behaviour_gives_partial_pass_rate_and_variance():
    def flaky(trial):
        delegates = trial % 2 == 0
        return FakeLLM(lambda ctx: _delegate("coder", "x") if (delegates and ctx["role"] == "planner") else _solo())

    agg = run_scenario(FIX, flaky, trials=4).aggregate()
    assert agg["delegates_to:coder"].pass_rate == 0.5
    assert agg["delegates_to:coder"].variance > 0.0


def test_max_plan_calls_penalises_over_delegation():
    def chain(_):
        def r(ctx):
            if ctx["role"] == "planner":
                return _delegate("coder", "x")
            if ctx["role"] == "coder":
                return _delegate("reviewer", "y")
            return _solo()
        return FakeLLM(r)

    deep = Scenario("deep", "t", ["planner", "coder", "reviewer"], [max_plan_calls(2)])
    assert run_scenario(deep, chain, trials=1).aggregate()["<= 2 plan calls"].pass_rate == 0.0


def test_no_fallback_scorer_reads_event_log():
    # planner output is unparseable -> safe solo fallback (reasoning "fallback: ...")
    def fb(_):
        return RecordedLLM(["not json at all", '{"decision":{"mode":"solo"}}'])

    scn = Scenario("fb", "t", ["planner", "coder"], [no_fallback()])
    assert run_scenario(scn, fb, trials=1).aggregate()["no_llm_fallback"].pass_rate == 0.0


def test_llm_judge_scorer_with_fake_judge():
    judge = FakeLLM(lambda ctx: {"score": 0.9, "reason": "clean decomposition"})
    scn = Scenario("judged", "Fix parser", ["planner", "coder"], [llm_judge(judge, "Was the decomposition reasonable?")])
    agg = run_scenario(scn, good_factory, trials=1).aggregate()
    assert agg["judge"].mean == 0.9 and agg["judge"].pass_rate == 1.0


def test_render_report_smoke():
    out = render_report([run_scenario(FIX, good_factory, trials=2)])
    assert "fix-bug" in out and "delegates_to:coder" in out and "pass%" in out
