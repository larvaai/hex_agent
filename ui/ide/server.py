"""Live IDE control server — the real backend the control-plane UI drops onto. Epic E21 / IDE.

Same three control endpoints as ``tools/fake_control_server.py`` and the *identical* wire (it reuses
``control/``: ``parse_command``, the registries, ``Redactor``, ``build_snapshot``), so the existing
adapter/store/Graph/Timeline render against it with zero changes. Two differences make it an IDE:

1. **It runs the real agent.** ``SubmitPrompt`` dispatches an ``AgentRunner`` and the SSE stream is
   *held open*, pushing ``loop.*`` events live as the agent works (the fake closes after its fixture).
2. **It serves files.** A ``/api/files/*`` surface (tree/read/write/create/rename/delete/diff) lets
   the user browse, edit, and review the agent's changes alongside it — the opencode core loop.

It also serves the built UI from ``ui/control-plane/dist`` when present, so ``python -m ui.ide`` is a
single-command IDE; run ``vite dev`` against it instead for hot-reload development.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from control.command_registry import load_command_registry
from control.commands import CommandAck, parse_command
from control.errors import ControlContractError
from control.snapshot import build_snapshot

from . import files
from .files import FileOpError
from .runner import AgentRunner
from .session import IdeSession

DIST_DIR = Path(__file__).resolve().parent.parent / "control-plane" / "dist"
MAX_BODY_BYTES = 4 * 1024 * 1024  # editor saves can be large; capped to avoid an OOM POST
MAX_PROMPT_CHARS = 20_000
STREAM_KEEPALIVE_SECONDS = 12.0
DRAIN_TIMEOUT_SECONDS = 1.0
MAX_DEDUP_ENTRIES = 4_096  # bound the idempotency map so a long-lived server can't leak memory

# CORS is reflected only for same-machine origins (the served origin + the vite dev server). A
# blanket "*" would let any site a user visits read this localhost service's responses; reflecting
# only localhost/127.0.0.1 keeps the dev workflow while denying arbitrary cross-origin reads.
_LOCAL_ORIGIN = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$")


def _origin_allowed(origin: str | None) -> bool:
    return bool(origin) and bool(_LOCAL_ORIGIN.match(origin))


class IdeControlServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], *, token: str, session_id: str) -> None:
        self.token = token
        self.session = IdeSession(session_id)
        # Snapshot the workspace now so the diff endpoint reads empty until something actually
        # changes — otherwise an empty baseline makes every existing file look freshly "added".
        self.session.baseline = files.snapshot_baseline("workspace")
        self.runner = AgentRunner(self.session)
        self.command_registry = load_command_registry()
        self._dedup: dict[tuple[str, str], dict[str, Any]] = {}
        self._dedup_lock = threading.Lock()
        super().__init__(server_address, IdeHandler)

    # ── command handling (mirrors the fake's seam; SubmitPrompt drives a real run) ──
    def submit_command(self, *, token: str | None, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if token != self.token:
            return 401, {"error": "missing or invalid token"}
        try:
            cmd = parse_command(body)
            self.command_registry.assert_known(cmd.command_type)
        except ControlContractError as exc:
            cid = str(body.get("command_id") or uuid.uuid4().hex)
            self.session.emit("command.rejected", {"command_id": cid, "reason": str(exc)})
            return 400, CommandAck(command_id=cid, status="rejected", rejection_reason=str(exc)).as_dict()

        key = (cmd.session_id, cmd.idempotency_key)
        with self._dedup_lock:
            if key in self._dedup:
                return 200, self._dedup[key]  # idempotent replay → same ack, run dispatched once
            seq = self.session.emit(
                "command.received", {"command_id": cmd.command_id, "command_type": cmd.command_type}
            )
            ack = CommandAck(command_id=cmd.command_id, status="received", seq=seq)
            ack_dict = ack.as_dict()
            self._dedup[key] = ack_dict
            if len(self._dedup) > MAX_DEDUP_ENTRIES:
                # dict preserves insertion order — drop the oldest; idempotency only needs a window.
                del self._dedup[next(iter(self._dedup))]

        self._dispatch(cmd.command_type, cmd.payload)
        return 200, ack_dict

    def _dispatch(self, command_type: str, payload: dict[str, Any]) -> None:
        if command_type == "SubmitPrompt":
            prompt = str(payload.get("prompt") or "").strip()[:MAX_PROMPT_CHARS]
            if not prompt:
                return
            # runner.start atomically refuses to start over a live run (would clobber the diff
            # baseline and interleave two runs' loop.* events); surface that as a rejected command.
            if self.runner.start(prompt, str(payload.get("system_prompt") or "") or None) is None:
                self.session.emit("command.rejected", {"reason": "a run is already active"})
        # ApproveCheckpoint / RejectCheckpoint / others: accepted + recorded, but the single-agent
        # runner has no live approval gate yet, so they are no-ops beyond the command.received event.


class IdeHandler(BaseHTTPRequestHandler):
    server_version = "AgentIDE/0.1"

    @property
    def app(self) -> IdeControlServer:
        return self.server  # type: ignore[return-value]

    def log_message(self, *args: Any) -> None:
        return  # quiet; the dev server prints its own line

    # ── helpers ────────────────────────────────────────────────────────────────
    def _cors(self) -> None:
        """Reflect the Origin only for localhost dev origins (never a blanket ``*``)."""
        origin = self.headers.get("Origin")
        if _origin_allowed(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _require_token(self) -> bool:
        """Gate a request on the shared token (header only — the file surface mutates disk).

        The token is what stops the unauthenticated-localhost-service attack: a site the user visits
        cannot read it, so even with CORS it cannot forge an authorized file read/write. Returns True
        if authorized; otherwise writes 401 and returns False (caller must stop)."""
        token = self.headers.get("X-Auth-Token") or self.headers.get("Authorization")
        if token == self.app.token:
            return True
        self._json(401, {"ok": False, "error": "missing or invalid token"})
        return False

    def _json(self, status: int, body: Any) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return {}
        if length <= 0 or length > MAX_BODY_BYTES:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}

    def _file_result(self, fn) -> None:
        """Run a files.* op and map its FileOpError to the right HTTP status."""
        try:
            self._json(200, fn())
        except FileOpError as exc:
            self._json(exc.status, {"ok": False, "error": str(exc)})

    # ── GET ──────────────────────────────────────────────────────────────────────
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        path = parsed.path

        if path == "/api/snapshot":
            session = (qs.get("session") or [self.app.session.session_id])[0]
            if session and session != self.app.session.session_id:
                self._json(404, {"error": f"unknown session {session!r}"})
                return
            snap = build_snapshot(self.app.session.events(), session_id=self.app.session.session_id)
            self._json(200, snap.as_dict())
            return

        if path == "/api/stream":
            self._stream(qs)
            return

        if path == "/api/files/tree":
            if not self._require_token():
                return
            scope = (qs.get("scope") or ["workspace"])[0]
            self._file_result(lambda: files.tree_snapshot(scope))
            return

        if path == "/api/files/read":
            if not self._require_token():
                return
            scope = (qs.get("scope") or ["workspace"])[0]
            rel = unquote((qs.get("path") or [""])[0])
            self._file_result(lambda: files.read_file(scope, rel))
            return

        if path == "/api/files/diff":
            if not self._require_token():
                return
            diffs = files.compute_diffs(self.app.session.baseline, self.app.session.baseline_scope)
            self._json(200, {"session": self.app.session.session_id, "files": diffs})
            return

        self._serve_static(path)

    # ── POST ─────────────────────────────────────────────────────────────────────
    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/commands":
            token = self.headers.get("X-Auth-Token") or self.headers.get("Authorization")
            status, ack = self.app.submit_command(token=token, body=self._read_body())
            self._json(status, ack)
            return
        if path == "/api/files/create":
            if not self._require_token():
                return
            body = self._read_body()
            self._file_result(
                lambda: files.create_path(
                    str(body.get("scope") or "workspace"), str(body.get("path") or ""), str(body.get("kind") or "file")
                )
            )
            return
        if path == "/api/files/rename":
            if not self._require_token():
                return
            body = self._read_body()
            self._file_result(
                lambda: files.rename_path(
                    str(body.get("scope") or "workspace"), str(body.get("path") or ""), str(body.get("to") or "")
                )
            )
            return
        self._json(404, {"error": "not found"})

    # ── PUT (file save) ───────────────────────────────────────────────────────────
    def do_PUT(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/files/write":
            self._json(404, {"error": "not found"})
            return
        if not self._require_token():
            return
        body = self._read_body()
        content = body.get("content")
        if not isinstance(content, str):
            self._json(400, {"ok": False, "error": "content must be a string"})
            return
        self._file_result(
            lambda: files.write_file(str(body.get("scope") or "workspace"), str(body.get("path") or ""), content)
        )

    # ── DELETE ────────────────────────────────────────────────────────────────────
    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/files":
            self._json(404, {"error": "not found"})
            return
        if not self._require_token():
            return
        qs = parse_qs(parsed.query)
        scope = (qs.get("scope") or ["workspace"])[0]
        rel = unquote((qs.get("path") or [""])[0])
        self._file_result(lambda: files.delete_path(scope, rel))

    # ── OPTIONS (CORS preflight for the cross-origin write paths) ───────────────────
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Auth-Token, Authorization, Last-Event-ID")
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ── live SSE ────────────────────────────────────────────────────────────────
    def _stream(self, qs: dict[str, list[str]]) -> None:
        if (qs.get("token") or [None])[0] != self.app.token:
            self._json(401, {"error": "unauthorized"})
            return
        last = self.headers.get("Last-Event-ID") or (qs.get("lastEventId") or ["0"])[0]
        try:
            last_seq = int(last)
        except (TypeError, ValueError):
            last_seq = 0
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self._cors()
        self.end_headers()
        session = self.app.session
        try:
            self.wfile.write(b"retry: 1000\n\n")
            self.wfile.flush()
            last_keepalive = time.monotonic()
            while True:
                events, needs_resync = session.drain(last_seq, DRAIN_TIMEOUT_SECONDS)
                if needs_resync:
                    self.wfile.write(b"event: resync\ndata: {}\n\n")
                    self.wfile.flush()
                    last_keepalive = time.monotonic()
                wrote = False
                for ev in events:
                    if session.visibility(str(ev.get("event_type", ""))) not in ("public", "ui_safe"):
                        last_seq = max(last_seq, int(ev.get("seq", 0)))
                        continue
                    ui = ev.get("ui_payload")
                    ui = {} if ui is None else ui  # never fall back to the raw payload
                    frame = f"id: {int(ev.get('seq', 0))}\nevent: {ev.get('event_type', '')}\ndata: {json.dumps(ui)}\n\n"
                    self.wfile.write(frame.encode("utf-8"))
                    last_seq = max(last_seq, int(ev.get("seq", 0)))
                    wrote = True
                if wrote:
                    self.wfile.flush()
                    last_keepalive = time.monotonic()
                elif time.monotonic() - last_keepalive >= STREAM_KEEPALIVE_SECONDS:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    last_keepalive = time.monotonic()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, ValueError):
            return

    # ── static (serve the built UI when present) ────────────────────────────────────
    def _serve_static(self, path: str) -> None:
        if not DIST_DIR.is_dir():
            self._json(404, {"error": "UI not built; run `npm --prefix ui/control-plane run build` or use vite dev"})
            return
        rel = path.lstrip("/") or "index.html"
        candidate = (DIST_DIR / rel).resolve()
        if candidate != DIST_DIR.resolve() and not candidate.is_relative_to(DIST_DIR.resolve()):
            self._json(403, {"error": "forbidden"})
            return
        if not candidate.is_file():
            candidate = DIST_DIR / "index.html"  # SPA fallback
        if not candidate.is_file():
            self._json(404, {"error": "not found"})
            return
        raw = candidate.read_bytes()
        ctype = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") else ""))
        self.send_header("Content-Length", str(len(raw)))
        self._cors()
        self.end_headers()
        self.wfile.write(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live agent IDE control server (control-plane contract + files).")
    parser.add_argument("--host", default=os.getenv("IDE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("IDE_PORT", "8800")))
    parser.add_argument("--token", default=os.getenv("IDE_TOKEN", "dev-token"))
    parser.add_argument("--session", default=os.getenv("IDE_SESSION", "t1_demo"))
    args = parser.parse_args(argv)
    server = IdeControlServer((args.host, args.port), token=args.token, session_id=args.session)
    served = "serving built UI from dist" if DIST_DIR.is_dir() else "API only (run vite dev for the UI)"
    print(f"Agent IDE → http://{args.host}:{args.port}  (token={args.token!r}, session={args.session!r}; {served})", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
