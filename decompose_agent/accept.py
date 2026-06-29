"""Gate-2 — accept_decomposition: a PURE structural gate, run BEFORE any tree mutation.

The termination proof lives here: μ(node) = done_when_count, and every accepted child must
strictly shrink it (DEC-D1 — `(ℕ,<)` is well-ordered, so no infinite descent). Coverage is by
IMPLICATION (check-kind + params semantics), NOT artifact-name equality (F5): a child may cover
a parent criterion with a differently-named artifact and a tighter bound. Any violation returns
a machine-readable reason to inject back into the re-decompose prompt.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from .exec_cmd import CMD_CHECKS, CMD_TEMPLATES, CONTROL_KEYS, unsafe_path_value
from .gates import CHECK_VOCAB
from .node import ARTIFACTLESS_CHECKS, FORBIDDEN_VERDICT_KEYS, Node

MAX_FANOUT = 8
JACCARD_MAX = 0.80  # a child whose scope tokens overlap the parent's by >80% is a RENAME (D3)
_CRIT_KEYS = frozenset({"check", "params", "artifact"})
_WORD_RE = re.compile(r"[a-z0-9_]+")

# block-reason priority for the second-rejection BLOCKED code
_CODES = ("STUCK_DECOMP", "NOT_SMALLER", "SINGLETON", "FANOUT", "PROSE_CHILD", "UNDERCOVER", "RENAME",
          "unknown check", "cmd not whitelisted", "self-dependency", "cycle", "child==parent",
          "dup id", "dup title", "unsafe", "missing artifact", "verdict")


def _scope_tokens(criteria, extra=()) -> set[str]:
    """Word-set over a node's WORK content (done_when + notes/title) — NOT its id (ids share the
    parent prefix and would inflate every child's similarity). Used by the D3 rename detector."""
    parts: list[str] = [str(e) for e in extra]
    for cr in criteria:
        if isinstance(cr, dict):
            parts += [str(cr.get("check") or ""), str(cr.get("params") or ""), str(cr.get("artifact") or "")]
        else:  # a DoneWhen
            parts += [str(cr.check), str(cr.params or ""), str(cr.artifact or "")]
    toks: set[str] = set()
    for p in parts:
        toks.update(_WORD_RE.findall(p.lower()))
    return toks


def _jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def mu(node: Node) -> int:
    return len(node.done_when)


@dataclass(frozen=True)
class Accept:
    children: tuple[dict, ...]

    @property
    def ok(self) -> bool:
        return True


@dataclass(frozen=True)
class Reject:
    reasons: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return False

    @property
    def reason(self) -> str:
        return "; ".join(self.reasons)

    @property
    def code(self) -> str:
        blob = self.reason
        for c in _CODES:
            if c in blob:
                return c if (c.isupper() or "_" in c) else c
        return self.reasons[0] if self.reasons else "REJECTED"


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _unsafe_artifact(art: Any) -> bool:
    if not isinstance(art, str) or not art.strip():
        return True
    p = art.strip()
    return os.path.isabs(p) or p.startswith("~") or ".." in PurePosixPath(p).parts


def _ptr(params: dict) -> Any:
    return (params or {}).get("ptr")


def _implies(child_crit: dict, parent_crit) -> bool:
    """Does a child criterion guarantee the parent criterion? By kind + params, not artifact name."""
    cc, cp = child_crit.get("check"), child_crit.get("params") or {}
    pc, pp = parent_crit.check, parent_crit.params or {}
    if pc == "json_field_exists":  # any concrete json check on the same ptr implies existence
        return cc in ("json_field_in_range", "json_field_equals", "json_len_gte", "json_field_exists") and _ptr(cp) == _ptr(pp)
    if cc != pc:
        return False
    if pc == "file_exists":
        return True  # any produced file covers (F5: artifact rename is legal)
    if pc == "grep_absent":
        return cp.get("pattern") == pp.get("pattern")
    if pc == "grep_matches":
        return cp.get("pattern") == pp.get("pattern") and int(cp.get("min", 1)) >= int(pp.get("min", 1))
    if pc in ("row_count_gte", "file_nonempty_lines"):
        key = "n" if pc == "row_count_gte" else "min"
        return int(cp.get(key, 0)) >= int(pp.get(key, 0))
    if pc == "json_len_gte":
        return _ptr(cp) == _ptr(pp) and int(cp.get("n", 0)) >= int(pp.get("n", 0))
    if pc == "json_field_equals":
        return _ptr(cp) == _ptr(pp) and cp.get("value") == pp.get("value")
    if pc == "json_field_in_range":
        try:
            return _ptr(cp) == _ptr(pp) and float(cp["min"]) >= float(pp["min"]) and float(cp["max"]) <= float(pp["max"])
        except (KeyError, TypeError, ValueError):
            return False
    return False  # undefined implication for this kind → treat as NOT covered (safe, strict)


def _has_cycle(children: list[dict]) -> bool:
    by_id = {c.get("id"): c for c in children if c.get("id")}
    indeg = {cid: 0 for cid in by_id}
    for c in children:
        for d in c.get("depends_on") or []:
            if d in by_id:
                indeg[c["id"]] += 1
    queue = [cid for cid, d in indeg.items() if d == 0]
    seen = 0
    while queue:
        cur = queue.pop()
        seen += 1
        for c in children:
            if cur in (c.get("depends_on") or []) and c.get("id") in indeg:
                indeg[c["id"]] -= 1
                if indeg[c["id"]] == 0:
                    queue.append(c["id"])
    return seen != len(by_id)


