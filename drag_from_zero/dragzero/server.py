"""HTTP + WebSocket adapter that serves the Agent-IDE UI (Slice 6a).

Pure stdlib (no FastAPI): an `http.server` exposing the REST + WS contract the UI
expects, plus the two translation layers it needs:

  * `build_graph`  — reshapes our execution tree (read-model) into the UI's
    `{root, nodes, edges}` graph, filling the fields it reads (goal, mu,
    done_when, depends_on, children, runtime). mu/done_when are best-effort here;
    the verifier that fills them properly is Slice 6b.
  * `translate_event` — maps our event vocabulary onto the UI's
    (activate / propose / decompose / verdict / block / run_end).

A run executes on a background thread; every event is translated, buffered, and
broadcast to connected WS clients (buffer replay on connect, then live). The
orchestrator is untouched — this only *reads* its event log. `log.events()`
returns a GIL-atomic list copy, so reading the graph from another thread is safe.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import struct
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Empty, Queue
from threading import Lock, Thread
from urllib.parse import parse_qs, urlparse

from .contracts import TaskStatus
from .events import EventType
from .read_model import reduce
from .verifier import build_done_when, mu, run_checks

_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

_UI_STATUS = {
    TaskStatus.DONE.value: "done",
    TaskStatus.RUNNING.value: "active",
    TaskStatus.DELEGATED.value: "decomposed",
    TaskStatus.WAITING.value: "blocked",
    TaskStatus.FAILED.value: "blocked",
    TaskStatus.HALTED.value: "blocked",
    TaskStatus.BLOCKED.value: "blocked",
    TaskStatus.PENDING.value: "pending",
}


# --------------------------------------------------------------------------- #
# graph reshape: execution tree -> UI graph  (Slice 6b: code-owned verdicts)
# --------------------------------------------------------------------------- #
# A node carries `done_when` criteria authored in the run spec, keyed by node id,
# by `"__root__"` for the entry task, or by agent id (role). When the model CLAIMS a
# node complete (status done/delegated), code re-derives PASS/FAIL by running the gate
# over the sandbox — the model's claim never sets the verdict (spec.md:46,110-116).
# A node with no authored criteria is `unverified` (honest), never a faked pass.

def _done_when_raw(node, root_id, spec) -> list:
    if getattr(node, "done_when", None):  # Gap 2: worker-proposed criteria carried on the node win
        return node.done_when
    if node.id == root_id and "__root__" in spec:
        return spec["__root__"]
    if node.id in spec:
        return spec[node.id]
    if node.agent_id and node.agent_id in spec:
        return spec[node.agent_id]
    return []


def _verify_node(node, sandbox, spec, root_id, activated_at):
    """-> (done_when_dicts, verdict_str, mu_local). verdict ∈ PASS|FAIL|pending|unverified."""
    try:
        triples = build_done_when(_done_when_raw(node, root_id, spec))
    except ValueError as exc:  # our authored spec is malformed — surface, don't crash
        return [{"check": "malformed", "artifact": None, "ok": False, "reason": str(exc)}], "FAIL", 1

    if not triples:
        return [], "unverified", 1

    child_statuses = [c.status for c in node.children] if node.children else None
    # Judge only when the node is actually settled: a leaf the model completed (DONE), or a
    # delegated parent whose children have all settled. A still-running parent is `pending`,
    # not FAIL — we don't flash a red verdict mid-flight before its children finish.
    settled = node.status == TaskStatus.DONE.value or (
        node.status == TaskStatus.DELEGATED.value
        and bool(child_statuses)
        and all(s in (TaskStatus.DONE.value, TaskStatus.BLOCKED.value) for s in child_statuses)
    )
    if not settled or sandbox is None:
        return [{"check": t.check, "artifact": t.artifact, "ok": None, "reason": ""} for t in triples], "pending", mu(triples)

    v = run_checks(triples, sandbox.root, node_id=node.id, activated_at=activated_at, child_statuses=child_statuses)
    return [r.as_dict() for r in v.results], v.node_verdict, mu(triples)


def build_graph(log, sandbox=None, spec=None, activated_at=None) -> dict:
    spec = spec or {}
    root, nodes = reduce(log.events())
    if root is None:
        return {"root": None, "nodes": [], "edges": []}

    verified = {n.id: _verify_node(n, sandbox, spec, root.id, activated_at) for n in nodes.values()}

    def mu_of(n) -> int:  # μ = done_when_count, summed over the subtree (the spec's measure)
        return verified[n.id][2] + sum(mu_of(c) for c in n.children)

    ui_nodes, edges = [], []
    for n in nodes.values():
        done_when, verdict, _ = verified[n.id]
        status = _UI_STATUS.get(n.status, "pending")
        if verdict == "FAIL":
            status = "blocked"  # code overrides the model's "done" claim
        elif verdict == "PASS":
            status = "done"
        ui_nodes.append({
            "id": n.id,
            "goal": n.description,
            "mu": mu_of(n),
            "done_when": done_when,
            "verdict": verdict,
            "depends_on": [],
            "children": [c.id for c in n.children],
            "runtime": {"status": status, "agent": n.agent_id},
        })
        if n.parent_id:
            edges.append({"source": n.parent_id, "target": n.id, "kind": "child"})
    return {"root": root.id, "nodes": ui_nodes, "edges": edges}


def _final_status(log, sandbox=None, spec=None, activated_at=None) -> str:
    root, _ = reduce(log.events())
    if root is None:
        return "created"
    _, verdict, _ = _verify_node(root, sandbox, spec or {}, root.id, activated_at)
    if verdict == "PASS":
        return "done"
    if verdict == "FAIL":  # the model said done; code says the gate failed
        return "blocked"
    if root.status == TaskStatus.DONE.value:  # unverified/pending → model's terminal word
        return "done"
    if root.status in (TaskStatus.FAILED.value, TaskStatus.HALTED.value, TaskStatus.BLOCKED.value, TaskStatus.WAITING.value):
        return "blocked"
    return "done"


# --------------------------------------------------------------------------- #
# event vocabulary translation: ours -> the UI's
# --------------------------------------------------------------------------- #
def _short_args(args) -> str:
    if not isinstance(args, dict):
        return ""
    return ", ".join(f"{k}={str(v)[:24]}" for k, v in args.items())


def translate_event(ev, verdict_fn=None) -> list:
    t, nid, p = ev.type, ev.task_id, (ev.payload or {})

    def E(typ, node_id=nid, payload=None):
        return {"type": "event", "data": {"type": typ, "node_id": node_id, "payload": payload or {}}}

    if t == EventType.TASK_STARTED:
        return [E("activate")]
    if t == EventType.TOOL_CALLED:
        return [E("propose", payload={"action": f"{p.get('tool')}({_short_args(p.get('args'))})"})]
    if t == EventType.SUBTASK_SPAWNED:
        return [E("decompose", node_id=p.get("parent"), payload={"children": [nid]})]
    if t == EventType.TASK_WAITING:
        return [E("block", payload={"reason": f"waiting for {p.get('target')}", "detail": ""})]
    if t == EventType.TASK_COMPLETED:
        # The completion is the model's CLAIM; the verdict is code's, re-derived over the
        # sandbox by verdict_fn. With no spec, fall back to the claim (orchestration-only runs).
        if verdict_fn is not None:
            passed, gate, evidence = verdict_fn(nid)
        else:
            passed = True
            gate = "compose" if p.get("result") == "delegated" else "solve"
            evidence = str(p.get("result", "done"))
        return [E("verdict", payload={"passed": passed, "gate": gate, "evidence": evidence})]
    if t == EventType.TASK_FAILED:
        return [E("verdict", payload={"passed": False, "gate": "solve", "evidence": str(p.get("error", "failed"))})]
    if t == EventType.HOOK_BLOCKED:
        return [E("block", payload={"reason": str(p.get("reason", "blocked")), "detail": str(p.get("phase", ""))})]
    if t == EventType.BUDGET_EXCEEDED:
        return [E("block", payload={"reason": "budget exceeded", "detail": f"used {p.get('used')}/{p.get('limit')}"})]
    # Gap 2 — decompose-until-trivial narration
    if t == EventType.LEAF_VERIFIED:
        reasons = "; ".join(p.get("reasons") or [])
        return [E("verdict", payload={"passed": p.get("verdict") == "PASS", "gate": "solve",
                                      "evidence": reasons or str(p.get("verdict", ""))})]
    if t == EventType.DECOMPOSITION_ACCEPTED:
        return [E("decompose", payload={"children": p.get("children") or []})]
    # Gap 3 — capability denials
    if t == EventType.TOOL_DENIED:
        return [E("block", payload={"reason": f"tool {p.get('tool')!r} denied", "detail": "capability"})]
    if t == EventType.CAPABILITY_EXHAUSTED:
        return [E("block", payload={"reason": str(p.get("reason", "capability exhausted")), "detail": "capability"})]
    return []


# --------------------------------------------------------------------------- #
# a run
# --------------------------------------------------------------------------- #
class Run:
    """One UI session: rebuildable orchestrator + buffered/broadcast event frames.

    `builder()` returns a fresh `(orchestrator, entry_agent, sandbox)`. reset()
    rebuilds and seeds the root; start() runs it on a daemon thread.
    """

    def __init__(self, id: str, title: str, task: str, builder, pace: float = 0.0,
                 done_when: dict | None = None, root_done_when: list | None = None) -> None:
        self.id = id
        self.title = title
        self.task = task
        self.builder = builder
        self.pace = pace
        self.done_when = done_when or {}  # projection spec: {node_id|"__root__"|agent_id: [criterion,...]}
        self.root_done_when = root_done_when  # Gap 2: the root task's own gate → orchestrator runs gated
        self._activated_at = None         # gate freshness floor; stamped at start()
        self._lock = Lock()
        self.frames: list = []
        self.subscribers: set = set()
        self.status = "created"
        self.done = False
        self.orch = None
        self.entry = None
        self.sandbox = None
        self.reset()

    # --- lifecycle ---
    def reset(self) -> None:
        with self._lock:
            if self.status == "running":
                return
            self.orch, self.entry, self.sandbox = self.builder()
            self.orch.start(self.task, agent=self.entry, done_when=self.root_done_when)
            self.frames = []
            self.status = "created"
            self.done = False

    def start(self) -> None:
        with self._lock:
            if self.status == "running":
                return
            self.status = "running"
            self.done = False
            self.frames = []
            self._activated_at = time.time()  # artifacts written from here on count as FRESH
        Thread(target=self._run, daemon=True).start()

    def _verdict_fn(self, task_id: str):
        """Code-owned verdict for a completed task: run the gate over the sandbox."""
        root, nodes = reduce(self.orch.log.events())
        node = nodes.get(task_id)
        if node is None:
            return True, "solve", "done"
        done_when, verdict, _ = _verify_node(node, self.sandbox, self.done_when,
                                              root.id if root else None, self._activated_at)
        if verdict == "unverified":
            return True, "solve", "completed (no done_when authored)"
        gate = "compose" if node.children else "solve"
        reasons = "; ".join(r["reason"] for r in done_when if r.get("ok") is False and r.get("reason"))
        return verdict == "PASS", gate, (reasons or verdict.lower())

    def _run(self) -> None:
        self._emit({"type": "event", "data": {"type": "run_start", "node_id": None, "payload": {}}})
        self._emit_snapshot()

        def sub(ev):
            for frame in translate_event(ev, self._verdict_fn):
                self._emit(frame)
            self._emit_snapshot()
            if self.pace:
                time.sleep(self.pace)

        self.orch.log.subscribe(sub)
        try:
            self.orch.run_until_idle()
            status = _final_status(self.orch.log, self.sandbox, self.done_when, self._activated_at)
        except Exception as exc:  # never let a run kill the server thread
            status = "blocked"
            self._emit({"type": "event", "data": {"type": "block", "node_id": None, "payload": {"reason": str(exc)}}})

        self._emit({"type": "event", "data": {"type": "run_end", "node_id": None,
                                              "payload": {"status": status, "steps_spent": len(self.orch.log)}}})
        self._emit_snapshot()
        with self._lock:
            self.status = status
            self.done = True
        self._emit({"type": "run_finished"})

    # --- frames ---
    def graph(self) -> dict:
        return build_graph(self.orch.log, self.sandbox, self.done_when, self._activated_at)

    def _emit_snapshot(self) -> None:
        self._emit({"type": "snapshot", "graph": self.graph()})

    def _emit(self, frame: dict) -> None:
        with self._lock:
            self.frames.append(frame)
            for q in self.subscribers:
                q.put(frame)

    def subscribe(self):
        """Register a queue, returning (backlog, queue, already_done) atomically."""
        q: Queue = Queue()
        with self._lock:
            backlog = list(self.frames)
            self.subscribers.add(q)
            return backlog, q, self.done

    def unsubscribe(self, q) -> None:
        with self._lock:
            self.subscribers.discard(q)

    # --- artifacts ---
    def artifacts(self) -> list:
        if self.sandbox is None:
            return []
        root = str(self.sandbox.root)
        out = []
        for dirpath, _, files in os.walk(root):
            for f in files:
                rel = os.path.relpath(os.path.join(dirpath, f), root).replace(os.sep, "/")
                out.append({"path": rel})
        return sorted(out, key=lambda a: a["path"])

    def read_artifact(self, path: str) -> str:
        try:
            return self.sandbox.read(path)
        except Exception as exc:
            return f"// could not load {path}: {exc}"


# --------------------------------------------------------------------------- #
# app + HTTP/WS handler
# --------------------------------------------------------------------------- #
class App:
    def __init__(self, run: Run, static_dir: str, index_file: str) -> None:
        self.runs = {run.id: run}
        self.default_run = run
        self.static_dir = os.path.abspath(static_dir)
        self.index_file = index_file

    def get_run(self, rid: str) -> Run:
        run = self.runs.get(rid)
        if run is None:
            raise KeyError(rid)
        return run

    def session(self) -> dict:
        r = self.default_run
        return {"id": r.id, "status": r.status, "title": r.title, "graph": r.graph()}


_CTYPES = {".html": "text/html", ".js": "application/javascript", ".json": "application/json",
           ".css": "text/css", ".svg": "image/svg+xml"}


def _ws_encode(text: str) -> bytes:
    data = text.encode("utf-8")
    n = len(data)
    head = bytearray([0x81])
    if n < 126:
        head.append(n)
    elif n < 65536:
        head.append(126)
        head += struct.pack(">H", n)
    else:
        head.append(127)
        head += struct.pack(">Q", n)
    return bytes(head) + data


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # quiet
        pass

    @property
    def app(self) -> App:
        return self.server.app  # type: ignore[attr-defined]

    def _json(self, obj, code=200) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        try:
            u = urlparse(self.path)
            path = u.path
            if path.startswith("/api/"):
                return self._api_get(path, u)
            return self._static(path)
        except KeyError:
            return self._json({"detail": "not found"}, 404)
        except Exception as exc:  # noqa: BLE001
            return self._json({"detail": str(exc)}, 500)

    def _api_get(self, path, u) -> None:
        if path == "/api/session":
            return self._json(self.app.session())
        m = re.match(r"^/api/runs/([^/]+)$", path)
        if m:
            run = self.app.get_run(m.group(1))
            return self._json({"graph": run.graph(), "status": run.status})
        m = re.match(r"^/api/runs/([^/]+)/artifacts$", path)
        if m:
            return self._json(self.app.get_run(m.group(1)).artifacts())
        m = re.match(r"^/api/runs/([^/]+)/artifact$", path)
        if m:
            p = (parse_qs(u.query).get("path") or [""])[0]
            return self._json({"content": self.app.get_run(m.group(1)).read_artifact(p)})
        m = re.match(r"^/api/runs/([^/]+)/events$", path)
        if m and self.headers.get("Upgrade", "").lower() == "websocket":
            return self._ws(self.app.get_run(m.group(1)))
        return self._json({"detail": "not found"}, 404)

    def do_POST(self) -> None:
        try:
            path = urlparse(self.path).path
            m = re.match(r"^/api/runs/([^/]+)/reset$", path)
            if m:
                self.app.get_run(m.group(1)).reset()
                return self._json({"ok": True})
            m = re.match(r"^/api/runs/([^/]+)/start$", path)
            if m:
                self.app.get_run(m.group(1)).start()
                return self._json({"ok": True})
            return self._json({"detail": "not found"}, 404)
        except KeyError:
            return self._json({"detail": "not found"}, 404)
        except Exception as exc:  # noqa: BLE001
            return self._json({"detail": str(exc)}, 500)

    def _static(self, path) -> None:
        fname = self.app.index_file if path in ("/", "") else path.lstrip("/")
        full = os.path.normpath(os.path.join(self.app.static_dir, fname))
        if not full.startswith(self.app.static_dir) or not os.path.isfile(full):
            return self._json({"detail": "not found"}, 404)
        with open(full, "rb") as f:
            data = f.read()
        ctype = _CTYPES.get(os.path.splitext(full)[1], "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _ws(self, run: Run) -> None:
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            return self._json({"detail": "bad websocket handshake"}, 400)
        accept = base64.b64encode(hashlib.sha1((key + _WS_GUID).encode()).digest()).decode()
        self.connection.sendall(
            (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
            ).encode()
        )
        self.close_connection = True
        sock = self.connection

        def send(frame):
            sock.sendall(_ws_encode(json.dumps(frame)))

        backlog, q, done = run.subscribe()
        try:
            for frame in backlog:
                send(frame)
            while not done:
                try:
                    frame = q.get(timeout=60)
                except Empty:
                    break
                send(frame)
                if frame.get("type") == "run_finished":
                    break
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            run.unsubscribe(q)


def make_server(run: Run, static_dir: str, host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), _Handler)
    httpd.daemon_threads = True
    httpd.app = App(run, static_dir, "Agent IDE.dc.html")  # type: ignore[attr-defined]
    return httpd
