"""The Worker boundary — the ONE untrusted component (the 35B), a pure local proposer.

A worker sees exactly the 4-cell context and never the graph: IDENTITY (fixed preamble) /
breadcrumb (root→node path only) / NODE (this node's title + done_when + notes) / journal
tail (last 1-3 lines of THIS node). It returns a proposed action; it never writes a verdict,
resolves a path, or mutates the tree.

Workers:
  * ScriptedWorker — deterministic test/demo double. With `satisfy=tree` it synthesizes a
    passing action from a node's done_when (drives the demo with no LLM).
  * LocalLLMWorker — OpenAI-compatible call in TEXT mode (no response_format; LM Studio 400s
    on json_object — DEC-D3/F6). Output goes through the json_repair ladder + normalize_action.
    Kept self-contained (no import of the old llm.adapter) so the package stays isolated.
"""
from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .json_repair import normalize_action, parse_children, parse_object
from .node import DoneWhen, Node

IDENTITY = (
    "You are a local worker solving ONE task node. Read the NODE cell (its done_when criteria "
    "and the artifact each names) and reply with EXACTLY ONE JSON action that writes the "
    "artifact(s) so every criterion passes. Use this shape:\n"
    '  {"action":"tool","tool":"write_artifacts","args":{"files":{"<relative_path>":"<content>"}}}\n'
    "Paths are relative to your node's own dir. No prose, no fences — one JSON object only."
)


# ── 4-cell context ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FourCell:
    identity: str
    breadcrumb: str
    node: str
    journal_tail: str
    node_id: str  # routing metadata, not a cell

    def cells(self) -> tuple[str, str, str, str]:
        return (self.identity, self.breadcrumb, self.node, self.journal_tail)

    def render(self) -> str:
        return (
            f"[IDENTITY]\n{self.identity}\n\n"
            f"[BREADCRUMB]\n{self.breadcrumb}\n\n"
            f"[NODE]\n{self.node}\n\n"
            f"[JOURNAL]\n{self.journal_tail}"
        )


def _breadcrumb(node: Node, tree) -> str:
    chain = [node.id]
    cur = node
    while cur.parent is not None:
        chain.append(cur.parent)
        cur = tree.nodes[cur.parent]
    return " > ".join(reversed(chain))


def _node_cell(node: Node) -> str:
    lines = [f"id: {node.id}"]
    if node.notes:
        lines.append(f"notes: {node.notes}")
    lines.append("done_when:")
    for c in node.done_when:
        suffix = f" artifact={c.artifact}" if c.artifact else ""
        params = f" params={c.params}" if c.params else ""
        lines.append(f"  - check={c.check}{params}{suffix}")
    return "\n".join(lines)


def assemble_4cell(node: Node, tree, journal=None) -> FourCell:
    tail = ""
    if journal is not None:
        recs = journal.tail(node.id, 3)
        tail = "\n".join(str(r) for r in recs)
    return FourCell(
        identity=IDENTITY,
        breadcrumb=_breadcrumb(node, tree),
        node=_node_cell(node),
        journal_tail=tail or "(no prior attempts)",
        node_id=node.id,
    )


# ── action helpers ────────────────────────────────────────────────────────────

def write_action(files: dict[str, str]) -> dict[str, Any]:
    """The canonical write action — a tool-call envelope (normalize_action no-ops on it)."""
    return {"action": "tool", "tool": "write_artifacts", "args": {"files": dict(files)}}


def _ptr_set(obj: dict, ptr: str, value: Any) -> None:
    tokens = ptr.lstrip("/").split("/")
    cur = obj
    for t in tokens[:-1]:
        cur = cur.setdefault(t, {})
    cur[tokens[-1]] = value


def satisfying_files(done_when: tuple[DoneWhen, ...]) -> dict[str, str]:
    """Deterministically synthesize artifact contents that pass `done_when` (demo/test only).

    Covers the checks the slice uses: file_exists, row_count_gte, file_nonempty_lines,
    grep_absent, grep_matches, json_field_* . Criteria on the same artifact are merged.
    """
    import json as _json

    by_art: dict[str, list[DoneWhen]] = defaultdict(list)
    for c in done_when:
        if c.artifact:
            by_art[c.artifact].append(c)

    files: dict[str, str] = {}
    for art, crits in by_art.items():
        if art.endswith(".json"):
            obj: dict[str, Any] = {}
            for c in crits:
                p = c.params
                if c.check == "json_field_in_range":
                    _ptr_set(obj, p["ptr"], (float(p["min"]) + float(p["max"])) / 2.0)
                elif c.check == "json_field_equals":
                    _ptr_set(obj, p["ptr"], p.get("value"))
                elif c.check == "json_field_exists":
                    _ptr_set(obj, p["ptr"], True)
                elif c.check == "json_len_gte":
                    _ptr_set(obj, p["ptr"], list(range(int(p["n"]))))
            files[art] = _json.dumps(obj or {"ok": True}, ensure_ascii=False)
        else:
            rows = 1
            for c in crits:
                if c.check == "row_count_gte":
                    rows = max(rows, int(c.params["n"]))
                elif c.check == "file_nonempty_lines":
                    rows = max(rows, int(c.params["min"]))
                elif c.check == "grep_matches":
                    rows = max(rows, int(c.params.get("min", 1)))
            files[art] = "\n".join(f'{{"i": {i}}}' for i in range(rows)) + "\n"
    return files


