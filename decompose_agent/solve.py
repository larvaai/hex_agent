"""The Navigator loop — leaf-attempt + the real decompose recursion (spec.md:180-239).

The cursor walk IS the recursion: when a node fails its K leaf attempts (dwc>1) it decomposes,
which attaches pending children that next_node() then picks — no separate recursive descent. A
decomposed parent closes via DEC-D4: all_children_done (len>=1, F1) AND a re-assertion of its
ORIGINAL done_when in its own dir. With `reduce` fenced, a structural parent completes and a
substantive-metric parent COMPOSE_FAILs (D12/F2) — the slice surfaces the hole, it doesn't hide it.

Convergence is code-owned: a parse fumble costs no step; every worker.decompose() costs a step
(F3); μ strictly shrinks at Gate-2 (D2/DEC-D1); an identical re-decompose is STUCK (D4); depth and
the per-root step budget are hard stops (D8/D10).
"""
from __future__ import annotations

import time
from collections import namedtuple
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .accept import accept_decomposition, coverage_inputs
from .budget import AttemptBudget, ParseBudget, RootBudget
from .gates import UnsafeArtifactPath, run_checks
from .journal import Journal
from .json_repair import JsonGateError
from .node import ARTIFACTLESS_CHECKS, DoneWhen, Node
from .reduce import run_reduce
from .store import DEFAULT_DECOMPOSER_VERSION, DecompCache, decomp_id, decomp_sig
from .worker import WorkerError, assemble_4cell
from .workspace import node_dir, write_artifact

K = 3
K_LEAF = 5          # dwc==1 floor: an atomic criterion can't be split, so give it more tries
MAX_DEPTH = 6
PARSE_MAX = 8
DEFAULT_STEPS = 200

Outcome = namedtuple("Outcome", "node status reason")


@dataclass
class RunResult:
    tree: Any
    outcomes: list[Outcome]
    blocked: Outcome | None


# ── action runner (F7: writes forced into the active node's dir) ──────────────

def _run_action(action: dict, node: Node, workspace_root, root: str) -> tuple[list[str], list[str]]:
    written: list[str] = []
    rejected: list[str] = []
    if action.get("action") == "tool" and action.get("tool") == "write_artifacts":
        for rel, content in ((action.get("args") or {}).get("files") or {}).items():
            try:
                written.append(str(write_artifact(workspace_root, root, node, rel, content)))
            except UnsafeArtifactPath:
                rejected.append(rel)
    return written, rejected


def _block(tree, node_id: str, reason: str, journal: Journal) -> Outcome:
    tree.set_status(node_id, "blocked")
    journal.append(node_id, {"event": "blocked", "node": node_id, "reason": reason})
    return Outcome(node_id, "blocked", reason)


def _propagate_block(tree, node_id: str, journal: Journal) -> None:
    """A blocked node blocks its decomposed ancestors (CHILD_BLOCKED)."""
    child = node_id
    parent_id = tree.nodes[child].parent
    while parent_id is not None and parent_id in tree.nodes and tree.nodes[parent_id].status == "decomposed":
        tree.set_status(parent_id, "blocked")
        journal.append(parent_id, {"event": "blocked", "node": parent_id, "reason": f"CHILD_BLOCKED:{child}"})
        child, parent_id = parent_id, tree.nodes[parent_id].parent


# ── leaf-attempt path ─────────────────────────────────────────────────────────

def solve_leaf(tree, node_id: str, worker, budget: RootBudget, journal: Journal,
               workspace_root, root: str, parse_max: int = PARSE_MAX) -> Outcome:
    node = tree.nodes[node_id]
    tree.nodes[node_id] = replace(node, status="active", activated_at=time.time())  # stamp BEFORE writes → fresh
    journal.append(node_id, {"event": "activated", "node": node_id, "kind": "work"})
    dwc = len(node.done_when)
    attempts = AttemptBudget(k=K_LEAF if dwc == 1 else K)
    parse = ParseBudget(max_parse=parse_max)
    nd = node_dir(workspace_root, root, node_id)

    while not attempts.exhausted():
        if budget.step_exceeded():
            return _block(tree, node_id, "BUDGET", journal)  # D10
        ctx = assemble_4cell(tree.nodes[node_id], tree, journal)
        try:
            action = worker.propose(ctx)
        except WorkerError as exc:  # dead/timed-out endpoint → infra block, don't burn K attempts
            journal.append(node_id, {"event": "worker_error", "node": node_id, "error": str(exc)})
            return _block(tree, node_id, "WORKER_ERROR", journal)
        except JsonGateError as exc:
            parse.record_error()  # fumble: NO step, NO attempt
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
        return _block(tree, node_id, "UNSOLVABLE_LEAF", journal)  # D9
    return Outcome(node_id, "needs_decompose", "")  # dwc>1 → hand to the decompose path


