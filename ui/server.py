"""Local HTTP/SSE server for the core_agent observability console."""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from core.bootstrap import create_kernel
from observability import EventLogger, attach_to_bus
from observability.event_log import runs_dir
from orchestrator import run as run_agent
from orchestrator.loop import DEFAULT_SYSTEM
from safety.sandbox import workspace_dir

PROJECT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_REQUEST_BYTES = 128 * 1024
MAX_PROMPT_CHARS = 20_000
MAX_SYSTEM_PROMPT_CHARS = 40_000
MAX_FILE_BYTES = 512 * 1024
MAX_TREE_ENTRIES = 2_500
STREAM_INTERVAL_SECONDS = 0.75
STREAM_KEEPALIVE_SECONDS = 12.0

IGNORED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
}
SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "credentials.json",
    "id_ed25519",
    "id_rsa",
}
SENSITIVE_SUFFIXES = {".key", ".p12", ".pem", ".pfx"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError, UnicodeError):
        return None
    return data if isinstance(data, dict) else None


def _read_events(path: Path, *, limit: int = 500) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError, UnicodeError):
        return []
    events: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return events


def _root_for_scope(scope: str) -> Path:
    if scope == "workspace":
        root = workspace_dir()
        root.mkdir(parents=True, exist_ok=True)
        return root
    if scope == "project":
        return PROJECT_DIR
    raise ValueError("scope must be 'workspace' or 'project'")


def _is_hidden_project_path(relative: Path) -> bool:
    parts = relative.parts
    if any(part in IGNORED_DIRS for part in parts):
        return True
    return len(parts) >= 2 and parts[0] == "var" and parts[1] == "agent_runs"


def _tree_node(path: Path, root: Path, scope: str, counter: list[int]) -> dict[str, Any] | None:
    if counter[0] >= MAX_TREE_ENTRIES:
        return None
    try:
        relative = path.relative_to(root)
        stat = path.lstat()
    except (OSError, ValueError):
        return None
    if scope == "project" and relative != Path(".") and _is_hidden_project_path(relative):
        return None
    counter[0] += 1
    relative_text = "" if relative == Path(".") else relative.as_posix()
    node: dict[str, Any] = {
        "name": root.name if not relative_text else path.name,
        "path": relative_text,
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
    }
    if path.is_symlink():
        node["type"] = "symlink"
        return node
    if path.is_dir():
        node["type"] = "directory"
        children: list[dict[str, Any]] = []
        try:
            entries = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        except OSError:
            entries = []
        for child in entries:
            child_node = _tree_node(child, root, scope, counter)
            if child_node is not None:
                children.append(child_node)
        node["children"] = children
    else:
        node["type"] = "file"
    return node


def tree_snapshot(scope: str) -> dict[str, Any]:
    root = _root_for_scope(scope)
    counter = [0]
    tree = _tree_node(root, root, scope, counter)
    return {
        "scope": scope,
        "root": str(root),
        "tree": tree,
        "entries": counter[0],
        "truncated": counter[0] >= MAX_TREE_ENTRIES,
    }


def _safe_file(scope: str, relative_path: str) -> tuple[Path, Path]:
    root = _root_for_scope(scope).resolve()
    candidate = (root / unquote(relative_path)).resolve()
    if candidate != root and not candidate.is_relative_to(root):
        raise ValueError("path is outside the selected root")
    relative = candidate.relative_to(root)
    if scope == "project" and _is_hidden_project_path(relative):
        raise PermissionError("this path is hidden from the project explorer")
    return candidate, relative


def read_file_snapshot(scope: str, relative_path: str) -> dict[str, Any]:
    path, relative = _safe_file(scope, relative_path)
    if not path.is_file():
        raise FileNotFoundError(relative_path)
    if path.name.lower() in SENSITIVE_NAMES or path.suffix.lower() in SENSITIVE_SUFFIXES:
        raise PermissionError("sensitive file preview is disabled")
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError(f"file exceeds preview limit ({MAX_FILE_BYTES} bytes)")
    raw = path.read_bytes()
    if b"\x00" in raw[:4096]:
        raise ValueError("binary file preview is disabled")
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("file is not UTF-8 text") from exc
    return {
        "scope": scope,
        "path": relative.as_posix(),
        "name": path.name,
        "size": size,
        "content": content,
        "language": path.suffix.lower().lstrip(".") or "text",
    }


@dataclass
class RunJob:
    run_id: str
    prompt: str
    system_prompt: str
    status: str = "queued"
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None


