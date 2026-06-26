"""Run scenarios over trials, aggregate scores, render a report."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from ..agent import Agent
from ..orchestrator import Orchestrator
from ..read_model import reduce
from ..registries import ToolRegistry
from ..roster import Roster
from .model import EvalContext, ScoreResult, ScorerAgg


def run_trial(scenario, llm) -> EvalContext:
    """Run one scenario trial with a given LLM and return its eval context."""
    roster = Roster([Agent(f"{r}-1", r, llm) for r in scenario.roles])
    tools = ToolRegistry()
    for tool in getattr(scenario, "tools", None) or []:
        tools.register(tool)
    sandbox = scenario.sandbox_factory() if getattr(scenario, "sandbox_factory", None) else None
    orch = Orchestrator(roster, tools=tools, sandbox=sandbox)
    entry = scenario.entry_role or scenario.roles[0]
    orch.run(scenario.task, agent=roster.by_role_or_id(entry))
    orch.run_until_idle()  # drain anything still ready (no-op if already idle)
    root, nodes = reduce(orch.log.events())
    return EvalContext(scenario, orch.log, root, nodes, orch)


def _scorer_name(scorer) -> str:
    return getattr(scorer, "score_name", getattr(scorer, "__name__", "scorer"))


@dataclass
class ScenarioResult:
    scenario: object
    trials: list  # list[list[ScoreResult]]

    def aggregate(self) -> dict:
        grouped: dict = {}
        for trial in self.trials:
            for sr in trial:
                grouped.setdefault(sr.name, []).append(sr)
        out: dict = {}
        for name, results in grouped.items():
            scores = [r.score for r in results]
            passes = [1 for r in results if r.passed]
            out[name] = ScorerAgg(
                name=name,
                n=len(scores),
                pass_rate=len(passes) / len(scores),
                mean=sum(scores) / len(scores),
                min=min(scores),
                max=max(scores),
                variance=_variance(scores),
            )
        return out


def _variance(xs) -> float:
    if not xs:
        return 0.0
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs) / len(xs)


def run_scenario(scenario, llm_factory: Callable[[int], object], trials: Optional[int] = None) -> ScenarioResult:
    """`llm_factory(trial_index) -> LLM`. A crashed trial scores every scorer 0."""
    n = trials if trials is not None else scenario.trials
    all_trials = []
    for i in range(n):
        llm = llm_factory(i)
        try:
            ctx = run_trial(scenario, llm)
            scores = [scorer(ctx) for scorer in scenario.scorers]
        except Exception as exc:  # transport/timeout/etc — a real eval signal
            scores = [ScoreResult(_scorer_name(s), 0.0, False, f"trial error: {exc}") for s in scenario.scorers]
        all_trials.append(scores)
    return ScenarioResult(scenario, all_trials)


def run_suite(scenarios, llm_factory, trials: Optional[int] = None) -> list:
    return [run_scenario(s, llm_factory, trials) for s in scenarios]


def render_report(scenario_results) -> str:
    lines = []
    for sr in scenario_results:
        agg = sr.aggregate()
        lines.append(f"## {sr.scenario.name}   task={sr.scenario.task!r}   trials={len(sr.trials)}")
        lines.append(f"  {'scorer':<26}{'pass%':>7}{'mean':>7}{'min':>6}{'max':>6}{'var':>8}")
        for name, a in agg.items():
            lines.append(
                f"  {name:<26}{a.pass_rate * 100:>6.0f}%{a.mean:>7.2f}{a.min:>6.2f}{a.max:>6.2f}{a.variance:>8.3f}"
            )
        lines.append("")
    return "\n".join(lines).rstrip()