# ── decompose path (spec.md:203-227) ──────────────────────────────────────────

# D5 (oscillation / CYCLE) is intentionally NOT implemented: with μ strictly shrinking (D2) and no
# cross-tree `needs`, a descendant's children are always strictly smaller than any ancestor's, so a
# decomposition signature can never recur down the DFS path — D5 would be unreachable. It earns its
# keep only once `needs` (or a non-shrinking μ) can reintroduce a shape; fenced until then.


def _decompose(tree, node_id: str, worker, budget: RootBudget, journal: Journal,
               workspace_root, root: str, cache: DecompCache, decomposer_version: int,
               parse_max: int) -> Outcome:
    node = tree.nodes[node_id]
    did = decomp_id(node, decomposer_version)

    cached = cache.get(did)  # idempotent resume — children returned verbatim, never re-validated
    if cached is not None:
        cache.commit(tree, node_id, cached, did)
        journal.append(node_id, {"event": "decomposed", "node": node_id, "source": "cache", "decomp_id": did})
        return Outcome(node_id, "decomposed", "")

    decomp_history: list[str] = []
    rejections = 0
    last_reason: str | None = None
    while True:
        budget.record_step()  # F3: every decompose() call costs a step
        if budget.step_exceeded():
            return _block(tree, node_id, "BUDGET", journal)
        try:
            raw = worker.decompose(node, failure_evidence=journal.tail(node_id, K), reason=last_reason)
        except WorkerError as exc:  # dead/timed-out endpoint → infra block
            journal.append(node_id, {"event": "worker_error", "node": node_id, "error": str(exc)})
            return _block(tree, node_id, "WORKER_ERROR", journal)
        except JsonGateError as exc:
            rejections += 1
            last_reason = f"DECOMP_PARSE: {exc}"
            journal.append(node_id, {"event": "decompose_parse_error", "node": node_id, "error": str(exc)})
            if rejections >= 2:
                return _block(tree, node_id, "DECOMP_PARSE", journal)
            continue
        sig = decomp_sig(raw)
        if sig in decomp_history:
            return _block(tree, node_id, "STUCK_DECOMP", journal)  # D4 — identical retry, no spin
        decomp_history.append(sig)
        verdict = accept_decomposition(node, raw)
        if verdict.ok:
            workers = list(verdict.children)
            reduce_child = _build_reduce_child(node, workers)
            children = workers + ([reduce_child] if reduce_child else [])
            if reduce_child:
                # the parent's substantive criteria now live on the reduce child (which composes
                # the workers' outputs); the parent's own gate becomes structural all_children_done
                tree.nodes[node_id] = replace(tree.nodes[node_id], done_when=(DoneWhen("all_children_done"),))
            cache.commit(tree, node_id, children, did)  # two-phase commit
            journal.append(node_id, {"event": "decomposed", "node": node_id,
                                     "children": [c["id"] for c in children], "decomp_id": did})
            return Outcome(node_id, "decomposed", "")
        rejections += 1
        last_reason = verdict.reason
        journal.append(node_id, {"event": "decompose_rejected", "node": node_id, "reasons": list(verdict.reasons)})
        if rejections >= 2:  # one charged re-decompose; a second rejection → BLOCKED
            return _block(tree, node_id, verdict.code, journal)


def _build_reduce_child(parent: Node, workers: list[dict]) -> dict | None:
    """Synthesize a reduce node that composes the workers' outputs into the parent's deliverable.
    Returns None when the parent has no substantive criteria (a purely structural parent needs no
    reduce — its children ARE the answer)."""
    substantive = [c for c in parent.done_when if c.check not in ARTIFACTLESS_CHECKS]
    if not substantive:
        return None
    return {
        "id": f"{parent.id}._reduce",
        "kind": "reduce",
        "reduce_op": "merge_json",
        "depends_on": [w["id"] for w in workers],
        "inputs": coverage_inputs(parent, workers),
        "done_when": [c.as_dict() for c in substantive],  # re-checked in the reduce's own dir
    }


