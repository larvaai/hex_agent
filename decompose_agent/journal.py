"""Append-only per-node JSONL journal (lift observability/event_log.py:60-99).

One file per node under `var/decompose/<root>/<node_id>.jsonl`. The reader is tolerant: a
torn or non-dict final line (a crash mid-write) is skipped, never raised — the journal is
evidence, and partial evidence must not take down the run that reads it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class Journal:
    def __init__(self, workspace_root: str | Path, root: str, sink=None) -> None:
        self._dir = Path(workspace_root) / "var" / "decompose" / root
        self._sink = sink  # optional callback(record) for live streaming (server SSE)

    def _path(self, node_id: str) -> Path:
        return self._dir / f"{node_id}.jsonl"

    def append(self, node_id: str, record: dict[str, Any]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        with self._path(node_id).open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        if self._sink is not None:
            try:
                self._sink({"node": node_id, **record})
            except Exception:  # a slow/broken consumer must never break the run
                pass

    def records(self, node_id: str) -> list[dict[str, Any]]:
        path = self._path(node_id)
        if not path.exists():
            return []
        out: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue  # torn / corrupt line — skip, do not raise
            if isinstance(rec, dict):
                out.append(rec)
        return out

    def tail(self, node_id: str, n: int = 3) -> list[dict[str, Any]]:
        return self.records(node_id)[-n:]