class RunController:
    def __init__(self, *, max_workers: int = 2) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, RunJob] = {}
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="agent-ui")

    def start(self, prompt: str, system_prompt: str = DEFAULT_SYSTEM) -> RunJob:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
        job = RunJob(run_id=run_id, prompt=prompt, system_prompt=system_prompt)
        with self._lock:
            self._jobs[run_id] = job
        self._executor.submit(self._execute, run_id)
        return job

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(run_id)
            return asdict(job) if job else None

    def _update(self, run_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs[run_id]
            for key, value in changes.items():
                setattr(job, key, value)

    def _execute(self, run_id: str) -> None:
        job = self.get(run_id)
        if job is None:
            return
        prompt = str(job["prompt"])
        system_prompt = str(job["system_prompt"])
        self._update(run_id, status="starting", started_at=_utc_now())
        logger = EventLogger(run_id=run_id)
        logger.emit("UIEvent", event="prompt.submitted", role="user", content=prompt)
        try:
            kernel = create_kernel()
            attach_to_bus(logger, kernel.events)
            self._update(run_id, status="running")
            outcome = run_agent(
                kernel,
                prompt,
                system_prompt=system_prompt,
                run_id=run_id,
                checkpoint=True,
            )
            status = str(outcome.get("status") or "completed")
            logger.finish(status, outcome=outcome)
            self._update(run_id, status=status, finished_at=_utc_now())
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            logger.emit("UIEvent", event="run.failed", error=error)
            logger.finish("failed", error=error)
            self._update(run_id, status="failed", finished_at=_utc_now(), error=error)

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)


def _run_summary(run_path: Path, controller: RunController) -> dict[str, Any]:
    checkpoint = _read_json(run_path / "checkpoint.json") or {}
    summary = _read_json(run_path / "summary.json") or {}
    job = controller.get(run_path.name) or {}
    status = job.get("status") or summary.get("status") or checkpoint.get("status") or "observed"
    status = _effective_status(checkpoint, str(status))
    prompt = checkpoint.get("task") or job.get("prompt") or ""
    try:
        modified = datetime.fromtimestamp(run_path.stat().st_mtime, timezone.utc).isoformat()
    except OSError:
        modified = None
    return {
        "run_id": run_path.name,
        "status": status,
        "prompt": prompt,
        "step": checkpoint.get("step", 0),
        "modified_at": modified,
        "metrics": summary.get("metrics") or {},
    }


def list_runs(controller: RunController) -> list[dict[str, Any]]:
    base = runs_dir()
    if not base.exists():
        return []
    paths = sorted((path for path in base.iterdir() if path.is_dir()), key=lambda path: path.name, reverse=True)
    return [_run_summary(path, controller) for path in paths[:100]]


def _final_action(checkpoint: dict[str, Any]) -> dict[str, Any] | None:
    for raw in reversed(checkpoint.get("messages") or []):
        if not isinstance(raw, dict) or raw.get("role") != "assistant":
            continue
        try:
            action = json.loads(raw.get("content") or "")
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(action, dict) and action.get("action") == "final":
            return action
    return None


def _effective_status(checkpoint: dict[str, Any], status: str) -> str:
    action = _final_action(checkpoint)
    if action and str(action.get("finish_reason") or "").lower() in {"error", "failed"}:
        return "failed"
    return status