def solve_reduce(tree, node_id: str, budget: RootBudget, journal: Journal, workspace_root, root: str) -> Outcome:
    """Run a reduce node by CODE (no LLM): gather sibling outputs → compose → Gate-1."""
    node = tree.nodes[node_id]
    tree.nodes[node_id] = replace(node, status="active", activated_at=time.time())  # stamp before write → fresh
    journal.append(node_id, {"event": "activated", "node": node_id, "kind": "reduce"})
    budget.record_step()
    if budget.step_exceeded():
        return _block(tree, node_id, "BUDGET", journal)
    try:
        run_reduce(tree.nodes[node_id], workspace_root, root)
    except Exception as exc:  # a broken reduce is a wiring bug, not a re-decompose trigger
        journal.append(node_id, {"event": "reduce_error", "node": node_id, "error": str(exc)})
        return _block(tree, node_id, "COMPOSE_FAIL", journal)
    gate = run_checks(tree.nodes[node_id], node_dir(workspace_root, root, node_id))
    journal.append(node_id, {"event": "reduce", "node": node_id, "op": node.reduce_op,
                             "verdict": gate.node_verdict,
                             "reasons": [r.reason for r in gate.results if not r.ok]})
    if gate.ok:
        tree.set_status(node_id, "done")
        return Outcome(node_id, "done", "")
    return _block(tree, node_id, "COMPOSE_FAIL", journal)  # composed but the aggregate fails its gate


# ── all_children_done closure + DEC-D4 compose re-assertion ───────────────────

def _close_done_parents(tree, workspace_root, root: str, journal: Journal) -> Outcome | None:
    changed = True
    compose_fail: Outcome | None = None
    while changed:
        changed = False
        for nid, node in list(tree.nodes.items()):
            if node.status != "decomposed":
                continue
            statuses = [tree.nodes[c].status for c in tree.children_of(nid)]
            if any(s not in ("done", "blocked") for s in statuses):
                continue  # children not all settled yet
            if any(s == "blocked" for s in statuses):
                continue  # CHILD_BLOCKED is handled by _propagate_block
            acd_ok = len(statuses) >= 1 and all(s == "done" for s in statuses)  # F1: 0 children → False
            gate = run_checks(node, node_dir(workspace_root, root, nid), child_statuses=statuses)
            if acd_ok and gate.ok:
                tree.set_status(nid, "done")
                journal.append(nid, {"event": "closed", "node": nid, "verdict": "PASS"})
                changed = True
            else:  # children done but parent gate fails → D12/F2, freeze (do NOT re-decompose)
                tree.set_status(nid, "blocked")
                journal.append(nid, {"event": "blocked", "node": nid, "reason": "COMPOSE_FAIL"})
                compose_fail = Outcome(nid, "blocked", "COMPOSE_FAIL")
                changed = True
    return compose_fail


# ── driver ────────────────────────────────────────────────────────────────────

def solve(tree, worker, *, root: str, workspace_root, budget: RootBudget | None = None,
          journal: Journal | None = None, parse_max: int = PARSE_MAX,
          cache: DecompCache | None = None, decomposer_version: int = DEFAULT_DECOMPOSER_VERSION) -> RunResult:
    budget = budget or RootBudget(max_steps=DEFAULT_STEPS)
    journal = journal or Journal(workspace_root, root)
    cache = cache or DecompCache(workspace_root, root)
    workspace_root = Path(workspace_root)
    outcomes: list[Outcome] = []
    blocked: Outcome | None = None

    while (node := tree.next_node()) is not None:
        nid = node.id
        if node.depth > MAX_DEPTH:  # D8
            blocked = _block(tree, nid, "MAX_DEPTH", journal)
            _propagate_block(tree, nid, journal)
            outcomes.append(blocked)
            break

        if node.kind == "reduce":  # composed by code, never the worker
            outcome = solve_reduce(tree, nid, budget, journal, workspace_root, root)
        else:
            outcome = solve_leaf(tree, nid, worker, budget, journal, workspace_root, root, parse_max)
        outcomes.append(outcome)

        if outcome.status == "done":
            cf = _close_done_parents(tree, workspace_root, root, journal)
            if cf:
                blocked = cf
                break
            continue
        if outcome.status == "needs_decompose":
            d = _decompose(tree, nid, worker, budget, journal, workspace_root, root, cache, decomposer_version, parse_max)
            outcomes.append(d)
            if d.status == "blocked":
                _propagate_block(tree, nid, journal)
                blocked = d
                break
            continue  # children are pending now — the cursor picks them up
        # leaf blocked (UNSOLVABLE_LEAF / BUDGET / PARSE_BUDGET)
        _propagate_block(tree, nid, journal)
        blocked = outcome
        break

    cf = _close_done_parents(tree, workspace_root, root, journal)
    if cf and blocked is None:
        blocked = cf
    return RunResult(tree=tree, outcomes=outcomes, blocked=blocked)
