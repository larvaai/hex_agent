"""Drive the orchestrator with a REAL local LLM (LM Studio / llama.cpp server).

    # LM Studio default endpoint (http://localhost:1234/v1):
    python run_local.py --task "Fix parse_config and add a test"

    # point elsewhere / pick a model:
    OPENAI_BASE_URL=http://localhost:8080/v1 MODEL=qwen2.5-coder python run_local.py

This is the token-burn entrypoint: it hits real weights, so output is
non-deterministic. The harness (events, tree, gates) is byte-identical to the
deterministic tests — only the adapter behind the LLM port changed.
"""
import argparse
import os
import sys

from dragzero import Agent, Budget, Orchestrator, Roster, ToolRegistry, reduce, render_log, render_tree
from dragzero.adapters.llm_local import OpenAICompatLLM
from dragzero.adapters.tools_fs import FsSandbox, build_fs_tools


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="Fix parse_config and add a test")
    ap.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", "http://localhost:1234/v1"))
    ap.add_argument("--model", default=os.environ.get("MODEL", "local-model"))
    ap.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", "lm-studio"))
    ap.add_argument("--max-llm-calls", type=int, default=0, help="0 = unlimited; >0 registers a Budget halt")
    ap.add_argument("--sandbox", default=None, help="dir to enable filesystem tools (read/write/list) rooted there")
    args = ap.parse_args()

    roles = ["coder", "reviewer", "tester"]
    llm = OpenAICompatLLM(base_url=args.base_url, model=args.model, api_key=args.api_key, roles=roles)
    roster = Roster([Agent("planner-1", "planner", llm)] + [Agent(f"{r}-1", r, llm) for r in roles])
    budget = Budget(limit=args.max_llm_calls) if args.max_llm_calls > 0 else None
    tools = build_fs_tools() if args.sandbox else ToolRegistry()
    sandbox = FsSandbox(args.sandbox) if args.sandbox else None
    orch = Orchestrator(roster, budget=budget, tools=tools, sandbox=sandbox)

    try:
        log = orch.run(args.task)
    except Exception as exc:  # connection refused, timeout, bad payload, ...
        print(f"[!] Could not reach an LLM at {args.base_url}: {exc}", file=sys.stderr)
        print("    Start LM Studio (or a llama.cpp server) and retry.", file=sys.stderr)
        return 2

    print("=== event log (source of truth) ===")
    print(render_log(log.events()))
    print("\n=== execution tree (read-model projection) ===")
    root, _ = reduce(log.events())
    print(render_tree(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