def _normalize_messages(checkpoint: dict[str, Any], summary: dict[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(checkpoint.get("messages") or []):
        if not isinstance(raw, dict):
            continue
        role = str(raw.get("role") or "unknown")
        content = raw.get("content", "")
        agent_id = raw.get("agent_id") or raw.get("name")
        item = {
            "id": f"message-{index}",
            "role": role,
            "agent_id": agent_id or ("Agent" if role == "assistant" else role.title()),
            "content": content if isinstance(content, str) else json.dumps(content, ensure_ascii=False),
        }
        normalized.append(item)
    outcome = summary.get("outcome")
    if isinstance(outcome, dict) and outcome.get("result") is not None:
        final_text = outcome.get("result")
        if isinstance(final_text, (dict, list)):
            final_text = json.dumps(final_text, ensure_ascii=False, indent=2)
        final_action = _final_action(checkpoint) or {}
        has_final = str(final_action.get("message") or "") == str(final_text)
        if not has_final:
            normalized.append({
                "id": "summary-outcome",
                "role": "assistant",
                "agent_id": "Agent",
                "content": str(final_text),
                "final": True,
            })
    return normalized


def run_snapshot(run_id: str | None, scope: str, controller: RunController) -> dict[str, Any]:
    runs = list_runs(controller)
    selected = run_id or (runs[0]["run_id"] if runs else None)
    checkpoint: dict[str, Any] = {}
    summary: dict[str, Any] = {}
    events: list[dict[str, Any]] = []
    job: dict[str, Any] | None = None
    if selected:
        run_path = runs_dir() / selected
        if run_path.is_dir() and run_path.parent.resolve() == runs_dir().resolve():
            checkpoint = _read_json(run_path / "checkpoint.json") or {}
            summary = _read_json(run_path / "summary.json") or {}
            events = _read_events(run_path / "events.jsonl")
            job = controller.get(selected)
    status = (job or {}).get("status") or summary.get("status") or checkpoint.get("status") or "idle"
    status = _effective_status(checkpoint, str(status))
    return {
        "selected_run_id": selected,
        "runs": runs,
        "run": {
            "run_id": selected,
            "status": status,
            "checkpoint": checkpoint,
            "summary": summary,
            "events": events,
            "messages": _normalize_messages(checkpoint, summary),
            "job": job,
        },
        "files": tree_snapshot(scope),
    }


class AgentUIHandler(BaseHTTPRequestHandler):
    server_version = "CoreAgentUI/0.1"

    @property
    def controller(self) -> RunController:
        return self.server.controller  # type: ignore[attr-defined]

    def log_message(self, format_string: str, *args: Any) -> None:
        print(f"[ui] {self.address_string()} {format_string % args}")

    def _json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _error(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
        self._json({"ok": False, "error": message}, status)

    def _serve_static(self, relative: str) -> None:
        name = relative or "index.html"
        path = (STATIC_DIR / name).resolve()
        if path.parent != STATIC_DIR.resolve() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        raw = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type + ("; charset=utf-8" if content_type.startswith("text/") else ""))
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/api/bootstrap":
            scope = query.get("scope", ["workspace"])[0]
            self._json({
                "project": PROJECT_DIR.name,
                "default_system_prompt": DEFAULT_SYSTEM,
                **run_snapshot(None, scope, self.controller),
            })
            return
        if parsed.path == "/api/runs":
            self._json({"runs": list_runs(self.controller)})
            return
        if parsed.path == "/api/snapshot":
            scope = query.get("scope", ["workspace"])[0]
            run_id = query.get("run_id", [None])[0]
            try:
                self._json(run_snapshot(run_id, scope, self.controller))
            except ValueError as exc:
                self._error(str(exc))
            return
        if parsed.path == "/api/tree":
            scope = query.get("scope", ["workspace"])[0]
            try:
                self._json(tree_snapshot(scope))
            except ValueError as exc:
                self._error(str(exc))
            return
        if parsed.path == "/api/file":
            scope = query.get("scope", ["workspace"])[0]
            relative_path = query.get("path", [""])[0]
            try:
                self._json(read_file_snapshot(scope, relative_path))
            except FileNotFoundError:
                self._error("file not found", HTTPStatus.NOT_FOUND)
            except PermissionError as exc:
                self._error(str(exc), HTTPStatus.FORBIDDEN)
            except ValueError as exc:
                self._error(str(exc))
            return
        if parsed.path == "/api/stream":
            scope = query.get("scope", ["workspace"])[0]
            run_id = query.get("run_id", [None])[0]
            self._stream(run_id, scope)
            return
        if parsed.path in {"/", "/index.html"}:
            self._serve_static("index.html")
            return
        self._serve_static(parsed.path.lstrip("/"))

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/runs":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._error("invalid Content-Length")
            return
        if length <= 0 or length > MAX_REQUEST_BYTES:
            self._error("request body is empty or too large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._error("body must be valid UTF-8 JSON")
            return
        prompt = str(payload.get("prompt") or "").strip() if isinstance(payload, dict) else ""
        if not prompt:
            self._error("prompt is required")
            return
        if len(prompt) > MAX_PROMPT_CHARS:
            self._error(f"prompt exceeds {MAX_PROMPT_CHARS} characters")
            return
        system_prompt = payload.get("system_prompt", DEFAULT_SYSTEM)
        if not isinstance(system_prompt, str):
            self._error("system_prompt must be a string")
            return
        if len(system_prompt) > MAX_SYSTEM_PROMPT_CHARS:
            self._error(f"system_prompt exceeds {MAX_SYSTEM_PROMPT_CHARS} characters")
            return
        job = self.controller.start(prompt, system_prompt)
        self._json({"ok": True, "run": asdict(job)}, HTTPStatus.ACCEPTED)

    def _stream(self, run_id: str | None, scope: str) -> None:
        try:
            _root_for_scope(scope)
        except ValueError as exc:
            self._error(str(exc))
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        last_digest = ""
        last_write = 0.0
        try:
            self.wfile.write(b"retry: 1000\n\n")
            self.wfile.flush()
            while True:
                payload = run_snapshot(run_id, scope, self.controller)
                raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                digest = hashlib.sha256(raw).hexdigest()
                now = time.monotonic()
                if digest != last_digest:
                    self.wfile.write(b"event: snapshot\n")
                    self.wfile.write(b"data: " + raw + b"\n\n")
                    self.wfile.flush()
                    last_digest = digest
                    last_write = now
                elif now - last_write >= STREAM_KEEPALIVE_SECONDS:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    last_write = now
                time.sleep(STREAM_INTERVAL_SECONDS)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return


class AgentUIServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], controller: RunController) -> None:
        self.controller = controller
        super().__init__(server_address, AgentUIHandler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local core_agent observability console.")
    parser.add_argument("--host", default=os.getenv("AGENT_UI_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("AGENT_UI_PORT", "8765")))
    args = parser.parse_args(argv)
    controller = RunController()
    server = AgentUIServer((args.host, args.port), controller)
    print(f"Core Agent UI: http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        controller.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
