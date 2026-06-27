"""
runtime_event_projection.py — CQRS Read Model qua "fold events" (bản distill).

NGUỒN THẬT trong hex_agent mà case này distill từ đó:
  - control/snapshot.py:189-365  -> build_snapshot(): fold chuỗi loop.* events
        thành TaskLoopSnapshot (read model cho UI). Đây là vai PROJECTION thuần CQRS:
        events đến từ supervisor (write side), build_snapshot chiếu chúng thành một
        view tối ưu cho UI. Trạng thái agents/checkpoints/orchestrator được DERIVE
        từ fold, KHÔNG mutate trực tiếp.
  - control/snapshot.py:36-134   -> AgentView / TaskLoopSnapshot (read-model dataclass,
        frozen=True — bất biến; có as_dict/from_dict).
  - control/snapshot.py:137-178  -> _STATUS_BY_EVENT, _fields, _tool_status (helper fold).
  - control/events.py:113-190    -> RuntimeEvent (event envelope bất biến, frozen=True),
        nguồn của event_type + ui_payload mà build_snapshot đọc.

Ý TƯỞNG (đúng như plan.runnableIdea):
  Lấy ~10 RuntimeEvent loop.* (dạng dict đã serialize), đưa vào build_snapshot(),
  cho thấy tuple agents, list checkpoints và state orchestrator được DỰNG hoàn toàn
  bằng cách FOLD events — snapshot là DERIVED chứ không bị mutate trực tiếp.

CHỈ DÙNG STDLIB. Không import hex_agent, không thư viện bên thứ ba.
Hạ tầng nặng được thay bằng fake tối thiểu:
  - LLM/supervisor thật -> thay bằng danh sách event dicts dựng sẵn.
  - SQLite/SSE/HTTP -> bỏ; ta chỉ giữ phần fold (đúng vai projection).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Iterable


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# WRITE SIDE — event bất biến (distill RuntimeEvent: control/events.py:113-190)
# Trong hex_agent đây là dataclass(frozen=True) với rất nhiều field (actor, trace,
# redaction, seq...). Ở đây ta giữ đúng TINH THẦN: event là FACT quá khứ, bất biến,
# có event_type, payload (raw) và ui_payload (đã redact — cái UI được đọc).
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RuntimeEvent:
    event_type: str            # past-tense fact: "loop.turn", "loop.team_composed"...
    payload: dict[str, Any] = field(default_factory=dict)        # raw, nội bộ
    ui_payload: dict[str, Any] | None = None                     # đã redact, UI đọc cái này
    round_no: int | None = None
    created_at: str = field(default_factory=_utc_now)


# ─────────────────────────────────────────────────────────────────────────────
# READ SIDE — read model bất biến (distill AgentView/TaskLoopSnapshot snapshot.py:36-134)
# ─────────────────────────────────────────────────────────────────────────────
AGENT_STATUSES = frozenset({"pending", "waiting", "running", "done", "failed"})


@dataclass(frozen=True)
class AgentView:
    """Một node trong Agent Graph (read model). frozen=True: read model bất biến."""
    agent_id: str
    role: str = ""
    status: str = "pending"
    round_no: int = 0
    last_output_summary: str = ""

    def __post_init__(self) -> None:
        if not self.agent_id:
            raise ValueError("AgentView.agent_id phải khác rỗng.")
        if self.status not in AGENT_STATUSES:
            raise ValueError(f"status không hợp lệ: {self.status!r}")


@dataclass(frozen=True)
class TaskLoopSnapshot:
    """Toàn bộ read model UI render cho 1 session. DERIVED từ events."""
    session_id: str
    status: str = "created"
    round_no: int = 0
    orchestrator: dict[str, str] = field(default_factory=lambda: {"last_decision": "", "reason": ""})
    agents: tuple[AgentView, ...] = ()
    tool_calls: tuple[dict[str, Any], ...] = ()
    checkpoints: tuple[dict[str, Any], ...] = ()
    last_updated_at: str = field(default_factory=_utc_now)


# ── bảng fold: event-type -> trạng thái session nó hàm ý (snapshot.py:140-149) ──
_STATUS_BY_EVENT = {
    "loop.team_composed": "team_selected",
    "loop.decision": "in_discussion",
    "loop.turn": "in_discussion",
    "loop.tool": "waiting_tool",
    "loop.finished": "finished",
    "loop.blocked": "blocked",
    "loop.failed": "failed",
}
_TERMINAL_STATUS = {"finished", "blocked", "failed"}


def _fields(ev: RuntimeEvent | dict[str, Any]):
    """Chuẩn hoá event (RuntimeEvent hoặc dict JSONL) thành
    (event_type, view, redacted_view, created_at, round_no).
    view ưu tiên ui_payload (đã redact); redacted_view = ui_payload riêng (nguồn DUY NHẤT
    để copy dict free-form -> không lọt secret). Distill snapshot.py:152-167."""
    if isinstance(ev, RuntimeEvent):
        et, up, pl, created, rn = ev.event_type, ev.ui_payload, ev.payload, ev.created_at, ev.round_no
    else:
        et = str(ev.get("event_type", ""))
        up = ev.get("ui_payload")
        pl = ev.get("payload") or {}
        created = ev.get("created_at")
        rn = ev.get("round_no")
    view = up if up is not None else (pl or {})
    return et, view, up, created, rn


# ─────────────────────────────────────────────────────────────────────────────
# PROJECTION — fold events -> snapshot (distill build_snapshot snapshot.py:189-365)
# Đây là TRÁI TIM của case: state agents/checkpoints/orchestrator được DERIVE bằng
# một vòng fold tuyến tính, order-sensitive — đúng như stream event thật.
# ─────────────────────────────────────────────────────────────────────────────
def build_snapshot(events: Iterable[RuntimeEvent | dict[str, Any]], *, session_id: str) -> TaskLoopSnapshot:
    order: list[str] = []                      # giữ thứ tự agent xuất hiện
    meta: dict[str, dict[str, Any]] = {}
    turned: set[str] = set()                   # agent đã có loop.turn -> done
    waiting: set[str] = set()                  # agent bị 1 checkpoint chặn -> waiting
    latest_calls: list[str] = []               # agent trong quyết định mới nhất
    tool_calls: list[dict[str, Any]] = []
    checkpoints: list[dict[str, Any]] = []
    cp_index: dict[str, dict[str, Any]] = {}   # checkpoint_id -> entry (để approval.* resolve)
    orchestrator = {"last_decision": "", "reason": ""}
    status = "created"
    round_no = 0
    last_updated = ""

    def see(agent_id: str) -> None:
        if agent_id and agent_id not in meta:
            meta[agent_id] = {"role": "", "last_output_summary": "", "round_no": 0}
            order.append(agent_id)

    for ev in events:
        et, view, redacted, created, rn = _fields(ev)
        if created:
            last_updated = str(created)
        if rn is not None:
            round_no = max(round_no, int(rn))
        # status session: không cho marker sau ghi đè một trạng thái terminal.
        if status not in _TERMINAL_STATUS and et in _STATUS_BY_EVENT:
            status = _STATUS_BY_EVENT[et]

        if et == "loop.team_composed":
            for aid in view.get("selected") or []:
                see(str(aid))

        elif et == "loop.decision":
            orchestrator = {
                "last_decision": str(view.get("decision", "")),
                "reason": str(view.get("reason", "")),
            }
            latest_calls = [str(c.get("agent_id")) for c in (view.get("next_agent_calls") or []) if isinstance(c, dict)]
            for aid in latest_calls:
                see(aid)

        elif et == "loop.turn":
            aid = str(view.get("agent_id", ""))
            see(aid)
            if aid:
                turned.add(aid)
                meta[aid]["last_output_summary"] = str(view.get("outcome", view.get("output_summary", "")))
                if rn is not None:
                    meta[aid]["round_no"] = int(rn)
                if isinstance(redacted, dict) and redacted.get("role"):
                    meta[aid]["role"] = str(redacted["role"])

        elif et == "loop.tool":
            tool_calls.append({
                "tool": str(view.get("tool", "")),
                "status": view.get("status", "ok" if view.get("ok") else "failed"),
                "risk_level": view.get("risk_level"),
            })

        elif et == "checkpoint.reached":
            entry = {k: view.get(k) for k in ("checkpoint_id", "checkpoint_type", "risk_level", "status", "agent_id") if k in view}
            checkpoints.append(entry)
            cid = str(entry.get("checkpoint_id") or "")
            if cid:
                cp_index[cid] = entry
            aid = str(entry.get("agent_id") or "")
            if aid:
                see(aid)
                waiting.add(aid)

        elif et in ("approval.approved", "approval.rejected"):
            cid = str(view.get("checkpoint_id", ""))
            entry = cp_index.get(cid)
            new_status = "approved" if et == "approval.approved" else "rejected"
            if entry is not None:
                entry["status"] = new_status
            aid = str(view.get("agent_id") or (entry.get("agent_id") if entry else "") or "")
            waiting.discard(aid)

    # Quy tắc derive status node: done > waiting > running > pending (snapshot.py:339-352)
    running = set(latest_calls) - turned
    agents = tuple(
        AgentView(
            agent_id=aid,
            role=meta[aid]["role"],
            status=("done" if aid in turned else "waiting" if aid in waiting else "running" if aid in running else "pending"),
            round_no=meta[aid]["round_no"],
            last_output_summary=meta[aid]["last_output_summary"],
        )
        for aid in order
    )

    return TaskLoopSnapshot(
        session_id=session_id,
        status=status,
        round_no=round_no,
        orchestrator=orchestrator,
        agents=agents,
        tool_calls=tuple(tool_calls),
        checkpoints=tuple(checkpoints),
        last_updated_at=last_updated or _utc_now(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# ĐỐI CHỨNG — "read model mutable" (không tách write/read, tự sửa state trực tiếp)
# Đây là cách CRUD/anti-CQRS hay làm: dùng cùng một object cho write lẫn read,
# command đi tới đâu thì set field tới đó. Hậu quả: mất lịch sử, không rebuild được,
# và rất dễ vào trạng thái mâu thuẫn (vd: vừa "running" vừa "done").
# ─────────────────────────────────────────────────────────────────────────────
class MutableBoard:
    def __init__(self) -> None:
        self.agent_status: dict[str, str] = {}

    def on_decision(self, agent_id: str) -> None:
        self.agent_status[agent_id] = "running"

    def on_turn(self, agent_id: str) -> None:
        self.agent_status[agent_id] = "done"

    # Nếu event tới SAI THỨ TỰ (turn trước decision), state mutable sẽ kẹt sai.
    # Projection thì luôn cho kết quả đúng vì nó derive từ TẬP event, không phụ thuộc
    # thứ tự ghi-đè của hai lệnh set rời rạc.


def _sample_events() -> list[dict[str, Any]]:
    """10 event loop.* serialize sẵn (mô phỏng những gì supervisor publish)."""
    return [
        {"event_type": "loop.team_composed", "ui_payload": {"selected": ["coder", "reviewer", "tester"]}, "round_no": 0},
        {"event_type": "loop.decision", "ui_payload": {
            "decision": "delegate", "reason": "chia việc vòng 1",
            "next_agent_calls": [{"agent_id": "coder"}, {"agent_id": "reviewer"}]}, "round_no": 1},
        {"event_type": "loop.turn", "ui_payload": {"agent_id": "coder", "role": "engineer", "outcome": "viết xong module X"}, "round_no": 1},
        {"event_type": "loop.tool", "ui_payload": {"tool": "fs_write", "ok": True, "risk_level": "low"}, "round_no": 1},
        {"event_type": "checkpoint.reached", "ui_payload": {
            "checkpoint_id": "cp1", "checkpoint_type": "shell", "risk_level": "high",
            "status": "waiting", "agent_id": "reviewer"}, "round_no": 1},
        {"event_type": "loop.tool", "ui_payload": {"tool": "shell", "ok": False, "status": "failed", "risk_level": "high"}, "round_no": 1},
        {"event_type": "approval.approved", "ui_payload": {"checkpoint_id": "cp1", "agent_id": "reviewer"}, "round_no": 1},
        {"event_type": "loop.turn", "ui_payload": {"agent_id": "reviewer", "role": "reviewer", "outcome": "duyệt OK"}, "round_no": 1},
        {"event_type": "loop.decision", "ui_payload": {
            "decision": "delegate", "reason": "vòng 2: kiểm thử",
            "next_agent_calls": [{"agent_id": "tester"}]}, "round_no": 2},
        {"event_type": "loop.finished", "ui_payload": {}, "round_no": 2},
    ]


def demo() -> None:
    print("=" * 72)
    print("CASE 01 — Runtime Event Projection (CQRS Read Model qua fold)")
    print("Distill từ control/snapshot.py:189-365 (build_snapshot)")
    print("=" * 72)

    events = _sample_events()
    print(f"\n[WRITE SIDE] supervisor đã publish {len(events)} event loop.* (bất biến):")
    for i, ev in enumerate(events, 1):
        print(f"  {i:>2}. {ev['event_type']:<20} {ev.get('ui_payload')}")

    print("\n[PROJECTION] build_snapshot() FOLD chuỗi event -> 1 read model duy nhất...")
    snap = build_snapshot(events, session_id="sess-001")

    print(f"\n[READ MODEL] TaskLoopSnapshot (DERIVED, không mutate trực tiếp):")
    print(f"  status        = {snap.status}")
    print(f"  round_no      = {snap.round_no}")
    print(f"  orchestrator  = {snap.orchestrator}")
    print(f"  agents:")
    for a in snap.agents:
        print(f"    - {a.agent_id:<10} status={a.status:<8} role={a.role!r:<12} outcome={a.last_output_summary!r}")
    print(f"  tool_calls    = {list(snap.tool_calls)}")
    print(f"  checkpoints   = {list(snap.checkpoints)}")

    # ── ASSERT: chứng minh state là DERIVE đúng từ fold ──────────────────────
    by_id = {a.agent_id: a for a in snap.agents}
    # coder & reviewer đã có loop.turn -> done
    assert by_id["coder"].status == "done", "coder phải done sau loop.turn"
    assert by_id["reviewer"].status == "done", "reviewer phải done sau loop.turn"
    # tester nằm trong decision mới nhất, chưa turn -> running
    assert by_id["tester"].status == "running", "tester phải running (trong decision mới nhất, chưa turn)"
    # checkpoint cp1 đã được approval.approved resolve -> không còn 'waiting'
    assert snap.checkpoints[0]["status"] == "approved", "cp1 phải approved sau approval.approved"
    assert by_id["reviewer"].status != "waiting", "reviewer không còn waiting sau khi gate resolve"
    # status terminal 'finished' không bị marker sau ghi đè
    assert snap.status == "finished", "status phải là finished (terminal)"
    print("\n[ASSERT] OK: agents/checkpoints/status đều DERIVE đúng từ fold events.")

    # ── BẤT BIẾN read model: rebuild lại từ CÙNG event -> CÙNG kết quả ────────
    snap2 = build_snapshot(events, session_id="sess-001")
    same = {a.agent_id: a.status for a in snap.agents} == {a.agent_id: a.status for a in snap2.agents}
    assert same, "fold cùng event phải cho cùng read model (determinism)"
    print("[ASSERT] OK: fold deterministic — rebuild từ cùng event cho cùng read model.")

    # ── read model bất biến (frozen=True): không thể mutate ──────────────────
    try:
        snap.agents[0].status = "failed"  # type: ignore[misc]
        raise AssertionError("Lẽ ra không sửa được AgentView (frozen=True)")
    except (AttributeError, TypeError):
        print("[ASSERT] OK: AgentView frozen=True — read model bất biến, không ai mutate được.")

    # ── ĐỐI CHỨNG: read model mutable + event SAI THỨ TỰ -> kẹt sai ──────────
    print("\n" + "-" * 72)
    print("[ĐỐI CHỨNG] MutableBoard (anti-CQRS): set state trực tiếp, phụ thuộc thứ tự ghi-đè")
    print("-" * 72)
    out_of_order = [("turn", "coder"), ("decision", "coder")]  # turn ĐẾN TRƯỚC decision
    board = MutableBoard()
    for kind, aid in out_of_order:
        (board.on_turn if kind == "turn" else board.on_decision)(aid)
    print(f"  Event tới sai thứ tự {out_of_order} -> MutableBoard.agent_status = {board.agent_status}")
    assert board.agent_status["coder"] == "running", "Mutable bị decision ghi đè -> 'running' (SAI: coder đã turn xong)"
    print("  => SAI: coder đã có turn (phải 'done') nhưng bị decision sau ghi đè thành 'running'.")

    # Cùng tập event đó, projection vẫn ĐÚNG vì derive từ cả tập, ưu tiên 'turned'.
    proj_events = [
        {"event_type": "loop.turn", "ui_payload": {"agent_id": "coder", "outcome": "xong"}},
        {"event_type": "loop.decision", "ui_payload": {"next_agent_calls": [{"agent_id": "coder"}]}},
    ]
    proj = build_snapshot(proj_events, session_id="s")
    assert proj.agents[0].status == "done", "projection vẫn cho 'done' vì 'turned' thắng 'running'"
    print(f"  => build_snapshot trên CÙNG event: coder.status = {proj.agents[0].status!r} (ĐÚNG: done).")
    print("\n  KẾT: tách write (events) khỏi read (projection) + derive-không-mutate giúp read model")
    print("       luôn nhất quán; cách mutable trực tiếp dễ vào trạng thái mâu thuẫn.")

    print("\n" + "=" * 72)
    print("XONG CASE 01.")
    print("=" * 72)


if __name__ == "__main__":
    demo()
