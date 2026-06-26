"""Topology (Đồ thị 1) — declarative, serialisable design-time config.

Pure data: a node palette (agent / tool / router / memory / hook) plus edges
(routing / subscription wiring) and an optional budget. It round-trips to/from
JSON — the React Flow UI reads and writes exactly this. Turning it into a
runnable Orchestrator is `dragzero.wiring.build_runtime`. This module imports no
core runtime; it is config, not behaviour.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

NODE_TYPES = {"agent", "tool", "router", "memory", "hook"}
EDGE_TYPES = {"delegates_to", "uses_tool", "subscribes", "routes"}


class TopologyError(ValueError):
    """The topology is structurally invalid or references an unknown capability."""


@dataclass
class Node:
    id: str
    type: str
    attrs: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "Node":
        return cls(id=d["id"], type=d["type"], attrs={k: v for k, v in d.items() if k not in ("id", "type")})

    def to_dict(self) -> dict:
        return {"id": self.id, "type": self.type, **self.attrs}


@dataclass
class Edge:
    src: str
    dst: str
    type: str = "delegates_to"

    @classmethod
    def from_dict(cls, d: dict) -> "Edge":
        return cls(src=d["from"], dst=d["to"], type=d.get("type", "delegates_to"))

    def to_dict(self) -> dict:
        return {"from": self.src, "to": self.dst, "type": self.type}


@dataclass
class Topology:
    nodes: list = field(default_factory=list)
    edges: list = field(default_factory=list)
    budget: Optional[dict] = None
    version: int = 1

    @classmethod
    def from_dict(cls, d: dict) -> "Topology":
        return cls(
            version=d.get("version", 1),
            nodes=[Node.from_dict(n) for n in d.get("nodes", [])],
            edges=[Edge.from_dict(e) for e in d.get("edges", [])],
            budget=d.get("budget"),
        )

    def to_dict(self) -> dict:
        out = {
            "version": self.version,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }
        if self.budget:
            out["budget"] = self.budget
        return out

    def agents(self) -> list:
        return [n for n in self.nodes if n.type == "agent"]

    def validate(self, raise_on_error: bool = False) -> list:
        errors: list = []
        ids = [n.id for n in self.nodes]
        for dup in sorted({i for i in ids if ids.count(i) > 1}):
            errors.append(f"duplicate node id: {dup!r}")
        idset = set(ids)

        for n in self.nodes:
            if n.type not in NODE_TYPES:
                errors.append(f"unknown node type {n.type!r} (node {n.id!r})")
            required = {"agent": "role", "tool": "tool", "hook": "hook", "router": "rule"}.get(n.type)
            if required and not n.attrs.get(required):
                errors.append(f"{n.type} node {n.id!r} missing {required!r}")

        for e in self.edges:
            if e.src not in idset:
                errors.append(f"edge from unknown node {e.src!r}")
            if e.dst not in idset:
                errors.append(f"edge to unknown node {e.dst!r}")
            if e.type not in EDGE_TYPES:
                errors.append(f"unknown edge type {e.type!r}")

        if not self.agents():
            errors.append("topology has no agent nodes")
        if len([n for n in self.agents() if n.attrs.get("entry")]) > 1:
            errors.append("more than one entry agent")

        if raise_on_error and errors:
            raise TopologyError("; ".join(errors))
        return errors


def load_json(text: str) -> Topology:
    return Topology.from_dict(json.loads(text))


def dump_json(topology: Topology, indent: int = 2) -> str:
    return json.dumps(topology.to_dict(), indent=indent)


def load_file(path: str) -> Topology:
    with open(path) as f:
        return Topology.from_dict(json.load(f))
