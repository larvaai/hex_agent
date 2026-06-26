"""E21 Phase 3 — fake control server + replay buffer tests. Maps to S21.15/16/17.

The fake speaks the REAL E21 contract by reusing control/ (Redactor, SessionSeq, parse_command,
build_snapshot, the registries). These tests pin the seam so that wiring the real backend is
"change the URL", not "re-render": SSE streams only the redacted ui_payload, the visibility
gate drops secret events, Last-Event-ID resumes without dups, out-of-ring forces a resync, the
write path enforces a static token + registry + idempotency, and a snapshot never carries a
raw secret.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import time

from control import Actor, RedactionInfo, Redactor, RuntimeEvent, TraceContext
from control.event_registry import parse_event_registry
from control.replay import EventReplayBuffer

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load_server():
    spec = importlib.util.spec_from_file_location(
        "fake_control_server", ROOT / "tools" / "fake_control_server.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _redacted(event_type: str, payload: dict, seq: int, session_id: str = "t1") -> dict:
    """A realistic stored event dict: built through the real RuntimeEvent + Redactor path."""
    ev = RuntimeEvent(
        event_type=event_type,
        session_id=session_id,
        actor=Actor(type="runtime", id="supervisor"),
        trace=TraceContext(trace_id="tr", span_id="sp"),
        redaction=RedactionInfo(level="ui_safe"),
        payload=payload,
        seq=seq,
    )
    return Redactor().apply(ev).as_dict()


def _cp(**kw):
    return _load_server().FakeControlPlane(token="tok", session_id="t1", **kw)


# ── replay buffer (D4 / F7 / F9 / F15) ────────────────────────────────────────
def test_replay_ring_and_reality_dedup():
    buf = EventReplayBuffer(maxlen=2048)
    buf.append(_redacted("loop.turn", {"agent_id": "A"}, seq=1))
    buf.append(_redacted("loop.turn", {"agent_id": "A"}, seq=9))  # same event_id? no — distinct ids
    # explicit duplicate event_id (reality: at-least-once delivery, possibly re-stamped seq)
    dup = _redacted("loop.tool", {"tool": "x"}, seq=2)
    buf.append(dup)
    buf.append({**dup, "seq": 7})  # same event_id, different seq -> must be deduped
    ids = [e["event_id"] for e in buf.events_after(0)]
    assert len(ids) == len(set(ids))  # no duplicate event_id survives
    # ordered by seq ascending
    seqs = [int(e["seq"]) for e in buf.events_after(0)]
    assert seqs == sorted(seqs)


def test_replay_ring_evicts_oldest():
    buf = EventReplayBuffer(maxlen=3)
    for i in range(1, 6):
        buf.append(_redacted("loop.turn", {"n": i}, seq=i))
    assert len(buf.events) == 3
    assert buf.oldest_seq() == 3 and buf.newest_seq() == 5


# ── GET /api/snapshot (S21.17) ────────────────────────────────────────────────
def test_snapshot_no_raw_secret_and_unknown_session_404():
    cp = _cp()
    cp.buffer.append(_redacted("loop.team_composed", {"selected": ["A"]}, seq=1))
    cp.buffer.append(_redacted("loop.turn", {"agent_id": "A", "outcome": "ok", "api_key": "sk-LEAK"}, seq=2))
    status, body = cp.snapshot("t1")
    assert status == 200
    assert "sk-LEAK" not in json.dumps(body)
    assert cp.snapshot("nope")[0] == 404


# ── GET /api/stream (SSE) — S21.16 / F2 / F7 / F8 ─────────────────────────────
def test_sse_redacts_reachable_event():
    cp = _cp()
    cp.buffer.append(_redacted("loop.tool", {"tool": "http", "api_key": "sk-LEAK"}, seq=1))
    status, frames = cp.stream(token="tok", last_seq=0)
    assert status == 200
    blob = "".join(frames)
    assert "sk-LEAK" not in blob
    assert "[REDACTED]" in blob
    # frame shape: id/event/data
    assert "id: 1" in blob and "event: loop.tool" in blob and "data: " in blob


def test_sse_drops_secret_visibility():
    reg = parse_event_registry(
        {"event_types": {"loop.turn": {"visibility": "ui_safe"}, "debug.secret": {"visibility": "secret"}}}
    )
    cp = _cp(event_registry=reg)
    cp.buffer.append(_redacted("debug.secret", {"x": 1}, seq=1))
    cp.buffer.append(_redacted("loop.turn", {"agent_id": "A"}, seq=2))
    _, frames = cp.stream(token="tok", last_seq=0)
    blob = "".join(frames)
    assert "debug.secret" not in blob  # secret-visibility event dropped
    assert "loop.turn" in blob


def test_last_event_id_catchup_no_dup():
    cp = _cp()
    for i in range(1, 8):
        cp.buffer.append(_redacted("loop.turn", {"n": i}, seq=i))
    _, frames = cp.stream(token="tok", last_seq=5)
    sent_ids = [ln.split("id: ")[1] for f in frames for ln in f.splitlines() if ln.startswith("id: ")]
    assert sent_ids == ["6", "7"]  # only seq>5, in order, no dup


def test_out_of_ring_resync():
    cp = _cp()
    # only seq 50..52 retained; client last saw seq 5 -> the gap is gone -> resync
    for s in (50, 51, 52):
        cp.buffer.append(_redacted("loop.turn", {"s": s}, seq=s))
    _, frames = cp.stream(token="tok", last_seq=5)
    assert any("event: resync" in f for f in frames)


def test_stream_token_query():
    cp = _cp()
    cp.buffer.append(_redacted("loop.turn", {"agent_id": "A"}, seq=1))
    assert cp.stream(token="wrong", last_seq=0)[0] == 401
    assert cp.stream(token="tok", last_seq=0)[0] == 200


# ── POST /api/commands (S21.15 / S21.10 / F4 / F9) ────────────────────────────
def _cmd(**over) -> dict:
    base = {
        "command_type": "ApproveCheckpoint",
        "session_id": "t1",
        "issued_by": {"type": "human", "user_id": "u1"},
        "idempotency_key": "u1:t1:approve:1",
        "payload": {"checkpoint_id": "cp1"},
    }
    base.update(over)
    return base


def test_post_command_authz():
    cp = _cp()
    assert cp.submit_command(token="wrong", body=_cmd())[0] == 401
    assert cp.submit_command(token=None, body=_cmd())[0] == 401


def test_post_command_unknown_type():
    cp = _cp()
    status, ack = cp.submit_command(token="tok", body=_cmd(command_type="Frobnicate"))
    assert status == 400 and ack["status"] == "rejected" and ack["rejection_reason"]
    assert "command.rejected" in cp.emitted_types


def test_post_command_bad_schema():
    cp = _cp()
    bad = _cmd()
    del bad["idempotency_key"]
    status, ack = cp.submit_command(token="tok", body=bad)
    assert status == 400 and ack["status"] == "rejected"
    assert "command.rejected" in cp.emitted_types


def test_post_command_ack_and_idempotency():
    cp = _cp()
    t0 = time.perf_counter()
    status, ack = cp.submit_command(token="tok", body=_cmd())
    dt_ms = (time.perf_counter() - t0) * 1000
    assert status == 200 and ack["status"] == "received" and ack["command_id"]
    assert isinstance(ack["seq"], int)
    assert dt_ms < 300  # synchronous receipt budget

    again_status, again = cp.submit_command(token="tok", body=_cmd())
    assert again_status == 200 and again == ack  # same ack returned
    assert cp.emitted_types.count("command.received") == 1  # applied exactly once


# ── CORS preflight (browser write path: POST carries X-Auth-Token → preflight) ─
def test_options_preflight_allows_cross_origin_post():
    """A real browser sends a CORS preflight OPTIONS before any POST that carries a
    custom header (X-Auth-Token). Without handling it, the Approve/Reject/Send write
    path silently fails cross-origin (501 on preflight) even though same-process tests
    pass — the UI runs on a different port than the server. S21.15 / F8 (drop-in seam)."""
    import http.client
    import threading

    gen = _load_server()
    cp = _cp()
    httpd = gen.build_server(cp, host="127.0.0.1", port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        port = httpd.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        conn.request(
            "OPTIONS",
            "/api/commands",
            headers={
                "Origin": "http://localhost:5176",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "x-auth-token,content-type",
            },
        )
        resp = conn.getresponse()
        resp.read()
        assert resp.status in (200, 204)  # preflight must succeed, not 501
        assert resp.getheader("Access-Control-Allow-Origin") == "*"
        allow_methods = (resp.getheader("Access-Control-Allow-Methods") or "").upper()
        assert "POST" in allow_methods
        allow_headers = (resp.getheader("Access-Control-Allow-Headers") or "").lower()
        assert "x-auth-token" in allow_headers  # the auth header the write path sends
        conn.close()

        # and the real POST after a passing preflight reaches the handler + acks
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        conn.request(
            "POST",
            "/api/commands",
            body=json.dumps(_cmd()),
            headers={"Content-Type": "application/json", "X-Auth-Token": "tok"},
        )
        resp = conn.getresponse()
        body = json.loads(resp.read())
        assert resp.status == 200 and body["status"] == "received"
        conn.close()
    finally:
        httpd.shutdown()


# ── HTTP wiring smoke (R6 import path + handler) ──────────────────────────────
def test_http_server_serves_snapshot():
    import http.client
    import threading

    gen = _load_server()
    cp = _cp()
    cp.buffer.append(_redacted("loop.team_composed", {"selected": ["A"]}, seq=1))
    httpd = gen.build_server(cp, host="127.0.0.1", port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        port = httpd.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        conn.request("GET", "/api/snapshot?session=t1")
        resp = conn.getresponse()
        assert resp.status == 200
        body = json.loads(resp.read())
        assert body["session_id"] == "t1" and body["agents"][0]["agent_id"] == "A"
        conn.close()
    finally:
        httpd.shutdown()


# ── review I1: SSE gate is an allowlist — internal/restricted events never reach the wire ─
def test_sse_drops_non_uisafe_visibility():
    reg = parse_event_registry(
        {
            "event_types": {
                "loop.turn": {"visibility": "ui_safe"},
                "agent.secret": {"visibility": "internal"},
                "agent.locked": {"visibility": "restricted"},
            }
        }
    )
    cp = _cp(event_registry=reg)
    cp.buffer.append(_redacted("agent.secret", {"x": 1}, seq=1))
    cp.buffer.append(_redacted("agent.locked", {"y": 2}, seq=2))
    cp.buffer.append(_redacted("loop.turn", {"agent_id": "A"}, seq=3))
    _, frames = cp.stream(token="tok", last_seq=0)
    blob = "".join(frames)
    assert "agent.secret" not in blob and "agent.locked" not in blob  # internal/restricted dropped
    assert "loop.turn" in blob  # ui_safe passes


# ── review I3: the SSE connection cap is actually enforced (was a dead field) ──
def test_stream_cap_is_enforced():
    cp = _cp(max_sse_connections=1)
    assert cp.try_acquire_stream() is True  # first slot
    assert cp.try_acquire_stream() is False  # over the cap
    cp.release_stream()
    assert cp.try_acquire_stream() is True  # slot freed
