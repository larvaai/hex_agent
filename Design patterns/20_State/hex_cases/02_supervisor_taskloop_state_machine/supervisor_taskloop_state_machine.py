"""
State Pattern — Case 02: Supervisor TaskLoop (enum status + transitions).

Bản DISTILL TRUNG THỰC từ hex_agent. Nguồn thật:
  - supervisor/state.py:14-25   — TaskLoopStatus(str, Enum) 8 state:
                                  CREATED, TEAM_SELECTED, IN_DISCUSSION, WAITING_TOOL,
                                  REVIEWING_AC, FINISHED, BLOCKED, FAILED.
                                  TERMINAL = {FINISHED, BLOCKED, FAILED} — không có lối ra.
  - supervisor/state.py:84      — TaskLoopState.status giữ state hiện tại.
  - supervisor/state.py:105-107 — is_terminal: TaskLoopStatus(status) ∈ TERMINAL.
  - supervisor/state.py:109-111 — acceptance_snapshot(): snapshot tiến độ cho loop guard.
  - supervisor/graph.py:102     — compose_team() -> TEAM_SELECTED.
  - supervisor/graph.py:211     — run_round()   -> IN_DISCUSSION.
  - supervisor/graph.py:227     — run_tool()    -> WAITING_TOOL.
  - supervisor/graph.py:256     — judge_acceptance() -> REVIEWING_AC.
  - supervisor/loop.py:154-201  — _drive(): Context orchestrator. while not is_terminal,
                                  route decision.decision tới handler đúng (run_round/
                                  run_tool/judge_acceptance) -> handler đổi status.
  - supervisor/loop.py:204-208  — _terminate(): set status terminal + lý do.

Pattern: State (Behavioral).
  - Context: TaskLoopState (mang status hiện tại + blackboard: artifacts/turns/AC).
  - State: TaskLoopStatus enum (8 state) + subset TERMINAL (không transition ra).
  - Transition: context-driven trong _drive(): decision.decision quyết nhánh; mỗi handler
    set state.status + tăng round_no. Guard: is_terminal, max_rounds, repeat_count, progress.

CHỈ dùng thư viện chuẩn Python 3.14. KHÔNG import hex_agent / bên thứ ba.
Hạ tầng nặng bị thay:
  - Orchestrator (LLM O) -> ScriptedOrchestrator (hàng đợi quyết định cố định).
  - DelegationManager / Broker / KernelSession -> bỏ; handler chỉ thêm artifact giả.
  - SQLite checkpoint -> bỏ (giữ state trong RAM).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ── State interface: enum 8 trạng thái (distill state.py:14-25) ──────────────
class TaskLoopStatus(str, Enum):
    CREATED = "created"
    TEAM_SELECTED = "team_selected"
    IN_DISCUSSION = "in_discussion"
    WAITING_TOOL = "waiting_tool"
    REVIEWING_AC = "reviewing_ac"
    FINISHED = "finished"
    BLOCKED = "blocked"
    FAILED = "failed"


# State cuối: vào là không ra (state.py:25).
TERMINAL = {TaskLoopStatus.FINISHED, TaskLoopStatus.BLOCKED, TaskLoopStatus.FAILED}


@dataclass
class AcceptanceCheck:
    """Một tiêu chí chấp nhận (state.py:28-37)."""

    id: str
    text: str
    status: str = "pending"            # pending | passed | failed
    evidence_ids: list[str] = field(default_factory=list)

    @property
    def is_satisfied(self) -> bool:
        return self.status == "passed" and bool(self.evidence_ids)


# ── Context: TaskLoopState (distill state.py:80-111) ─────────────────────────
@dataclass
class TaskLoopState:
    task_id: str
    status: str = TaskLoopStatus.CREATED.value
    selected_agents: list[str] = field(default_factory=list)
    acceptance_checks: list[AcceptanceCheck] = field(default_factory=list)
    round_no: int = 0
    max_rounds: int = 5
    artifacts: dict[str, dict] = field(default_factory=dict)
    reason: str = ""

    def add_artifact(self, artifact_id: str, payload: dict) -> None:
        self.artifacts[artifact_id] = payload

    def acceptance_by_id(self, check_id: str) -> AcceptanceCheck | None:
        return next((c for c in self.acceptance_checks if c.id == check_id), None)

    def all_accepted(self) -> bool:
        return bool(self.acceptance_checks) and all(c.is_satisfied for c in self.acceptance_checks)

    @property
    def is_terminal(self) -> bool:
        """Guard chính của vòng lặp (state.py:105-107)."""
        return TaskLoopStatus(self.status) in TERMINAL

    def acceptance_snapshot(self) -> tuple[tuple[str, str, int], ...]:
        """Snapshot tiến độ AC, dùng để phát hiện 'không tiến triển' (state.py:109-111)."""
        return tuple((c.id, c.status, len(c.evidence_ids)) for c in self.acceptance_checks)


# ── Decision (distill supervisor/contracts.py OrchestratorDecision) ───────────
@dataclass
class Decision:
    decision: str                                  # continue | need_tool | finished | blocked | failed
    acceptance_status: list[dict] = field(default_factory=list)
    reason: str = ""


class ScriptedOrchestrator:
    """Thay LLM O: trả compose cố định + hàng đợi decision (giống ScriptedOrchestrator ở
    supervisor/orchestrator.py:21-39)."""

    def __init__(self, team: list[str], decisions: list[Decision]) -> None:
        self._team = team
        self._decisions = list(decisions)

    def compose_team(self) -> list[str]:
        return list(self._team)

    def decide(self) -> Decision:
        if self._decisions:
            return self._decisions.pop(0)
        return Decision("blocked", reason="orchestrator script exhausted")


# ── Handlers: mỗi handler đổi state.status (distill graph.py) ─────────────────
def compose_team(state: TaskLoopState, o: ScriptedOrchestrator) -> None:
    state.selected_agents = o.compose_team()
    state.add_artifact("session_plan", {"kind": "session_plan", "agents": list(state.selected_agents)})
    state.status = TaskLoopStatus.TEAM_SELECTED.value      # graph.py:102
    print(f"    compose_team -> {state.status} (team={state.selected_agents})")


def run_round(state: TaskLoopState, decision: Decision) -> None:
    """Mỗi agent làm một lượt, thêm artifact vào blackboard (graph.py:137-211)."""
    for agent in state.selected_agents:
        aid = f"art_{agent}_{state.round_no}"
        state.add_artifact(aid, {"kind": "delegation_result", "agent_id": agent, "evidence": True})
    state.status = TaskLoopStatus.IN_DISCUSSION.value      # graph.py:211
    print(f"    run_round -> {state.status} (+{len(state.selected_agents)} artifacts)")


def run_tool(state: TaskLoopState, decision: Decision) -> None:
    aid = f"tool_{state.round_no}"
    state.add_artifact(aid, {"kind": "tool_result", "ok": True})
    state.status = TaskLoopStatus.WAITING_TOOL.value       # graph.py:227
    print(f"    run_tool -> {state.status}")


def judge_acceptance(state: TaskLoopState, decision: Decision) -> None:
    """Áp report AC của O; 'passed' chỉ được chấp nếu evidence resolve trên blackboard
    (graph.py:231-256)."""
    for row in decision.acceptance_status:
        check = state.acceptance_by_id(str(row.get("id", "")))
        if check is None:
            continue
        claimed = str(row.get("status", "pending"))
        evidence = [str(e) for e in (row.get("evidence_ids") or [])]
        if claimed == "passed" and evidence and all(e in state.artifacts for e in evidence):
            check.status = "passed"
            check.evidence_ids = evidence
        elif claimed == "failed":
            check.status = "failed"
            check.evidence_ids = evidence
        else:
            check.status = "pending"
    state.status = TaskLoopStatus.REVIEWING_AC.value       # graph.py:256
    print(f"    judge_acceptance -> {state.status} (accepted_all={state.all_accepted()})")


def _terminate(state: TaskLoopState, status: TaskLoopStatus, reason: str) -> None:
    """Set state terminal (loop.py:204-208)."""
    state.status = status.value
    state.reason = reason
    print(f"    _terminate -> {state.status} ({reason})")


# ── Context orchestrator: _drive (distill loop.py:148-201) ───────────────────
def drive(state: TaskLoopState, o: ScriptedOrchestrator, *, max_decision_repeats: int = 3) -> dict:
    last_signature: str | None = None
    repeat_count = 0
    transitions: list[str] = []

    while not state.is_terminal:                            # guard: chỉ chạy khi chưa terminal
        prev = state.status
        if state.round_no >= state.max_rounds:              # guard: max_rounds (loop.py:155)
            _terminate(state, TaskLoopStatus.BLOCKED, "max_rounds reached")
            break

        before_artifacts = len(state.artifacts)
        before_acceptance = state.acceptance_snapshot()

        decision = o.decide()
        signature = decision.decision
        repeat_count = repeat_count + 1 if signature == last_signature else 0
        last_signature = signature

        # ── route theo decision -> handler -> handler đổi status ──
        if decision.decision == "finished":
            judge_acceptance(state, decision)
            if state.all_accepted():
                _terminate(state, TaskLoopStatus.FINISHED, decision.reason or "all criteria passed")
                transitions.append(f"{prev} -> {state.status}")
                break
            state.reason = "finish denied: acceptance criteria incomplete"
        elif decision.decision == "need_tool":
            run_tool(state, decision)
            judge_acceptance(state, decision)
        elif decision.decision == "continue":
            run_round(state, decision)
            judge_acceptance(state, decision)
        elif decision.decision in {"blocked", "failed"}:
            status = TaskLoopStatus.BLOCKED if decision.decision == "blocked" else TaskLoopStatus.FAILED
            _terminate(state, status, decision.reason or decision.decision)
            transitions.append(f"{prev} -> {state.status}")
            break

        state.round_no += 1
        transitions.append(f"{prev} -> {state.status}")

        # guard: không tiến triển -> block (loop.py:193-196)
        progressed = len(state.artifacts) > before_artifacts or state.acceptance_snapshot() != before_acceptance
        if not progressed:
            _terminate(state, TaskLoopStatus.BLOCKED, "no progress this round")
            transitions.append(f"{state.status}")
            break
        # guard: O lặp lại y hệt quá nhiều lần (loop.py:197-199)
        if repeat_count >= max_decision_repeats:
            _terminate(state, TaskLoopStatus.BLOCKED, "orchestrator repeated the same decision")
            transitions.append(f"{state.status}")
            break

    return {
        "status": state.status,
        "rounds": state.round_no,
        "reason": state.reason,
        "transitions": transitions,
    }


# ── Demo ──────────────────────────────────────────────────────────────────────
def demo() -> None:
    print("=" * 70)
    print("CASE 02 — Supervisor TaskLoop: enum status + context-driven transitions")
    print("=" * 70)

    # ── Kịch bản 1: HAPPY PATH -> FINISHED ──
    print("\n--- Kịch bản 1: continue -> finished (mọi AC pass) ---")
    state = TaskLoopState(task_id="T1", max_rounds=5)
    state.acceptance_checks = [AcceptanceCheck(id="ac1", text="tài liệu sẵn sàng")]
    o = ScriptedOrchestrator(
        team=["writer", "reviewer"],
        decisions=[
            Decision("continue"),
            # vòng kết: O báo finished + evidence trỏ tới artifact THẬT trên blackboard.
            # run_round ở vòng 0 tạo "art_writer_0" (đặt tên theo round_no lúc chạy = 0).
            Decision("finished", acceptance_status=[{"id": "ac1", "status": "passed",
                                                      "evidence_ids": ["art_writer_0"]}]),
        ],
    )
    print(f"  init: status={state.status}")
    compose_team(state, o)
    print(f"  after compose: status={state.status}")
    result = drive(state, o)
    print(f"\n  Chuỗi transition: {' | '.join(result['transitions'])}")
    print(f"  Kết quả: {result['status']} sau {result['rounds']} vòng — {result['reason']}")

    assert result["status"] == TaskLoopStatus.FINISHED.value
    assert TaskLoopStatus(result["status"]) in TERMINAL
    assert state.all_accepted(), "mọi AC phải pass khi FINISHED"
    print("  [assert] OK: CREATED->TEAM_SELECTED->IN_DISCUSSION->REVIEWING_AC->FINISHED.")

    # ── Kịch bản 2: GUARD max_rounds -> BLOCKED ──
    print("\n--- Kịch bản 2: O cứ 'continue' mãi -> max_rounds guard -> BLOCKED ---")
    state2 = TaskLoopState(task_id="T2", max_rounds=3)
    state2.acceptance_checks = [AcceptanceCheck(id="ac1", text="không bao giờ pass")]
    o2 = ScriptedOrchestrator(team=["w"], decisions=[Decision("continue")] * 10)
    compose_team(state2, o2)
    result2 = drive(state2, o2)
    print(f"  Kết quả: {result2['status']} sau {result2['rounds']} vòng — {result2['reason']}")
    assert result2["status"] == TaskLoopStatus.BLOCKED.value
    assert result2["rounds"] <= state2.max_rounds
    print("  [assert] OK: guard max_rounds chặn vòng lặp vô hạn (terminal=BLOCKED).")

    # ── Bất biến terminal: vào terminal là không chạy thêm vòng ──
    print("\n--- Bất biến: terminal state không transition ra ---")
    frozen = TaskLoopState(task_id="T3", status=TaskLoopStatus.FINISHED.value)
    assert frozen.is_terminal
    res3 = drive(frozen, ScriptedOrchestrator(team=[], decisions=[Decision("continue")]))
    assert res3["rounds"] == 0, "không vòng nào chạy khi state đã terminal"
    print("  [assert] OK: is_terminal chặn _drive ngay từ đầu (TERMINAL là 'sink').")

    # ── Đối chứng: KHÔNG enum / KHÔNG TERMINAL set ──
    print("\n--- Đối chứng: nếu status là str tự do, không TERMINAL set ---")
    print("  Mỗi nơi phải tự liệt kê {'finished','blocked','failed'} để biết khi nào dừng.")
    print("  Thêm state mới (vd 'paused') -> phải sửa MỌI chỗ kiểm tra terminal -> dễ sót.")
    print("  Enum + TERMINAL gom 'tập state cuối' về MỘT nơi (state.py:25).")

    print("\nKẾT LUẬN: TaskLoopStatus(enum) + TERMINAL + _drive route theo decision =")
    print("State pattern. _drive là Context; handler đổi status; guard chặn transition sai.")


if __name__ == "__main__":
    demo()