def topo_sort(children: list[dict]) -> list[dict]:
    by_id = {c["id"]: c for c in children if c.get("id")}
    indeg = {cid: 0 for cid in by_id}
    for c in children:
        for d in c.get("depends_on") or []:
            if d in by_id:
                indeg[c["id"]] += 1
    ordered: list[dict] = []
    ready = [c for c in children if indeg.get(c.get("id"), 0) == 0]  # preserve input order
    while ready:
        cur = ready.pop(0)
        ordered.append(cur)
        for c in children:
            if cur.get("id") in (c.get("depends_on") or []) and c.get("id") in indeg:
                indeg[c["id"]] -= 1
                if indeg[c["id"]] == 0:
                    ready.append(c)
    return ordered if len(ordered) == len(children) else list(children)


def coverage_inputs(parent: Node, children: list[dict]) -> list[dict]:
    """For each substantive parent criterion, the covering child output to compose: a list of
    {from, artifact, as} mapping a child's artifact onto the parent criterion's artifact name.
    Assumes coverage already held (accept passed), so every criterion has a cover."""
    inputs: list[dict] = []
    for pcrit in parent.done_when:
        if pcrit.check in ARTIFACTLESS_CHECKS:
            continue
        for c in children:
            match = next((cc for cc in (c.get("done_when") or []) if _implies(cc, pcrit)), None)
            if match is not None:
                inputs.append({"from": c.get("id"), "artifact": match.get("artifact"), "as": pcrit.artifact})
                break
    return inputs


def accept_decomposition(parent: Node, children: list[dict]) -> Accept | Reject:
    V: list[str] = []
    n = len(children)
    if n < 2:
        V.append("SINGLETON: need >=2 children (1-child split = rename)")
    if n > MAX_FANOUT:
        V.append(f"FANOUT: >{MAX_FANOUT} children")

    parent_mu = mu(parent)
    parent_title = _norm(parent.id)
    parent_tokens = _scope_tokens(parent.done_when)  # D3 reference — structural content only, no notes
    visible_deps = set(parent.depends_on)
    child_ids = {c.get("id") for c in children if c.get("id")}
    ids: set[str] = set()
    titles: set[str] = set()

    for c in children:
        cid = c.get("id")
        if not cid:
            V.append("child missing id")
            continue
        title = _norm(c.get("title") or cid)
        if cid == parent.id or title == parent_title:
            V.append(f"{cid}: child==parent")
        if cid in ids:
            V.append(f"dup id {cid}")
        if title in titles:
            V.append(f"dup title {c.get('title') or cid}")
        ids.add(cid)
        titles.add(title)

        dw = c.get("done_when") or []
        if not dw:
            V.append(f"{cid}: empty done_when (PROSE_CHILD)")
        if len(dw) >= parent_mu:
            V.append(f"{cid}: NOT_SMALLER (mu {len(dw)} >= parent {parent_mu})")
        if dw and parent_tokens:  # D3: a child that just restates the parent is a rename, not a split
            child_tokens = _scope_tokens(dw)  # structural only — notes can't dilute the score
            if _jaccard(parent_tokens, child_tokens) > JACCARD_MAX:
                V.append(f"{cid}: RENAME of parent (jaccard > {JACCARD_MAX})")
        for crit in dw:
            if not isinstance(crit, dict):
                V.append(f"{cid}: malformed criterion")
                continue
            forged = (set(crit) - _CRIT_KEYS) & FORBIDDEN_VERDICT_KEYS
            if forged:
                V.append(f"{cid}: self-grade verdict field {sorted(forged)} forbidden")
            check = crit.get("check")
            if check not in CHECK_VOCAB and check not in ARTIFACTLESS_CHECKS and check not in CMD_CHECKS:
                V.append(f"{cid}: unknown check {check!r} (prose)")
            if check in CMD_CHECKS:  # cmd checks: whitelisted cmd_id only, no verdict-shaping, jailed params
                p = crit.get("params") or {}
                if p.get("cmd_id") not in CMD_TEMPLATES:
                    V.append(f"{cid}: cmd not whitelisted (cmd_id={p.get('cmd_id')!r})")
                if "expect_code" in p:  # the success code is fixed at 0; the author must not set it
                    V.append(f"{cid}: expect_code is operator-controlled, not author-settable")
                if "timeout" in p and not isinstance(p["timeout"], (int, float)):
                    V.append(f"{cid}: cmd timeout must be a number")
                for key, value in p.items():
                    if key not in CONTROL_KEYS and unsafe_path_value(value):
                        V.append(f"{cid}: unsafe path in cmd param {key!r}")
            elif check not in ARTIFACTLESS_CHECKS:
                art = crit.get("artifact")
                if not art:
                    V.append(f"{cid}: missing artifact for {check}")
                elif _unsafe_artifact(art):
                    V.append(f"{cid}: unsafe artifact {art!r}")

        for d in c.get("depends_on") or []:
            if d == cid:
                V.append(f"{cid}: self-dependency")
            elif d not in child_ids and d not in visible_deps:
                V.append(f"{cid}: depends_on unknown {d}")

    # coverage (D6): every substantive parent criterion implied by >=1 child criterion
    for pcrit in parent.done_when:
        if pcrit.check in ARTIFACTLESS_CHECKS:
            continue
        covered = any(_implies(cc, pcrit) for c in children for cc in (c.get("done_when") or []))
        if not covered:
            V.append(f"UNDERCOVER: parent criterion {pcrit.check}@{_ptr(pcrit.params)} not implied by any child")

    if _has_cycle(children):
        V.append("dep cycle among children / not topo-orderable")

    if V:
        return Reject(tuple(V))
    return Accept(tuple(topo_sort(children)))
