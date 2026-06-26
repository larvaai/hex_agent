"""Content-addressed, transactional decomposition store (F4).

`decomp_id = sha256(node_id ‖ canonical_spec ‖ decomposer_version)` — same input ⇒ same id,
so retry/resume reuses the SAME children and never re-samples a temp-0 model. The staging file
IS the cache (no second store): `get` reads `decompositions/<id>.yaml` verbatim, no re-validation.
`commit` writes staging first, then attaches children-edges AND flips the parent to `decomposed`
in the in-memory tree, then persists the whole tree in ONE `os.replace` — there is no on-disk
window where the status flipped but the children are missing.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from .node import Node

DEFAULT_DECOMPOSER_VERSION = 3
_US = "␟"  # unit separator between the hash components


def canonical_spec(node: Node) -> str:
    dw = sorted(
        json.dumps({"check": c.check, "params": c.params, "artifact": c.artifact}, sort_keys=True, ensure_ascii=False)
        for c in node.done_when
    )
    return json.dumps({"id": node.id, "done_when": dw, "notes": node.notes}, sort_keys=True, ensure_ascii=False)


def decomp_id(node: Node, decomposer_version: int = DEFAULT_DECOMPOSER_VERSION) -> str:
    blob = f"{node.id}{_US}{canonical_spec(node)}{_US}{decomposer_version}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def decomp_sig(children: list[dict]) -> str:
    """Order-independent signature over the children's done_when criteria (D4 thrash detector)."""
    per_child = []
    for c in children:
        crits = sorted(
            json.dumps({"check": x.get("check"), "params": x.get("params") or {}, "artifact": x.get("artifact")},
                       sort_keys=True, ensure_ascii=False)
            for x in (c.get("done_when") or [])
        )
        per_child.append(json.dumps(crits, sort_keys=True))
    return hashlib.sha256(json.dumps(sorted(per_child)).encode("utf-8")).hexdigest()


class DecompCache:
    def __init__(self, workspace_root: str | Path, root: str) -> None:
        base = Path(workspace_root) / "var" / "decompose" / root
        self._decomp_dir = base / "decompositions"
        self.tree_state_path = base / "tree_state.yaml"

    def staging_path(self, decomp_id: str) -> Path:
        return self._decomp_dir / f"{decomp_id}.yaml"

    def get(self, decomp_id: str) -> list[dict] | None:
        p = self.staging_path(decomp_id)
        if not p.exists():
            return None
        return yaml.safe_load(p.read_text(encoding="utf-8"))  # verbatim — never re-validated

    def stage(self, decomp_id: str, children: list[dict]) -> None:
        self._decomp_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.staging_path(decomp_id).with_suffix(".tmp")
        tmp.write_text(yaml.safe_dump(children, sort_keys=False), encoding="utf-8")
        os.replace(tmp, self.staging_path(decomp_id))

    def commit(self, tree, parent_id: str, children: list[dict], decomp_id: str) -> None:
        self.stage(decomp_id, children)          # staging IS the cache — written before the tree flip
        self._attach(tree, parent_id, children)  # in-memory dict mutation (atomic, no yield)
        self._persist_tree(tree)                 # disk: one os.replace; status + children together

    def _attach(self, tree, parent_id: str, children: list[dict]) -> None:
        parent = tree.nodes[parent_id]
        for i, c in enumerate(children):
            child = Node.from_dict({**c, "parent": parent_id, "status": "pending"})
            tree.nodes[child.id] = replace(child, depth=parent.depth + 1, order=len(tree.nodes) + i)
        tree.nodes[parent_id] = replace(parent, status="decomposed")
        tree.rebuild_children()

    def _persist_tree(self, tree) -> None:
        self.tree_state_path.parent.mkdir(parents=True, exist_ok=True)
        data: list[dict[str, Any]] = [n.as_dict() for n in tree.nodes.values()]
        tmp = self.tree_state_path.with_suffix(".tmp")
        tmp.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        os.replace(tmp, self.tree_state_path)