# ── workers ───────────────────────────────────────────────────────────────────

@runtime_checkable
class Worker(Protocol):
    def propose(self, ctx: FourCell) -> dict[str, Any]: ...
    def decompose(self, node: Node, failure_evidence: Any = None, reason: str | None = None) -> Any: ...


class ScriptedWorker:
    """Deterministic double. `scripts[node_id]` is a list of actions (dict) or raw strings
    (parsed through the repair ladder; a torn string raises JsonGateError, exercising the
    parse-fumble path). With `satisfy=tree`, an un-scripted node gets a synthesized pass action."""

    def __init__(self, scripts: dict[str, list[Any]] | None = None, *, satisfy=None,
                 decompose_scripts: dict[str, list[Any]] | None = None) -> None:
        self._scripts = scripts or {}
        self._decompose_scripts = decompose_scripts or {}
        self._satisfy = satisfy
        self._calls: dict[str, int] = defaultdict(int)
        self._dcalls: dict[str, int] = defaultdict(int)

    def propose(self, ctx: FourCell) -> dict[str, Any]:
        nid = ctx.node_id
        i = self._calls[nid]
        self._calls[nid] += 1
        script = self._scripts.get(nid)
        if script:
            item = script[i] if i < len(script) else script[-1]
            if isinstance(item, str):
                return normalize_action(parse_object(item))  # may raise JsonGateError (fumble)
            return item
        if self._satisfy is not None:
            return write_action(satisfying_files(self._satisfy.nodes[nid].done_when))
        return write_action({})  # no script, no satisfier → no-op (gate will FAIL)

    def decompose(self, node: Node, failure_evidence: Any = None, reason: str | None = None) -> list[dict]:
        nid = node.id
        i = self._dcalls[nid]
        self._dcalls[nid] += 1
        script = self._decompose_scripts.get(nid)
        if script:
            item = script[i] if i < len(script) else script[-1]
            return parse_children(item) if isinstance(item, str) else item
        if self._satisfy is not None:
            # deterministic 2-way split: each child gets one trivial criterion (dwc=1 < parent's dwc)
            return [{"id": f"{nid}.c{j}", "depends_on": [],
                     "done_when": [{"check": "file_exists", "artifact": f"c{j}.txt"}]} for j in range(2)]
        raise NotImplementedError(f"decompose() not scripted for {nid!r}")


class LocalLLMWorker:
    """OpenAI-compatible worker, TEXT mode (no response_format — F6/DEC-D3). Self-contained;
    `client` is injectable for tests so nothing hits the network."""

    def __init__(self, *, client: Any = None, model: str | None = None,
                 base_url: str | None = None, temperature: float = 0.0) -> None:
        self._client = client
        self._model = model or os.getenv("LLM_MODEL", "local-model")
        self._base_url = base_url or os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
        self._temperature = temperature

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI  # lazy import — only when actually calling out
            self._client = OpenAI(base_url=self._base_url, api_key=os.getenv("LLM_API_KEY", "lm-studio"))
        return self._client

    def propose(self, ctx: FourCell) -> dict[str, Any]:
        messages = [{"role": "system", "content": ctx.identity},
                    {"role": "user", "content": ctx.render()}]
        resp = self._get_client().chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=self._temperature,
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "2048")),
            # NOTE: deliberately NO response_format — text mode (DEC-D3/F6). The repair
            # ladder parses plain text; LM Studio 400s on response_format=json_object.
        )
        raw = resp.choices[0].message.content or ""
        return normalize_action(parse_object(raw))

    def decompose(self, node: Node, failure_evidence: Any = None, reason: str | None = None) -> list[dict]:
        sys_msg = (
            "You split ONE task that's too hard into >=2 SMALLER child tasks. Reply with EXACTLY ONE "
            "JSON array of children. Each child has fewer done_when criteria than the parent (strictly "
            "smaller). Shape:\n"
            '  [{"id":"<parent_id>.<slug>","depends_on":[],'
            '"done_when":[{"check":"<check>","params":{...},"artifact":"<relative/path>"}]}]\n'
            "No prose, no fences — one JSON array only."
        )
        parts = [_node_cell(node)]
        if reason:
            parts.append(f"[PRIOR REJECTION — fix this]\n{reason}")
        if failure_evidence:
            parts.append(f"[FAILURE EVIDENCE]\n{failure_evidence}")
        resp = self._get_client().chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": "\n\n".join(parts)}],
            temperature=0.0,  # temp-0: content-addressed cache wants a stable sample
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "2048")),
        )
        return parse_children(resp.choices[0].message.content or "")
