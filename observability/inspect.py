"""CLI to inspect runs — list / summary / events from the event log. Epic E04."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from observability.event_log import runs_dir


def _run_dirs() -> list[Path]:
    base = runs_dir()
    if not base.exists():
        return []
    return sorted((p for p in base.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True)


def _resolve(run_id: str | None) -> Path | None:
    dirs = _run_dirs()
    if not dirs:
        return None
    if run_id in (None, "latest"):
        return dirs[0]
    for p in dirs:
        if p.name == run_id:
            return p
    return None


def list_runs() -> list[str]:
    return [p.name for p in _run_dirs()]


def read_summary(run_id: str | None = None) -> dict[str, Any] | None:
    run = _resolve(run_id)
    if run is None:
        return None
    summary = run / "summary.json"
    if not summary.exists():
        return None
    return json.loads(summary.read_text(encoding="utf-8"))


def read_events(run_id: str | None = None, *, kind: str | None = None, topic: str | None = None) -> list[dict[str, Any]]:
    run = _resolve(run_id)
    if run is None:
        return []
    path = run / "events.jsonl"
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue  # skip truncated/partial writes
        if not isinstance(event, dict):
            continue  # skip valid JSON that is not an event object
        if kind and event.get("kind") != kind:
            continue
        if topic and event.get("topic") != topic:
            continue
        events.append(event)
    return events


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else "list"
    if cmd in {"list", "ls"}:
        for name in list_runs():
            print(name)
        return 0
    if cmd == "summary":
        run_id = args[1] if len(args) > 1 else "latest"
        summary = read_summary(run_id)
        print(json.dumps(summary, ensure_ascii=False, indent=2) if summary else "No summary found.")
        return 0
    if cmd == "events":
        run_id = args[1] if len(args) > 1 else "latest"
        kind = None
        if "--kind" in args:
            idx = args.index("--kind")
            if idx + 1 >= len(args):
                print("usage: inspect events [run|latest] --kind KIND")
                return 2
            kind = args[idx + 1]
        for event in read_events(run_id, kind=kind):
            print(json.dumps(event, ensure_ascii=False))
        return 0
    print("usage: inspect [list | summary [run|latest] | events [run|latest] --kind KIND]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
