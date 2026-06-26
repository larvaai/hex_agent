"""Serve the bundled Agent-IDE UI and feed it LIVE decompose_agent data.

Zero-dependency stdlib HTTP server. The UI is a `.dc` React export that must be served over HTTP
(its dynamic `import()` + `fetch(location.href)` break on file://). Routing:
  * GET /                       → 302 to the .dc.html (so the doc URL ends in .dc.html, as the
                                  dc-runtime expects; relative imports then resolve to /<name>)
  * GET /project-data.js        → generated on the fly from a real solve() run (the live bridge)
  * GET /<anything in ui/>      → served statically from ui/

Run:  python -m decompose_agent.server [--tree PATH] [--root ID] [--port 8765] [--host 127.0.0.1]
"""
from __future__ import annotations

import argparse
import json
import queue
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from .journal import Journal
from .solve import solve as run_solve
from .tree import load_tree
from .ui_data import DEFAULT_ROOT, DEFAULT_TREE, build_project_data_js
from .worker import ScriptedWorker

_UI_DIR = Path(__file__).resolve().parent / "ui"
_HTML_NAME = "Agent IDE.dc.html"

_CTYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".map": "application/json; charset=utf-8",
}


def _ctype(path: Path) -> str:
    return _CTYPES.get(path.suffix.lower(), "application/octet-stream")


def _slim(record: dict) -> dict:
    """Drop the heavy payload (artifact contents) from a journal record before streaming —
    the live UI only needs node / event / verdict / reason."""
    out = {k: v for k, v in record.items() if k not in ("action", "reasons", "children")}
    action = record.get("action")
    if isinstance(action, dict) and action.get("tool"):
        out["tool"] = action["tool"]
    return out


def _solve_into(tree_path: Path, root: str, sink) -> dict:
    """Run a real solve() in a fresh workspace, streaming each (slimmed) journal record to `sink`.
    Returns the final state (node statuses + blocked outcome)."""
    tree = load_tree(tree_path)
    workspace = tempfile.mkdtemp(prefix="decompose_run_")
    journal = Journal(workspace, root, sink=lambda rec: sink(_slim(rec)))
    result = run_solve(tree, ScriptedWorker(satisfy=tree), root=root,
                       workspace_root=workspace, journal=journal)
    return {
        "nodes": {nid: n.status for nid, n in result.tree.nodes.items()},
        "blocked": (result.blocked._asdict() if result.blocked else None),
    }


class _Handler(BaseHTTPRequestHandler):
    tree_path: Path = DEFAULT_TREE
    root: str = DEFAULT_ROOT

    def _send(self, body: bytes, ctype: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")  # always reflect live state
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = unquote(urlparse(self.path).path)

        if path in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/" + quote(_HTML_NAME))
            self.end_headers()
            return

        if path == "/project-data.js":
            try:
                js = build_project_data_js(self.tree_path, self.root)
            except Exception as exc:  # never 500 the page — surface the error in-module
                js = f"export const PROJECT=null,AGENTS=[],VIRTUAL={{}};console.error({exc!r});"
            self._send(js.encode("utf-8"), _CTYPES[".js"])
            return

        if path == "/api/run":  # one-shot: run a real solve, return the final state
            try:
                final = _solve_into(self.tree_path, self.root, lambda _rec: None)
            except Exception as exc:
                final = {"error": str(exc)}
            self._send(json.dumps(final).encode("utf-8"), _CTYPES[".json"])
            return

        if path == "/api/stream":  # live: SSE of journal events while a real solve() runs
            qs = parse_qs(urlparse(self.path).query)
            pace = float(qs.get("pace", ["0.22"])[0])
            self._stream_solve(pace)
            return

        target = (_UI_DIR / path.lstrip("/")).resolve()
        if _UI_DIR in target.parents and target.is_file():  # jailed to ui/
            self._send(target.read_bytes(), _ctype(target))
            return
        self._send(b"not found", "text/plain; charset=utf-8", status=404)

    do_HEAD = do_GET

    def _stream_solve(self, pace: float) -> None:
        """Run solve() in a worker thread; emit each journal record as an SSE event (paced so a
        fast scripted run is watchable), then a final `done` event with the end state."""
        events: queue.Queue = queue.Queue()
        DONE = object()
        final: dict = {}

        def work() -> None:
            try:
                final.update(_solve_into(self.tree_path, self.root, events.put))
            except Exception as exc:  # noqa: BLE001
                final["error"] = str(exc)
            finally:
                events.put(DONE)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        threading.Thread(target=work, daemon=True).start()
        try:
            while True:
                item = events.get()
                if item is DONE:
                    break
                self._sse("event", item)
                if pace > 0:
                    time.sleep(pace)
            self._sse("done", final)
        except (BrokenPipeError, ConnectionResetError):
            pass  # client navigated away mid-stream

    def _sse(self, event: str, data: object) -> None:
        self.wfile.write(f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8"))
        self.wfile.flush()

    def log_message(self, *args) -> None:  # quiet by default
        pass


def serve(tree_path: Path, root: str, host: str, port: int) -> None:
    _Handler.tree_path = Path(tree_path)
    _Handler.root = root
    httpd = ThreadingHTTPServer((host, port), _Handler)
    url = f"http://{host}:{port}/"
    print(f"decompose_agent UI → {url}  (tree={tree_path}, root={root})")
    print("  /project-data.js is generated live from a real solve() run. Ctrl-C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="decompose_agent.server")
    ap.add_argument("--tree", default=str(DEFAULT_TREE), help="tree.yaml to run for the UI data")
    ap.add_argument("--root", default=DEFAULT_ROOT, help="root node id")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args(argv)
    serve(Path(args.tree), args.root, args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
