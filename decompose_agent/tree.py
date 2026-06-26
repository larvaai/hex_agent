"""tree.yaml loader + DFS cursor.

The disk is the truth. `load_tree` validates referential integrity (every `parent` and
`depends_on` id exists) and acyclicity (both the `parent` forest and the `depends_on`
graph) at load time, in CODE — a malformed tree never reaches the solver. `next_node`
is the cursor: the leftmost `pending` node whose dependencies are all `done`, by
`(depth, order)`. The topo order over `depends_on` IS the "don't climb early" rule, free
(spec.md:247).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from .node import Node


@dataclass
class Tree:
    """The live node set. The Navigator owns it; status transitions replace frozen nodes."""

    nodes: dict[str, Node]
    _children: dict[str, tuple[str, ...]]

    def children_of(self, node_id: str) -> tuple[str, ...]:
        return self._children.get(node_id, ())

    def set_status(self, node_id: str, status: str) -> None:
        self.nodes[node_id] = replace(self.nodes[node_id], status=status)

    def next_node(self) -> Node | None:
        ready = [
            n for n in self.nodes.values()
            if n.status == "pending"
            and all(self.nodes[dep].status == "done" for dep in n.depends_on)
        ]
        if not ready:
            return None
        return min(ready, key=lambda n: (n.depth, n.order))


def _node_dicts(raw: Any, path: Path) -> list[dict[str, Any]]:
    if isinstance(raw, dict) and "nodes" in raw:
        raw = raw["nodes"]
    if not isinstance(raw, list):
        raise ValueError(f"{path}: tree must be a list of nodes (or a mapping with a 'nodes' list)")
    return raw


def _depth_of(node_id: str, nodes: dict[str, Node]) -> int:
    """Walk the parent chain to the root, detecting a parent cycle."""
    depth = 0
    seen: set[str] = set()
    current = node_id
    while True:
        parent = nodes[current].parent
        if parent is None:
            return depth
        if parent in seen:
            raise ValueError(f"parent cycle through node {current!r}")
        seen.add(current)
        current = parent
        depth += 1


def _assert_depends_on_acyclic(nodes: dict[str, Node]) -> None:
    """Kahn topo-sort over depends_on edges; any unprocessed node ⇒ a cycle."""
    indegree = {nid: len(n.depends_on) for nid, n in nodes.items()}
    dependents: dict[str, list[str]] = {nid: [] for nid in nodes}
    for nid, n in nodes.items():
        for dep in n.depends_on:
            dependents[dep].append(nid)
    queue = [nid for nid, deg in indegree.items() if deg == 0]
    processed = 0
    while queue:
        cur = queue.pop()
        processed += 1
        for dependent in dependents[cur]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                queue.append(dependent)
    if processed != len(nodes):
        stuck = sorted(nid for nid, deg in indegree.items() if deg > 0)
        raise ValueError(f"depends_on cycle among nodes: {stuck}")


def load_tree(path: str | Path) -> Tree:
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    nodes: dict[str, Node] = {}
    for order, d in enumerate(_node_dicts(raw, path)):
        node = replace(Node.from_dict(d), order=order)
        if node.id in nodes:
            raise ValueError(f"{path}: duplicate node id {node.id!r}")
        nodes[node.id] = node

    # referential integrity — parent + every depends_on must resolve
    for node in nodes.values():
        if node.parent is not None and node.parent not in nodes:
            raise ValueError(f"node {node.id!r} has unknown parent {node.parent!r}")
        for dep in node.depends_on:
            if dep not in nodes:
                raise ValueError(f"node {node.id!r} depends_on unknown node {dep!r}")

    # acyclic — parent forest + depends_on graph; assign depth from the parent chain
    for nid in nodes:
        depth = _depth_of(nid, nodes)
        nodes[nid] = replace(nodes[nid], depth=depth)
    _assert_depends_on_acyclic(nodes)

    children: dict[str, list[str]] = {nid: [] for nid in nodes}
    for node in nodes.values():
        if node.parent is not None:
            children[node.parent].append(node.id)
    return Tree(nodes=nodes, _children={k: tuple(v) for k, v in children.items()})
