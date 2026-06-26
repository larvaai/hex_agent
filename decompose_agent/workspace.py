"""Per-node artifact dirs + a write helper jailed to the ACTIVE node (F7).

Each node owns `var/decompose/<root>/artifacts/<node_id>/`. `write_artifact` resolves the
worker-proposed relative path UNDER the active node's dir and refuses any escape — so a
worker can never write into another node's dir to pre-satisfy its gate. The target is
forced by the active node, not read as a free path from the worker (spec.md:65, F7).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .gates import UnsafeArtifactPath
from .node import Node


def node_dir(workspace_root: str | Path, root: str, node_id: str) -> Path:
    return Path(workspace_root) / "var" / "decompose" / root / "artifacts" / node_id


def _to_text(data: Any) -> str:
    if isinstance(data, str):
        return data
    import json
    return json.dumps(data, ensure_ascii=False)


def write_artifact(workspace_root: str | Path, root: str, node: Node, rel_path: str, data: Any) -> Path:
    """Write `data` to `rel_path` under the node's own dir, refusing any path that escapes it."""
    base = node_dir(workspace_root, root, node.id)
    base.mkdir(parents=True, exist_ok=True)
    target = (base / rel_path).resolve()
    base_resolved = base.resolve()
    if target != base_resolved and base_resolved not in target.parents:
        raise UnsafeArtifactPath(f"{rel_path!r} escapes node dir for {node.id!r}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_to_text(data), encoding="utf-8")
    return target
