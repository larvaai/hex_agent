"""The Navigator loop — leaf-attempt path (spec.md:180-201), no live decompose yet.

Cursor walk: next_node() hands out the leftmost pending node whose deps are done; solve_leaf
runs activate → propose → run → Gate-1 → DONE | retry-K | BLOCKED. Parents close via the
all_children_done closure once every child is done. Two budget rules the spec is explicit
about: a parse fumble costs NO step (it is not progress), and the per-root step budget is the
real terminator (D10). A dwc==1 leaf that exhausts its K-floor is UNSOLVABLE_LEAF (D9); a
dwc>1 leaf that exhausts K is left as NEEDS_DECOMPOSE — phase 4 wires the decompose path there.
"""
from __future__ import annotations

import time
from collections import namedtuple
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .budget import AttemptBudget, ParseBudget, RootBudget
from .gates import UnsafeArtifactPath, run_checks
from .journal import Journal
from .json_repair import JsonGateError
from .node import Node
from .worker import assemble_4cell
from .workspace import node_dir, write_artifact

K = 3
K_LEAF = 5          # dwc==1 floor: cannot split an atomic criterion, give it more tries
MAX_DEPTH = 6
PARSE_MAX = 8
DEFAULT_STEPS = 200

Outcome = namedtuple("Outcome", "node status reason")


@dataclass
class RunResult:
    tree: Any
    outcomes: list[Outcome]
    blocked: Outcome | None


def _run_action(action: dict, node: Node, workspace_root, root: str) -> tuple[list[str], list[str]]:
    """Execute the action — only `write_artifacts`, with every write jailed to the node's dir.
    A path that escapes (F7) is rejected and recorded; it is NOT written."""
    written: list[str] = []
    rejected: list[str] = []
    if action.get("action") == "tool" and action.get("tool") == "write_artifacts":
        files = (action.get("args") or {}).get("files") or {}
        for rel, content in files.items():
            try:
                written.append(str(write_artifact(workspace_root, root, node, rel, content)))
            except UnsafeArtifactPath:
                rejected.append(rel)
    return written, rejected


def _block(tree, node_id: str, reason: str, journal: Journal) -> Outcome:
    tree.set_status(node_id, "blocked")
    journal.append(node_id, {"event": "blocked", "node": node_id, "reason": reason})
    return Outcome(node_id, "blocked", reason)


def solve_leaf(tree, node_id: str, worker, budget: RootBudget, journal: Journal,
               workspace_root, root: str, parse_max: int = PARSE_MAX) -> Outcome:
    node = tree.nodes[node_id]
    # activate: stamp activated_at BEFORE any write so artifacts are fresh (mtime >= activated_at)
    tree.nodes[node_id] = replace(node, status="active", activated_at=time.time())
    dwc = len(node.done_when)
    attempts = AttemptBudget(k=K_LEAF if dwc == 1 else K)
    parse = ParseBudget(max_parse=parse_max)
    nd = node_dir(workspace_root, root, node_id)

    while not attempts.exhausted():
        if budget.step_exceeded():
            return _block(tree, node_id, "BUDGET", journal)  # D10 hard stop
        ctx = assemble_4cell(tree.nodes[node_id], tree, journal)
        try:
            action = worker.propose(ctx)
        except JsonGateError as exc:
            parse.record_error()  # a fumble — NO step, NO attempt consumed
            journal.append(node_id, {"event": "parse_error", "node": node_id, "error": str(exc)})
            if parse.parse_exceeded():
                return _block(tree, node_id, "PARSE_BUDGET", journal)
            continue
        parse.record_success()
        attempts.record_attempt()
        budget.record_step()
        _, rejected = _run_action(action, tree.nodes[node_id], workspace_root, root)
        gate = run_checks(tree.nodes[node_id], nd)
        journal.append(node_id, {
            "event": "attempt", "node": node_id, "action": action,
            "verdict": gate.node_verdict, "rejected": rejected,
            "reasons": [r.reason for r in gate.results if not r.ok],
        })
        if gate.ok:
            tree.set_status(node_id, "done")
            return Outcome(node_id, "done", "")

    if dwc == 1:
        return _block(tree, node_id, "UNSOLVABLE_LEAF", journal)  # D9 leaf floor
    return _block(tree, node_id, "NEEDS_DECOMPOSE", journal)  # phase 4 replaces this branch


def _close_done_parents(tree, workspace_root, root: str, journal: Journal) -> None:
    """all_children_done closure: mark a decomposed parent done once every child is done.
    Fixpoint, so a parent-of-parents closes in the same call."""
    changed = True
    while changed:
        changed = False
        for nid, node in list(tree.nodes.items()):
            if node.status != "decomposed":
                continue
            statuses = [tree.nodes[c].status for c in tree.children_of(nid)]
            if run_checks(node, node_dir(workspace_root, root, nid), child_statuses=statuses).ok:
                tree.set_status(nid, "done")
                journal.append(nid, {"event": "closed", "node": nid, "verdict": "PASS"})
                changed = True


def solve(tree, worker, *, root: str, workspace_root, budget: RootBudget | None = None,
          journal: Journal | None = None, parse_max: int = PARSE_MAX) -> RunResult:
    """Drive the whole tree to done (or stop at the first blocked node)."""
    budget = budget or RootBudget(max_steps=DEFAULT_STEPS)
    journal = journal or Journal(workspace_root, root)
    workspace_root = Path(workspace_root)
    outcomes: list[Outcome] = []
    blocked: Outcome | None = None

    while (node := tree.next_node()) is not None:
        outcome = solve_leaf(tree, node.id, worker, budget, journal, workspace_root, root, parse_max)
        outcomes.append(outcome)
        if outcome.status == "blocked":
            blocked = outcome
            break
        _close_done_parents(tree, workspace_root, root, journal)

    _close_done_parents(tree, workspace_root, root, journal)
    return RunResult(tree=tree, outcomes=outcomes, blocked=blocked)
