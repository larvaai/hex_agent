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


def read_events(
    run_id: str | None = None,
    *,
    kind: str | None = None,
    topic: str | None = None,
    status: str | None = None,
    tool: str | None = None,
    text: str | None = None,
) -> list[dict[str, Any]]:
    """Read a run's events, optionally filtered. All filters AND together.

    ``kind``/``topic``/``status``/``tool`` match exactly; ``text`` is a
    case-insensitive substring over the whole serialized event.
    """
    run = _resolve(run_id)
    if run is None:
        return []
    path = run / "events.jsonl"
    if not path.exists():
        return []
    text_needle = text.lower() if text else None
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
        if status and event.get("status") != status:
            continue
        if tool and event.get("tool") != tool:
            continue
        if text_needle and text_needle not in json.dumps(event, ensure_ascii=False).lower():
            continue
        events.append(event)
    return events


def summarize_event(event: dict[str, Any]) -> str:
    """One compact human-readable line for a single event."""
    seq = event.get("sequence", "?")
    kind = event.get("kind", "?")
    label = event.get("topic") or event.get("status") or ""
    tool = event.get("tool")
    parts = [f"#{seq}", str(kind)]
    if label:
        parts.append(str(label))
    if tool:
        parts.append(str(tool))
    if "ok" in event:
        parts.append("ok" if event.get("ok") else "ERR")
    if event.get("error"):
        parts.append(f"error={str(event['error'])[:80]}")
    return "  ".join(parts)


def summarize_metrics(summary: dict[str, Any] | None) -> str:
    """Render a run summary's metrics as aligned ``metric  value`` columns."""
    if not summary:
        return "No summary found."
    metrics = summary.get("metrics") or {}
    header = f"run_id={summary.get('run_id', '?')}  status={summary.get('status', '?')}"
    if not metrics:
        return header
    width = max(len(k) for k in metrics)
    rows = [f"  {k.ljust(width)}  {v}" for k, v in metrics.items()]
    return "\n".join([header, *rows])


def _opt(args: list[str], flag: str) -> str | None:
    if flag in args:
        idx = args.index(flag)
        if idx + 1 < len(args):
            return args[idx + 1]
    return None


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else "list"
    if cmd in {"list", "ls"}:
        for name in list_runs():
            print(name)
        return 0
    if cmd == "summary":
        run_id = args[1] if len(args) > 1 and not args[1].startswith("-") else "latest"
        summary = read_summary(run_id)
        if "--metrics" in args:
            print(summarize_metrics(summary))
        else:
            print(json.dumps(summary, ensure_ascii=False, indent=2) if summary else "No summary found.")
        return 0
    if cmd == "events":
        run_id = args[1] if len(args) > 1 and not args[1].startswith("-") else "latest"
        for flag in ("--kind", "--topic", "--status", "--tool", "--text"):
            if flag in args and args.index(flag) + 1 >= len(args):
                print(f"usage: inspect events [run|latest] {flag} VALUE")
                return 2
        events = read_events(
            run_id,
            kind=_opt(args, "--kind"),
            topic=_opt(args, "--topic"),
            status=_opt(args, "--status"),
            tool=_opt(args, "--tool"),
            text=_opt(args, "--text"),
        )
        summarize = "--summarize" in args or "--short" in args
        for event in events:
            print(summarize_event(event) if summarize else json.dumps(event, ensure_ascii=False))
        return 0
    print(
        "usage: inspect [list | summary [run|latest] [--metrics] | "
        "events [run|latest] [--kind K] [--topic T] [--status S] [--tool T] [--text S] [--summarize]]"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
