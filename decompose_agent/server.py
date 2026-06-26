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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from .ui_data import DEFAULT_ROOT, DEFAULT_TREE, build_project_data_js

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

        target = (_UI_DIR / path.lstrip("/")).resolve()
        if _UI_DIR in target.parents and target.is_file():  # jailed to ui/
            self._send(target.read_bytes(), _ctype(target))
            return
        self._send(b"not found", "text/plain; charset=utf-8", status=404)

    do_HEAD = do_GET

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
