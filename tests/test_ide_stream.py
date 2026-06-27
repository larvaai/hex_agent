"""L1 backend-integration — the held-open SSE stream (server.py:387-436), driven over a real socket
against the real ``IdeControlServer``. No model: events are seeded in-process via ``session.emit``,
which is the only model-free door onto ``loop.*`` state.

Asserts the four stream invariants the browser can't observe deterministically without the model:
redaction (only ``ui_payload`` ever crosses the wire), the visibility filter (internal events are
dropped but seq still advances), Last-Event-ID catch-up, and the out-of-ring ``resync`` frame.
"""
from __future__ import annotations

import socket
import threading
import time
from http.client import HTTPConnection

import pytest

import ui.ide.server as server_mod
from control.replay import EventReplayBuffer


@pytest.fixture()
def server(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    srv = server_mod.IdeControlServer(("127.0.0.1", 0), token="tok", session_id="t1_demo")
    port = srv.socket.getsockname()[1]
    thread = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    time.sleep(0.1)
    try:
        yield srv, port
    finally:
        srv.shutdown()
        srv.server_close()


# ── redaction: the wire carries ui_payload, never the raw secret (security backbone) ──
@pytest.mark.security
@pytest.mark.integration
def test_stream_emits_ui_payload_only_never_raw(server):
    """Seed a secret-keyed event; the SSE frame must carry ``[REDACTED]`` and the raw secret must be
    absent from the *entire* byte stream. Invert: if ``_stream`` fell back to ``ev['payload']`` the
    raw ``sk-…`` would appear and this fails — that is the fake-vs-real discriminator."""
    srv, port = server
    secret = "sk-LIVE-SECRET-zzz999"
    srv.registry.get("t1_demo").emit("loop.tool", {"tool": "fs_write", "ok": True, "api_key": secret})

    text = _read_sse(port, "token=tok&session=t1_demo&lastEventId=0")
    assert "[REDACTED]" in text
    assert secret not in text


# ── visibility filter: internal dropped, but last_seq still advances (server.py:419) ──
@pytest.mark.security
@pytest.mark.integration
def test_stream_visibility_filter_drops_internal(server):
    srv, port = server
    session = srv.registry.get("t1_demo")
    session.emit("agent.output.raw", {"text": "internal-only-chain-of-thought"})  # seq 1, internal
    session.emit("loop.tool", {"tool": "fs_read", "ok": True})  # seq 2, ui_safe

    text = _read_sse(port, "token=tok&session=t1_demo&lastEventId=0")
    assert "event: agent.output.raw" not in text  # internal never framed
    assert "internal-only-chain-of-thought" not in text
    assert "id: 2" in text  # the ui_safe event keeps its true seq — the filter advanced past seq 1


# ── Last-Event-ID catch-up: only seq>k delivered, in order ────────────────────────
@pytest.mark.integration
def test_stream_last_event_id_resumes(server):
    srv, port = server
    session = srv.registry.get("t1_demo")
    for i in range(1, 5):  # seq 1..4
        session.emit("loop.tool", {"tool": f"t{i}", "ok": True})

    text = _read_sse(port, "token=tok&session=t1_demo&lastEventId=2")
    assert "id: 1" not in text and "id: 2" not in text  # already-seen, not replayed
    assert "id: 3" in text and "id: 4" in text
    assert text.index("id: 3") < text.index("id: 4")  # ordered by seq


# ── out-of-ring resync frame, not a silent gap (replay.needs_resync) ──────────────
@pytest.mark.integration
def test_stream_resync_frame_when_out_of_ring(server):
    srv, port = server
    session = srv.registry.get("t1_demo")
    session.buffer = EventReplayBuffer(maxlen=2)  # shrink the ring so early seqs fall off
    for i in range(1, 6):  # seq 1..5; only 4,5 survive the ring
        session.emit("loop.tool", {"tool": f"t{i}", "ok": True})

    # client last saw seq 1 — long since evicted → the server must signal resync, not skip silently
    text = _read_sse(port, "token=tok&session=t1_demo&lastEventId=1")
    assert "event: resync" in text


# ── SSE socket reader: read lines until the stream goes quiet (no model, bounded) ──
def _read_sse(port, query, *, read_seconds=1.5):
    conn = HTTPConnection("127.0.0.1", port, timeout=read_seconds + 3)
    conn.request("GET", f"/api/stream?{query}")
    # getresponse() hands the socket to the response (conn.sock → None) for a read-to-close body, so
    # grab the live socket first and set the read timeout on it — the SSE stream never sends EOF.
    sock = conn.sock
    sock.settimeout(read_seconds)
    resp = conn.getresponse()
    assert resp.status == 200
    lines: list[bytes] = []
    try:
        while True:
            line = resp.fp.readline()
            if not line:
                break
            lines.append(line)
    except (socket.timeout, TimeoutError, OSError):
        pass  # backlog drained, stream idle → done
    finally:
        conn.close()
    return b"".join(lines).decode("utf-8", "replace")
