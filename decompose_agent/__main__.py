"""CLI: python -m decompose_agent <tree.yaml> --root <id> [--llm] [--workspace DIR]

Default worker is the deterministic ScriptedWorker(satisfy=tree) — drives the hand-baked tree
to completion with no LLM. `--llm` swaps in LocalLLMWorker (text-mode local 35B).
"""
from __future__ import annotations

import argparse
import sys
import tempfile

from .solve import solve
from .tree import load_tree
from .worker import LocalLLMWorker, ScriptedWorker


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="decompose_agent")
    ap.add_argument("tree", help="path to tree.yaml")
    ap.add_argument("--root", required=True, help="root node id to solve")
    ap.add_argument("--llm", action="store_true", help="use the local 35B instead of the demo worker")
    ap.add_argument("--workspace", default=None, help="artifact workspace dir (default: a temp dir)")
    args = ap.parse_args(argv)

    tree = load_tree(args.tree)
    workspace = args.workspace or tempfile.mkdtemp(prefix="decompose_")
    worker = LocalLLMWorker() if args.llm else ScriptedWorker(satisfy=tree)

    result = solve(tree, worker, root=args.root, workspace_root=workspace)

    for nid, node in tree.nodes.items():
        print(f"{node.status:11} {nid}")
    print(f"\nworkspace: {workspace}")
    if result.blocked is not None:
        print(f"BLOCKED: {result.blocked.node} — {result.blocked.reason}", file=sys.stderr)
        return 1
    print("ALL DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
