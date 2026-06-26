"""Pure-code compose for reduce nodes — closes COMPOSE_FAIL.

A reduce node gathers its siblings' output artifacts (named by `inputs`) and writes the aggregate
into its OWN dir, where its done_when then checks it. No 35B — this is deterministic Navigator
code, so it is allowed to read sibling dirs (unlike the jailed worker). `reduce_op`:

  * merge_json — deep-merge all JSON inputs sharing a destination → the dst (the metric aggregate)
  * pick       — copy each input verbatim to its destination
  * concat     — concatenate text inputs sharing a destination
  * manifest   — write a JSON listing of the inputs (existence + size)

`inputs` items are {from: <sibling_id>, artifact: <rel-in-sibling-dir>, as?: <dst-rel, default=artifact>}.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .node import Node
from .workspace import node_dir


def resolve_inputs(node: Node, workspace_root: str | Path, root: str) -> list[tuple[str, Path]]:
    """(dst_rel, absolute source path) for each input. Navigator-resolved at activation; the
    `from` sibling is already done, so its artifact exists."""
    resolved: list[tuple[str, Path]] = []
    for item in node.inputs:
        src = node_dir(workspace_root, root, item["from"]) / item["artifact"]
        dst = item.get("as") or item["artifact"]
        resolved.append((dst, src))
    return resolved


def _deep_merge(into: dict, src: dict) -> dict:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(into.get(k), dict):
            _deep_merge(into[k], v)
        else:
            into[k] = v
    return into


def run_reduce(node: Node, workspace_root: str | Path, root: str) -> None:
    """Execute the node's reduce_op, writing every aggregate into the reduce node's own dir."""
    out_dir = node_dir(workspace_root, root, node.id)
    out_dir.mkdir(parents=True, exist_ok=True)
    resolved = resolve_inputs(node, workspace_root, root)

    if node.reduce_op == "manifest":
        target = node.done_when[0].artifact if node.done_when and node.done_when[0].artifact else "manifest.json"
        inputs = [{"from": i["from"], "artifact": i["artifact"],
                   "exists": (node_dir(workspace_root, root, i["from"]) / i["artifact"]).is_file(),
                   "size": _size(node_dir(workspace_root, root, i["from"]) / i["artifact"])}
                  for i in node.inputs]
        (out_dir / target).write_text(json.dumps({"inputs": inputs}, ensure_ascii=False), encoding="utf-8")
        return

    # group by destination so multiple sources can fold into one aggregate
    by_dst: dict[str, list[Path]] = {}
    for dst, src in resolved:
        by_dst.setdefault(dst, []).append(src)

    for dst, srcs in by_dst.items():
        target = out_dir / dst
        target.parent.mkdir(parents=True, exist_ok=True)
        if node.reduce_op == "pick":
            target.write_bytes(srcs[-1].read_bytes() if srcs[-1].is_file() else b"")
        elif node.reduce_op == "concat":
            target.write_text("".join(_read_text(s) for s in srcs), encoding="utf-8")
        elif node.reduce_op == "merge_json":
            merged: dict[str, Any] = {}
            for s in srcs:
                obj = _load_json(s)
                if isinstance(obj, dict):
                    _deep_merge(merged, obj)
            target.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")


def _size(p: Path) -> int:
    return p.stat().st_size if p.is_file() else 0


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""


def _load_json(p: Path) -> Any:
    try:
        return json.loads(_read_text(p))
    except (json.JSONDecodeError, ValueError):
        return None
