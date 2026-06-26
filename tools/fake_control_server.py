"""Fake control server — speaks the REAL E21 contract by reusing control/. Epic E21 (DEC-6, S21.15/16/17).

This is where "drop-in = change the URL" becomes true rather than aspirational: the fake runs the
same Redactor, the same parse_command / CommandTypeRegistry, the same build_snapshot the real
backend will. So the UI is built against the actual seam, not a hand-shaped facade.

Logic lives in ``FakeControlPlane`` (pure, unit-testable); the stdlib ``ThreadingHTTPServer`` handler
(D5: no extra dependency) is a thin adapter over it. Three endpoints:

* ``GET  /api/snapshot``  → TaskLoopSnapshot (no raw secret) — S21.17
* ``GET  /api/stream``    → SSE of redacted ui_payload, Last-Event-ID catch-up + resync — S21.16
* ``POST /api/commands``  → static-token authz, registry + schema validation, CommandAck, idempotency — S21.15

Reality injection (latency / forced drop) is gated by ``inject_reality`` and lives only in the HTTP
loop, so the pure methods stay deterministic for tests; the demo CLI turns it on by default.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from control.command_registry import CommandTypeRegistry, load_command_registry  # noqa: E402
from control.commands import CommandAck, parse_command  # noqa: E402
from control.errors import ControlContractError  # noqa: E402
from control.event_registry import EventTypeRegistry, load_event_registry  # noqa: E402
from control.events import Actor, RedactionInfo, RuntimeEvent, TraceContext  # noqa: E402
from control.redaction import Redactor  # noqa: E402
from control.replay import EventReplayBuffer  # noqa: E402
from control.snapshot import build_snapshot  # noqa: E402

DEFAULT_FIXTURE = ROOT / "fixtures" / "control_plane" / "t1_scenario.events.jsonl"


class FakeControlPlane:
    """The contract logic behind the three endpoints — no HTTP, fully testable."""

    def __init__(
        self,
        *,
        token: str = "dev-token",
        session_id: str = "t1_demo",
        inject_reality: bool = False,
        reality_drop_after: int = 4,
        max_sse_connections: int = 1,
        event_registry: EventTypeRegistry | None = None,
        command_registry: CommandTypeRegistry | None = None,
    ) -> None:
        self.token = token
        self.session_id = session_id
        self.inject_reality = inject_reality
        self.reality_drop_after = reality_drop_after  # L3: force a mid-stream SSE drop after N frames
        self.max_sse_connections = max_sse_connections  # F12: cap concurrent streams (demo single-client)
        self.buffer = EventReplayBuffer()
        self.event_registry = event_registry or load_event_registry()
        self.command_registry = command_registry or load_command_registry()
        self.redactor = Redactor()
        self._dedup: dict[tuple[str, str], dict] = {}  # (session_id, idempotency_key) -> ack dict (F9)
        self._emitted: list[dict] = []
        self._cmd_seq = 0
        self._trace = TraceContext(trace_id="fake-root", span_id="fake-span")
        # ThreadingHTTPServer runs handlers concurrently over one FakeControlPlane, so every
        # touch of the shared mutable state (dedup map, seq counter, buffer) is serialized.
        self._lock = threading.Lock()
        self._active_streams = 0

    # ── read: snapshot ────────────────────────────────────────────────────────
    def snapshot(self, session_id: str | None) -> tuple[int, dict]:
        if session_id and session_id != self.session_id:
            return 404, {"error": f"unknown session {session_id!r}"}
        with self._lock:  # copy events atomically — a concurrent _emit must not mutate mid-read
            events = self.buffer.events
        snap = build_snapshot(events, session_id=self.session_id)
        return 200, snap.as_dict()

    # ── read: SSE stream (pure — returns the frames to write) ─────────────────
    def stream(self, *, token: str | None, last_seq: int) -> tuple[int, list[str]]:
        if token != self.token:  # read-path token via ?token= (EventSource can't set headers — F8/D7)
            return 401, []
        with self._lock:  # snapshot the catch-up window atomically before formatting
            if self.buffer.needs_resync(last_seq):
                return 200, ["event: resync\ndata: {}\n\n"]  # out-of-ring (F7) — client re-fetches snapshot
            pending = self.buffer.events_after(last_seq)
        frames: list[str] = []
        for ev in pending:
            et = str(ev.get("event_type", ""))
            # Allowlist (review I1): only public/ui_safe events ever reach the wire — an internal
            # or restricted event with a ui_payload must NOT leak to the UI (a denylist on 'secret'
            # alone would). The Redactor still masks secret-keyed fields inside what does pass.
            if self._visibility(et) not in ("public", "ui_safe"):
                continue
            ui = ev.get("ui_payload")
            if ui is None:
                ui = {}  # never fall back to the raw payload
            frames.append(f"id: {int(ev.get('seq', 0))}\nevent: {et}\ndata: {json.dumps(ui)}\n\n")
        return 200, frames

    def _visibility(self, event_type: str) -> str:
        try:
            return self.event_registry.visibility(event_type)
        except ControlContractError:
            return "ui_safe"

    # ── write: POST /api/commands ─────────────────────────────────────────────
    def submit_command(self, *, token: str | None, body: dict) -> tuple[int, dict]:
        if token != self.token:  # L2 static-token seam
            return 401, {"error": "missing or invalid token"}
        # L2 SCOPE (review I2): authz here is the static-token seam ONLY. The command registry's
        # `requires_permission` is intentionally NOT enforced — the fake has no real identity/login.
        # The real backend WILL enforce it and may return 403; the UI is built to surface a rejected
        # ack, so the drop-in stays honest. Per-permission enforcement is out of this slice (BACKLOG).
        try:
            cmd = parse_command(body)  # schema gate (idempotency_key/issued_by) — S21.15
            self.command_registry.assert_known(cmd.command_type)  # registry gate (F4)
            if cmd.session_id != self.session_id:  # write must validate session like the read path 404s
                raise ControlContractError(f"unknown session {cmd.session_id!r}")
        except ControlContractError as exc:
            # body may be a non-dict (array/str/number) from a hostile client — never assume .get()
            cid = str((body.get("command_id") if isinstance(body, dict) else None) or uuid.uuid4().hex)
            with self._lock:
                self._emit("command.rejected", {"command_id": cid, "reason": str(exc)})
            ack = CommandAck(command_id=cid, status="rejected", rejection_reason=str(exc))
            return 400, ack.as_dict()

        issuer = cmd.issued_by
        key = (cmd.session_id, cmd.idempotency_key)
        with self._lock:  # check-and-set + seq stamp must be atomic (concurrent POSTs, S21.10/F9)
            if key in self._dedup:
                return 200, self._dedup[key]  # idempotent: same ack, applied exactly once
            seq = self._next_seq()
            # carry the REAL issuer into the audit event (envelope actor + payload) — not a constant
            self._emit(
                "command.received",
                {"command_id": cmd.command_id, "command_type": cmd.command_type, "issued_by": issuer.as_dict()},
                seq=seq,
                actor=Actor(type=issuer.type, id=(issuer.user_id or issuer.agent_id or "ui")),
            )
            ack = CommandAck(command_id=cmd.command_id, status="received", seq=seq)
            self._dedup[key] = ack.as_dict()
            return 200, ack.as_dict()

    # ── emit helper (records + streams the command lifecycle event) ───────────
    def _next_seq(self) -> int:
        self._cmd_seq = max(self._cmd_seq, self.buffer.newest_seq()) + 1
        return self._cmd_seq

    def _emit(self, event_type: str, payload: dict, *, seq: int | None = None, actor: Actor | None = None) -> None:
        spec_seq = seq if seq is not None else self._next_seq()
        ev = RuntimeEvent(
            event_type=event_type,
            session_id=self.session_id,
            actor=actor or Actor(type="human", id="ui"),
            trace=self._trace,
            redaction=RedactionInfo(level=self._visibility(event_type)),
            payload=dict(payload),
            seq=spec_seq,
        )
        final = self.redactor.apply(ev, level=self._visibility(event_type)).as_dict()
        self.buffer.append(final)
        self._emitted.append(final)

    @property
    def emitted_types(self) -> list[str]:
        return [e["event_type"] for e in self._emitted]

    # ── F12: actually enforce the SSE connection cap (was a declared-but-unused field) ───
    def try_acquire_stream(self) -> bool:
        """Reserve a stream slot. False → over the cap; the handler returns 503 (demo single-client)."""
        with self._lock:
            if self._active_streams >= self.max_sse_connections:
                return False
            self._active_streams += 1
            return True

    def release_stream(self) -> None:
        with self._lock:
            self._active_streams = max(0, self._active_streams - 1)


# ── HTTP adapter ──────────────────────────────────────────────────────────────
class _Handler(BaseHTTPRequestHandler):
    def _cp(self) -> FakeControlPlane:
        return self.server.control_plane  # type: ignore[attr-defined]

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if parsed.path == "/api/snapshot":
            session = (qs.get("session") or [self._cp().session_id])[0]
            status, body = self._cp().snapshot(session)
            self._json(status, body)
        elif parsed.path == "/api/stream":
            self._stream(qs)
        else:
            self._json(404, {"error": "not found"})

    def _stream(self, qs: dict) -> None:
        cp = self._cp()
        token = (qs.get("token") or [None])[0]
        last = self.headers.get("Last-Event-ID") or (qs.get("lastEventId") or ["0"])[0]
        try:
            last_seq = int(last)
        except (TypeError, ValueError):
            last_seq = 0
        status, frames = cp.stream(token=token, last_seq=last_seq)
        if status != 200:
            self._json(status, {"error": "unauthorized"})
            return
        if not cp.try_acquire_stream():  # F12: enforce the concurrent-stream cap (demo single-client)
            self._json(503, {"error": "stream limit reached (demo single-client)"})
            return
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")  # dev: UI runs on a different port
            self.end_headers()
            sent = 0
            for frame in frames:
                if cp.inject_reality:
                    time.sleep(0.01)  # reality: per-event latency (L3)
                    if sent >= cp.reality_drop_after:
                        return  # reality: force a mid-stream drop → client reconnects via Last-Event-ID (S21.25)
                self.wfile.write(frame.encode("utf-8"))
                sent += 1
            self.wfile.flush()
            # Demo: the fixture is fully present, so all frames are sent and the connection closes.
            # A live backend would hold the socket and push new events here.
        finally:
            cp.release_stream()

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/commands":
            self._json(404, {"error": "not found"})
            return
        token = self.headers.get("X-Auth-Token") or self.headers.get("Authorization")
        try:  # a malformed/negative Content-Length must not crash the request thread (mirrors _stream)
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            length = 0
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            body = {}
        status, ack = self._cp().submit_command(token=token, body=body)
        self._json(status, ack)

    def do_OPTIONS(self) -> None:
        # CORS preflight: the browser sends this before any POST carrying a custom header
        # (X-Auth-Token). Without it the cross-origin write path (Approve/Reject/Send) dies
        # at the preflight — same-process tests never see it because they don't enforce CORS.
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Auth-Token, Authorization, Last-Event-ID")
        self.send_header("Access-Control-Max-Age", "86400")  # cache the preflight (one round-trip per session)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")  # dev: UI runs on a different port
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:  # keep the test/demo output quiet
        return


def build_server(cp: FakeControlPlane, *, host: str = "127.0.0.1", port: int = 8800) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), _Handler)
    httpd.daemon_threads = True  # don't hang shutdown on an open stream (ui/server.py pattern)
    httpd.control_plane = cp  # type: ignore[attr-defined]
    return httpd


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fake E21 control server (reuses control/).")
    ap.add_argument("--port", type=int, default=8800)
    ap.add_argument("--token", default="dev-token")
    ap.add_argument("--session", default="t1_demo")
    ap.add_argument("--no-reality", action="store_true", help="deterministic: no latency/drop injection")
    ap.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    args = ap.parse_args(argv)

    cp = FakeControlPlane(token=args.token, session_id=args.session, inject_reality=not args.no_reality)
    fixture = Path(args.fixture)
    if fixture.exists():
        print(f"loaded {cp.buffer.load_jsonl(fixture)} events from {fixture}")
    else:
        print(f"(no fixture at {fixture} — run tools/gen_t1_fixture.py)", file=sys.stderr)

    httpd = build_server(cp, port=args.port)
    print(
        f"fake control server → http://127.0.0.1:{args.port}  "
        f"(token={args.token!r}, reality={'off' if args.no_reality else 'on'})"
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
