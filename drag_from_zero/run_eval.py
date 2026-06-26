"""Run an eval suite and print a scored report.

Deterministic by default (FakeLLM behaviours — useful as a smoke run). Use
``--real`` to evaluate a local model (LM Studio / llama.cpp): that is the
non-deterministic token burn, where you crank ``--trials`` up and read the
pass-rate / variance instead of eyeballing traces.

    python run_eval.py                       # deterministic demo
    python run_eval.py --real --trials 5     # score your local model
"""
import argparse

from dragzero import FakeLLM
from dragzero.eval import Scenario, render_report, run_suite
from dragzero.eval.scorers import (
    completed,
    expects_delegation_to,
    expects_solo,
    max_plan_calls,
    reached_role,
)

SUITE = [
    Scenario(
        name="fix-bug",
        task="Fix parse_config and add a test",
        roles=["planner", "coder", "reviewer", "tester"],
        scorers=[expects_delegation_to("coder"), reached_role("coder"), completed(), max_plan_calls(4)],
    ),
    Scenario(
        name="trivial-answer",
        task="What is the capital of France?",
        roles=["planner", "coder"],
        scorers=[expects_solo(), completed()],
    ),
]


def _deterministic_factory(_):
    def responder(ctx):
        if ctx["role"] == "planner":
            return {"plan": {"steps": [], "next": None}, "decision": {"mode": "delegate", "target": "coder", "subtask": "patch parse_config"}}
        return {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}}

    return FakeLLM(responder)


def _real_factory(args):
    from dragzero.adapters.llm_local import OpenAICompatLLM

    def factory(_):
        return OpenAICompatLLM(
            base_url=args.base_url,
            model=args.model,
            api_key=args.api_key,
            roles=["coder", "reviewer", "tester"],
        )

    return factory


def main() -> int:
    import os

    ap = argparse.ArgumentParser()
    ap.add_argument("--real", action="store_true", help="evaluate a real local model instead of FakeLLM")
    ap.add_argument("--trials", type=int, default=1)
    ap.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", "http://localhost:1234/v1"))
    ap.add_argument("--model", default=os.environ.get("MODEL", "local-model"))
    ap.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", "lm-studio"))
    args = ap.parse_args()

    factory = _real_factory(args) if args.real else _deterministic_factory
    results = run_suite(SUITE, factory, trials=args.trials)
    print(render_report(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
