"""Node + DoneWhen records. A structurally-wrong node cannot exist — every invariant
is enforced at construction (lift control/events.py:134-151).

The integrity boundary this protects: the Worker (35B) is the one untrusted component,
and it never gets to write a verdict. So a done_when criterion is *only* a question the
gate will answer — `{check, params, artifact}` — never an answer. Any verdict-shaped key
(`verdict`/`passed`/`status`/`score`/`done`) on a criterion is a forgery attempt and is
rejected here, before the object can exist.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

# Verdict-shaped keys a criterion must never carry — the gate writes verdicts, not the author.
FORBIDDEN_VERDICT_KEYS = frozenset({"verdict", "passed", "status", "score", "done"})

# The full criterion shape. Anything else is "not the triple" → reject.
_CRITERION_KEYS = frozenset({"check", "params", "artifact"})

# Checks that operate on tree structure, not a file → they legitimately have no artifact.
ARTIFACTLESS_CHECKS = frozenset({"all_children_done"})

VALID_STATUSES = frozenset({"pending", "active", "decomposed", "done", "blocked"})
VALID_KINDS = frozenset({"work"})  # `reduce` is fenced out this round


def assert_safe_relpath(path: str) -> str:
    """Path-jail an artifact at authoring time: a relative, in-workspace path only.

    Rejects absolute paths, `~`, and any `..` segment. The runner later resolves this
    under the active node's artifact dir; jailing here means an unsafe path can never
    reach the filesystem layer.
    """
    if not isinstance(path, str) or not path.strip():
        raise ValueError("artifact path must be a non-empty string")
    p = path.strip()
    if os.path.isabs(p) or p.startswith("~"):
        raise ValueError(f"artifact path must be relative and in-workspace: {path!r}")
    if ".." in PurePosixPath(p).parts:
        raise ValueError(f"artifact path must not escape the workspace ('..'): {path!r}")
    return p


@dataclass(frozen=True)
class DoneWhen:
    """One acceptance criterion: a question the gate answers. Never an answer."""

    check: str
    params: dict[str, Any] = field(default_factory=dict)
    artifact: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.check, str) or not self.check.strip():
            raise ValueError("done_when criterion is missing a non-empty 'check'")
        if not isinstance(self.params, dict):
            raise ValueError(f"done_when criterion 'params' must be a mapping, got {type(self.params).__name__}")
        if self.artifact is not None:
            object.__setattr__(self, "artifact", assert_safe_relpath(self.artifact))
        elif self.check not in ARTIFACTLESS_CHECKS:
            raise ValueError(f"done_when criterion {self.check!r} requires an 'artifact' path")

    @classmethod
    def from_dict(cls, raw: Any) -> DoneWhen:
        if not isinstance(raw, dict):
            raise ValueError(f"done_when criterion must be a mapping, got {type(raw).__name__}")
        extra = set(raw) - _CRITERION_KEYS
        forged = extra & FORBIDDEN_VERDICT_KEYS
        if forged:
            raise ValueError(
                f"done_when criterion must not carry a verdict field {sorted(forged)} — "
                "the gate writes the verdict, not the author"
            )
        if extra:
            raise ValueError(
                f"done_when criterion has unexpected field(s) {sorted(extra)}; "
                "criteria are exactly {check, params, artifact}"
            )
        return cls(
            check=raw.get("check"),
            params=dict(raw.get("params") or {}),
            artifact=raw.get("artifact"),
        )

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"check": self.check}
        if self.params:
            out["params"] = dict(self.params)
        if self.artifact is not None:
            out["artifact"] = self.artifact
        return out


@dataclass(frozen=True)
class Node:
    """One unit of work on disk. Frozen — status transitions go through dataclasses.replace
    (the Navigator owns the tree; nothing else mutates a node)."""

    id: str
    parent: str | None = None
    kind: str = "work"
    status: str = "pending"
    depends_on: tuple[str, ...] = ()
    done_when: tuple[DoneWhen, ...] = ()
    max_attempts: int = 3
    attempts: int = 0
    depth: int = 0
    order: int = 0
    activated_at: float | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Node.id is required and must be a non-empty string")
        if self.kind not in VALID_KINDS:
            raise ValueError(f"Node.kind must be one of {sorted(VALID_KINDS)}, got {self.kind!r}")
        if self.status not in VALID_STATUSES:
            raise ValueError(f"Node.status must be one of {sorted(VALID_STATUSES)}, got {self.status!r}")
        if not isinstance(self.depends_on, tuple):
            raise ValueError("Node.depends_on must be a tuple")
        if not isinstance(self.done_when, tuple) or not all(isinstance(c, DoneWhen) for c in self.done_when):
            raise ValueError("Node.done_when must be a tuple of DoneWhen")
        if self.max_attempts < 1:
            raise ValueError("Node.max_attempts (K) must be >= 1")
        if self.attempts < 0:
            raise ValueError("Node.attempts must be >= 0")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Node:
        if not isinstance(d, dict) or "id" not in d:
            raise ValueError("node must be a mapping with an 'id'")
        return cls(
            id=d["id"],
            parent=d.get("parent"),
            kind=d.get("kind", "work"),
            status=d.get("status", "pending"),
            depends_on=tuple(d.get("depends_on") or ()),
            done_when=tuple(DoneWhen.from_dict(c) for c in (d.get("done_when") or ())),
            max_attempts=int(d.get("max_attempts", 3)),
            attempts=int(d.get("attempts", 0)),
            notes=d.get("notes", ""),
        )

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "parent": self.parent,
            "kind": self.kind,
            "status": self.status,
            "depends_on": list(self.depends_on),
            "max_attempts": self.max_attempts,
            "done_when": [c.as_dict() for c in self.done_when],
        }
        if self.notes:
            out["notes"] = self.notes
        return out
