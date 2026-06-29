"""
Case 02 — Event Projection: fold chuỗi loop.* event thành TaskLoopSnapshot
==========================================================================

Bản DISTILL TRUNG THỰC (chỉ dùng thư viện chuẩn Python 3) của cơ chế "read model =
projection của event" trong hex_agent. Trong Event Storming (38_EventStorming.md),
sticky GREEN là read model: một view derive ra từ chuỗi event, KHÔNG phải nguồn sự
thật. hex_agent hiện thực đúng vậy: UI không bao giờ tự sửa state; nó render một
TaskLoopSnapshot được *fold* từ các loop.* event mà supervisor đã emit.

Bất biến cốt lõi của event sourcing: replay CÙNG chuỗi event LUÔN cho ra CÙNG snapshot.

NGUỒN THẬT distill từ (đã mở & xác nhận line):
  - control/snapshot.py:88-134   -> TaskLoopSnapshot (read model UI render cho 1 session)
  - control/snapshot.py:36-85    -> AgentView (node trong Agent Graph)
  - control/snapshot.py:140-148  -> _STATUS_BY_EVENT (policy: loop event -> session status)
  - control/snapshot.py:189-365  -> build_snapshot (fold tuyen tinh, order-sensitive)
  - control/snapshot.py:339-352  -> luat derive status: done/running/waiting/pending
  - supervisor/graph.py:56-75    -> SupervisorContext.emit (business logic emit event)
  - supervisor/graph.py:103      -> compose_team emit loop.team_composed
  - supervisor/graph.py:122      -> o_decide emit loop.decision
  - supervisor/graph.py:209      -> run_round emit loop.turn
  - supervisor/graph.py:226      -> run_tool emit loop.tool

LƯỢC BỎ so với bản thật:
  - Bỏ Blackboard/TaskLoopState thật, DelegationService, Broker, Orchestrator LLM
    -> thay bằng hàm fake sinh ra loop.* event.
  - Bỏ redaction/ui_payload (đã minh hoạ ở case 01) -> đọc thẳng payload cho gọn.
  - Bỏ checkpoint/approval resolve (giữ phần lõi: team_composed/decision/turn/tool/finished).

Chạy: python3 event_projection_snapshot.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


# =============================================================================
# [DOMAIN EVENT] — đơn giản hoá RuntimeEvent. control/events.py:113-152
# Ở đây chỉ cần event_type + payload + round_no cho việc fold.
# =============================================================================
@dataclass(frozen=True)
class LoopEvent:
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    round_no: int | None = None


# =============================================================================
# [READ MODEL] — AgentView + TaskLoopSnapshot (sticky GREEN / projection)
# control/snapshot.py:36-85 (AgentView), :88-134 (TaskLoopSnapshot)
# Frozen: projection là giá trị bất biến, render xong là xong.
# =============================================================================
AGENT_STATUSES = frozenset({"pending", "waiting", "running", "done", "failed"})


@dataclass(frozen=True)
class AgentView:
    """Một node trong Agent Graph. control/snapshot.py:36-85."""
    agent_id: str
    role: str = ""
    status: str = "pending"
    round_no: int = 0
    last_output_summary: str = ""

    def __post_init__(self) -> None:
        if not self.agent_id:
            raise ValueError("AgentView.agent_id bat buoc.")
        if self.status not in AGENT_STATUSES:
            raise ValueError(f"AgentView.status phai thuoc {sorted(AGENT_STATUSES)}, gap {self.status!r}.")

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "status": self.status,
            "round_no": self.round_no,
            "last_output_summary": self.last_output_summary,
        }


@dataclass(frozen=True)
class TaskLoopSnapshot:
    """Read model UI render cho 1 session. control/snapshot.py:88-134.

    KHÔNG phải state — là projection fold từ event. UI không mutate cái này.
    """
    session_id: str
    status: str = "created"
    round_no: int = 0
    orchestrator: dict[str, str] = field(default_factory=lambda: {"last_decision": "", "reason": ""})
    agents: tuple[AgentView, ...] = ()
    tool_calls: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "round_no": self.round_no,
            "orchestrator": dict(self.orchestrator),
            "agents": [a.as_dict() for a in self.agents],
            "tool_calls": [dict(c) for c in self.tool_calls],
        }


# =============================================================================
# [POLICY] — loop event -> session status. control/snapshot.py:140-148
# Terminal status thắng: đã 'finished' thì marker sau không ghi đè.
# =============================================================================
_STATUS_BY_EVENT = {
    "loop.team_composed": "team_selected",
    "loop.decision":      "in_discussion",
    "loop.turn":          "in_discussion",
    "loop.tool":          "waiting_tool",
    "loop.finished":      "finished",
    "loop.blocked":       "blocked",
    "loop.failed":        "failed",
}
_TERMINAL_STATUS = {"finished", "blocked", "failed"}


# =============================================================================
# [FOLD] — build_snapshot: gập tuyến tính chuỗi event thành 1 snapshot.
# control/snapshot.py:189-365 (rút gọn phần lõi)
#
# Luật derive status (control/snapshot.py:339-352):
#   - 'done'    : agent đã có loop.turn
#   - 'running' : agent nằm trong next_agent_calls của decision mới nhất và CHƯA có turn
#   - 'pending' : còn lại
# (waiting/failed lược bỏ trong bản distill này)
# =============================================================================
def build_snapshot(events: Iterable[LoopEvent], *, session_id: str) -> TaskLoopSnapshot:
    order: list[str] = []                 # giữ thứ tự agent xuất hiện
    meta: dict[str, dict[str, Any]] = {}  # agent_id -> {role, last_output_summary, round_no}
    turned: set[str] = set()              # agent đã có loop.turn
    latest_calls: list[str] = []          # agent_id trong decision mới nhất
    tool_calls: list[dict[str, Any]] = []
    orchestrator = {"last_decision": "", "reason": ""}
    status = "created"
    round_no = 0

    def see(agent_id: str) -> None:
        if agent_id and agent_id not in meta:
            meta[agent_id] = {"role": "", "last_output_summary": "", "round_no": 0}
            order.append(agent_id)

    for ev in events:
        view = ev.payload
        if ev.round_no is not None:
            round_no = max(round_no, ev.round_no)
        # session status: terminal không bị ghi đè bởi marker sau (control/snapshot.py:232-233)
        if status not in _TERMINAL_STATUS and ev.event_type in _STATUS_BY_EVENT:
            status = _STATUS_BY_EVENT[ev.event_type]

        if ev.event_type == "loop.team_composed":
            for aid in view.get("selected") or []:
                see(str(aid))

        elif ev.event_type == "loop.decision":
            orchestrator = {
                "last_decision": str(view.get("decision", "")),
                "reason": str(view.get("reason", "")),
            }
            latest_calls = [str(c["agent_id"]) for c in (view.get("next_agent_calls") or []) if "agent_id" in c]
            for aid in latest_calls:
                see(aid)

        elif ev.event_type == "loop.turn":
            aid = str(view.get("agent_id", ""))
            see(aid)
            if aid:
                turned.add(aid)
                meta[aid]["last_output_summary"] = str(view.get("outcome", ""))
                if ev.round_no is not None:
                    meta[aid]["round_no"] = ev.round_no
                if view.get("role"):
                    meta[aid]["role"] = str(view["role"])

        elif ev.event_type == "loop.tool":
            tool_calls.append({
                "tool": str(view.get("tool", "")),
                "status": "ok" if view.get("ok") else "failed",
            })

    running = set(latest_calls) - turned
    agents = tuple(
        AgentView(
            agent_id=aid,
            role=meta[aid]["role"],
            status=("done" if aid in turned else "running" if aid in running else "pending"),
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
    )


# =============================================================================
# [BUSINESS LOGIC emit event] — fake supervisor.
# Tương ứng supervisor/graph.py:103/122/209/226 (compose_team/o_decide/run_round/run_tool).
# Trong code thật mỗi node mutate Blackboard rồi gọi ctx.emit(...) — ở đây ta chỉ
# trả ra chuỗi event (chính là cái supervisor publish).
# =============================================================================
def fake_supervisor_run() -> list[LoopEvent]:
    """Mô phỏng 1 vòng multi-agent: chọn team 3 agent, O quyết định giao 3 agent,
    cả 3 chạy turn, gọi 1 tool, rồi finished."""
    events: list[LoopEvent] = []
    # compose_team -> loop.team_composed  (supervisor/graph.py:103)
    events.append(LoopEvent("loop.team_composed", {"selected": ["researcher", "writer", "reviewer"]}))
    # o_decide -> loop.decision  (supervisor/graph.py:122)
    events.append(LoopEvent("loop.decision", {
        "decision": "delegate",
        "reason": "chia viec cho ca 3",
        "next_agent_calls": [
            {"agent_id": "researcher"}, {"agent_id": "writer"}, {"agent_id": "reviewer"},
        ],
    }, round_no=1))
    # run_round -> 3 x loop.turn  (supervisor/graph.py:209)
    events.append(LoopEvent("loop.turn", {"agent_id": "researcher", "outcome": "thu thap 12 nguon", "role": "research"}, round_no=1))
    events.append(LoopEvent("loop.turn", {"agent_id": "writer", "outcome": "viet 3 doan", "role": "writing"}, round_no=1))
    # run_tool -> loop.tool  (supervisor/graph.py:226)
    events.append(LoopEvent("loop.tool", {"tool": "web.search", "ok": True}))
    events.append(LoopEvent("loop.turn", {"agent_id": "reviewer", "outcome": "duyet, dat", "role": "review"}, round_no=1))
    # finished
    events.append(LoopEvent("loop.finished", {}, round_no=1))
    return events


# =============================================================================
# DEMO
# =============================================================================
def _print_snapshot(snap: TaskLoopSnapshot) -> None:
    print(f"      session={snap.session_id} status={snap.status} round={snap.round_no}")
    print(f"      orchestrator.last_decision={snap.orchestrator['last_decision']!r} reason={snap.orchestrator['reason']!r}")
    for a in snap.agents:
        print(f"        agent {a.agent_id:11s} role={a.role:8s} status={a.status:7s} outcome={a.last_output_summary!r}")
    for t in snap.tool_calls:
        print(f"        tool  {t['tool']:11s} status={t['status']}")


def demo() -> None:
    print("=" * 74)
    print("CASE 02 — EVENT PROJECTION: fold loop.* -> TaskLoopSnapshot (hex_agent E21)")
    print("=" * 74)

    # ---- Bước 1: business logic emit chuỗi event (fact past-tense) ----
    print("\n[1] SUPERVISOR emit chuoi loop.* event (fact, nguon su that):")
    events = fake_supervisor_run()
    for i, ev in enumerate(events, 1):
        print(f"      {i}. {ev.event_type:20s} payload={ev.payload}")

    # ---- Bước 2: fold thành snapshot (read model UI render) ----
    print("\n[2] build_snapshot() fold chuoi event -> read model (UI render cai nay):")
    snap = build_snapshot(events, session_id="sess-42")
    _print_snapshot(snap)
    print("    -> Researcher/Writer/Reviewer deu 'done' (da co loop.turn); status=finished.")

    # ---- Bước 3: projection là HÀM THUẦN — fold dở chừng cho status khác ----
    print("\n[3] Projection la HAM THUAN cua chuoi event. Fold do chung (truoc cac turn):")
    partial = events[:2]  # mới team_composed + decision, chưa agent nào chạy
    snap_partial = build_snapshot(partial, session_id="sess-42")
    _print_snapshot(snap_partial)
    print("    -> Luc nay ca 3 agent 'running' (nam trong decision, chua co turn). Khong he sai state —")
    print("       chi la projection cua MOT TIEN TO khac cua cung chuoi event.")

    # ---- Bước 4: ĐỐI CHỨNG — khi UI tự nuôi state thay vì projection ----
    print("\n[4] DOI CHUNG: neu UI tu nuoi mutable state (KHONG dung projection):")
    print("    Gia su 1 su kien loop.turn cua 'writer' bi GIAO LAI lan 2 (at-least-once delivery).")
    events_dup = events + [LoopEvent("loop.turn", {"agent_id": "writer", "outcome": "viet 3 doan"}, round_no=1)]
    # Cách SAI: nuôi 1 bộ đếm mutable -> double count.
    naive_turn_count: dict[str, int] = {}
    for ev in events_dup:
        if ev.event_type == "loop.turn":
            aid = ev.payload["agent_id"]
            naive_turn_count[aid] = naive_turn_count.get(aid, 0) + 1
    print(f"      [SAI] dem turn kieu mutable -> writer={naive_turn_count['writer']} (double count!)")
    # Cách ĐÚNG: projection idempotent theo agent_id (set 'turned') -> writer vẫn 1 trạng thái done.
    snap_dup = build_snapshot(events_dup, session_id="sess-42")
    writer_view = next(a for a in snap_dup.agents if a.agent_id == "writer")
    print(f"      [DUNG] projection idempotent -> writer.status={writer_view.status} (van 'done', khong nhan doi)")

    # ---- Bước 5: asserts chứng minh bất biến của event sourcing ----
    print("\n[5] ASSERT — bat bien cua event sourcing")

    # (i) DETERMINISTIC: replay cùng chuỗi event -> cùng snapshot (so sánh as_dict)
    snap_again = build_snapshot(fake_supervisor_run(), session_id="sess-42")
    assert snap.as_dict() == snap_again.as_dict(), "replay cung event phai cho cung snapshot"
    print("      (i) replay CUNG chuoi event -> CUNG snapshot (deterministic)  -> OK")

    # (ii) IDEMPOTENT trước duplicate delivery: snapshot không đổi vì 1 turn lặp lại
    assert snap.as_dict() == snap_dup.as_dict(), "duplicate loop.turn khong duoc lam doi snapshot"
    print("      (ii) duplicate loop.turn KHONG lam doi snapshot (idempotent)  -> OK")

    # (iii) MONOTONIC: fold của prefix dài hơn không 'mất' agent đã thấy
    assert {a.agent_id for a in snap_partial.agents} <= {a.agent_id for a in snap.agents}, \
        "agent da xuat hien khong duoc bien mat khi fold them event"
    print("      (iii) tap agent chi lon dan khi fold them event (monotonic)  -> OK")

    # (iv) terminal status không bị marker sau ghi đè
    assert snap.status == "finished", f"status phai 'finished', gap {snap.status}"
    print("      (iv) terminal status 'finished' khong bi marker sau ghi de  -> OK")

    print("\n" + "=" * 74)
    print("KET LUAN: Event la nguon su that; TaskLoopSnapshot chi la PROJECTION (ham thuan).")
    print("UI render snapshot, khong mutate state -> tu dong dung voi mat-tin-cay + replay.")
    print("=" * 74)


if __name__ == "__main__":
    demo()
