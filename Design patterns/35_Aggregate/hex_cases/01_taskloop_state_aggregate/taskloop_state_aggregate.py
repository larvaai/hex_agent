"""
CASE 01 — TaskLoopState: Aggregate cho một lượt chạy multi-agent.

Bản DISTILL trung thực, CHỈ dùng thư viện chuẩn Python 3.14, KHÔNG import hex_agent.

NGUỒN THẬT đã mở & kiểm chứng (path:line trong /Users/uspro/Desktop/namnson/hex_agent):
  - supervisor/state.py:14-25    TaskLoopStatus (enum trạng thái) + tập TERMINAL
  - supervisor/state.py:28-49    AcceptanceCheck — internal entity (is_satisfied, as_dict/from_dict)
  - supervisor/state.py:52-77    AgentTurn — internal entity (record 1 lượt worker)
  - supervisor/state.py:80-111   TaskLoopState — Aggregate Root:
        * 80-93   private/mutable state (status, acceptance_checks, turns, artifacts...)
        * 96-97   add_artifact()      — public command (Tell-Don't-Ask)
        * 99-100  acceptance_by_id()  — public query lọc internal entity
        * 102-103 all_accepted()      — invariant "tất cả AC phải is_satisfied"
        * 105-107 is_terminal         — query chặn mutation khi đã ở trạng thái cuối
        * 109-111 acceptance_snapshot()— "domain event"/progress snapshot cho loop guard
  - supervisor/state.py:114-145  encode/decode_taskloop_state — biên giới persistence (SQLite/S3)

Trong code thật, TaskLoopState là "Blackboard" tuần-tự-hoá-được cho 1 lần chạy nhiều agent
(round-based). Bản distill này giữ NGUYÊN vai trò pattern, thay hạ tầng checkpoint nặng
(SQLite/S3) bằng round-trip qua dict thuần (encode/decode) trong bộ nhớ.

So với code thật: trong distill này ta SIẾT thêm encapsulation (status/round_no đặt private,
chỉ đổi qua command method advance()/finish()/fail()) để minh hoạ rõ "invariant inside AR".
Code thật của hex_agent dùng @dataclass với field public — đây là điểm bản distill cố ý
làm chặt hơn để dạy nguyên lý (xem README mục 4 & 5).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── Enum trạng thái — máy trạng thái của 1 lượt chạy (state.py:14-25) ─────────────
class TaskLoopStatus(str, Enum):
    CREATED = "created"
    TEAM_SELECTED = "team_selected"
    IN_DISCUSSION = "in_discussion"
    REVIEWING_AC = "reviewing_ac"
    FINISHED = "finished"
    BLOCKED = "blocked"
    FAILED = "failed"


# Trạng thái cuối: vào đây thì không được mutate nữa (state.py:25)
TERMINAL = {TaskLoopStatus.FINISHED, TaskLoopStatus.BLOCKED, TaskLoopStatus.FAILED}

# Các bước hợp lệ của máy trạng thái (distill thêm để enforce invariant rõ ràng).
# Code thật không khoá transition; ở đây ta khoá để dạy "invalid state should be impossible".
_LEGAL_ADVANCE = {
    TaskLoopStatus.CREATED: {TaskLoopStatus.TEAM_SELECTED},
    TaskLoopStatus.TEAM_SELECTED: {TaskLoopStatus.IN_DISCUSSION},
    TaskLoopStatus.IN_DISCUSSION: {TaskLoopStatus.REVIEWING_AC, TaskLoopStatus.IN_DISCUSSION},
    TaskLoopStatus.REVIEWING_AC: {TaskLoopStatus.IN_DISCUSSION, TaskLoopStatus.REVIEWING_AC},
}


# ── Internal entity 1: AcceptanceCheck (state.py:28-49) ───────────────────────────
@dataclass
class AcceptanceCheck:
    """Một tiêu chí nghiệm thu. CHỈ Aggregate Root (TaskLoopState) được sửa.

    Bất biến cục bộ: 'đạt' chỉ khi status == 'passed' VÀ có ít nhất 1 evidence
    (state.py:35-37) — không có bằng chứng thì không thể tính là pass.
    """
    id: str
    text: str
    status: str = "pending"             # pending | passed | failed
    evidence_ids: list[str] = field(default_factory=list)

    @property
    def is_satisfied(self) -> bool:
        return self.status == "passed" and bool(self.evidence_ids)

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "text": self.text, "status": self.status,
                "evidence_ids": list(self.evidence_ids)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AcceptanceCheck":
        return cls(
            id=str(d["id"]),
            text=str(d.get("text", "")),
            status=str(d.get("status", "pending")),
            evidence_ids=list(d.get("evidence_ids") or []),
        )


# ── Internal entity 2: AgentTurn (state.py:52-77) ─────────────────────────────────
@dataclass
class AgentTurn:
    """Một lượt làm việc của 1 worker trong 1 round. AR ghi nhận, ngoài không tạo trực tiếp."""
    round_no: int
    agent_id: str
    output_summary: str = ""
    artifact_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"round_no": self.round_no, "agent_id": self.agent_id,
                "output_summary": self.output_summary, "artifact_ids": list(self.artifact_ids)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AgentTurn":
        return cls(
            round_no=int(d["round_no"]),
            agent_id=str(d["agent_id"]),
            output_summary=str(d.get("output_summary", "")),
            artifact_ids=list(d.get("artifact_ids") or []),
        )


class InvariantError(RuntimeError):
    """Vi phạm bất biến của aggregate — ném ra TRƯỚC khi state bị hỏng."""


# ── AGGREGATE ROOT: TaskLoopState (state.py:80-111) ───────────────────────────────
@dataclass
class TaskLoopState:
    """Consistency boundary của một lượt chạy multi-agent.

    - Sở hữu một cụm AcceptanceCheck + AgentTurn + artifacts (internal entities).
    - Mọi thay đổi đi qua command method, mỗi method tự enforce invariant.
    - is_terminal canh cổng: vào trạng thái cuối thì khoá mutation.
    """
    session_id: str
    task_id: str
    max_rounds: int = 5
    # ↓ state nội bộ, đặt _private để buộc gọi qua method (distill siết chặt hơn code thật)
    _status: TaskLoopStatus = field(default=TaskLoopStatus.CREATED)
    _round_no: int = 0
    _selected_agents: list[str] = field(default_factory=list)
    _acceptance_checks: list[AcceptanceCheck] = field(default_factory=list)
    _turns: list[AgentTurn] = field(default_factory=list)
    _artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    _final_output: dict[str, Any] | None = None
    _reason: str = ""

    # ── query (read-only) ─────────────────────────────────────────────────────────
    @property
    def status(self) -> TaskLoopStatus:
        return self._status

    @property
    def round_no(self) -> int:
        return self._round_no

    @property
    def is_terminal(self) -> bool:
        return self._status in TERMINAL            # state.py:105-107

    def acceptance_by_id(self, check_id: str) -> AcceptanceCheck | None:
        # state.py:99-100 — lọc qua internal collection, không leak danh sách gốc
        return next((c for c in self._acceptance_checks if c.id == check_id), None)

    def all_accepted(self) -> bool:
        # state.py:102-103 — INVARIANT: chỉ True khi có AC và TẤT CẢ đều is_satisfied
        return bool(self._acceptance_checks) and all(
            c.is_satisfied for c in self._acceptance_checks
        )

    def acceptance_snapshot(self) -> tuple[tuple[str, str, int], ...]:
        # state.py:109-111 — snapshot tiến độ để loop guard so sánh (giống "domain event")
        return tuple((c.id, c.status, len(c.evidence_ids)) for c in self._acceptance_checks)

    def turns_count(self) -> int:
        return len(self._turns)

    # ── command (mutation, mỗi method tự gác invariant) ───────────────────────────
    def _guard_not_terminal(self, op: str) -> None:
        if self.is_terminal:
            raise InvariantError(
                f"Không thể {op}: aggregate đã ở trạng thái cuối {self._status.value!r}."
            )

    def select_team(self, agent_ids: list[str]) -> None:
        self._guard_not_terminal("chọn team")
        if not agent_ids:
            raise InvariantError("Team không được rỗng.")
        self._selected_agents = list(agent_ids)
        self._advance(TaskLoopStatus.TEAM_SELECTED)

    def add_acceptance_check(self, check_id: str, text: str) -> None:
        self._guard_not_terminal("thêm acceptance check")
        if self.acceptance_by_id(check_id) is not None:
            raise InvariantError(f"AcceptanceCheck trùng id {check_id!r}.")
        self._acceptance_checks.append(AcceptanceCheck(id=check_id, text=text))

    def pass_check(self, check_id: str, evidence_id: str) -> None:
        """Đánh dấu 1 AC là passed — BẮT BUỘC kèm evidence (giữ invariant is_satisfied)."""
        self._guard_not_terminal("pass check")
        check = self.acceptance_by_id(check_id)
        if check is None:
            raise InvariantError(f"Không có AcceptanceCheck id {check_id!r}.")
        if not evidence_id:
            raise InvariantError("pass_check yêu cầu evidence_id (không có bằng chứng = không pass).")
        check.evidence_ids.append(evidence_id)
        check.status = "passed"

    def add_artifact(self, artifact_id: str, payload: dict[str, Any]) -> None:
        # state.py:96-97 — cổng duy nhất để ghi vào map artifacts
        self._guard_not_terminal("ghi artifact")
        self._artifacts[artifact_id] = dict(payload)

    def record_turn(self, agent_id: str, output_summary: str,
                    artifact_ids: list[str] | None = None) -> AgentTurn:
        """Ghi 1 lượt worker vào round hiện tại; chuyển sang IN_DISCUSSION nếu cần."""
        self._guard_not_terminal("ghi turn")
        if agent_id not in self._selected_agents:
            raise InvariantError(f"Agent {agent_id!r} không thuộc team đã chọn.")
        if self._status == TaskLoopStatus.TEAM_SELECTED:
            self._advance(TaskLoopStatus.IN_DISCUSSION)
        turn = AgentTurn(round_no=self._round_no, agent_id=agent_id,
                         output_summary=output_summary, artifact_ids=list(artifact_ids or []))
        self._turns.append(turn)
        return turn

    def advance_round(self) -> None:
        """Sang round mới. Invariant: không vượt max_rounds."""
        self._guard_not_terminal("sang round")
        if self._round_no + 1 > self.max_rounds:
            raise InvariantError(f"Vượt max_rounds={self.max_rounds}.")
        self._round_no += 1

    def review_acceptance(self) -> None:
        self._guard_not_terminal("review AC")
        self._advance(TaskLoopStatus.REVIEWING_AC)

    def finish(self, final_output: dict[str, Any]) -> None:
        """Kết thúc THÀNH CÔNG — invariant: chỉ finish được khi all_accepted()."""
        self._guard_not_terminal("finish")
        if not self.all_accepted():
            raise InvariantError(
                "Không thể FINISHED khi chưa thoả tất cả acceptance check (all_accepted=False)."
            )
        self._final_output = dict(final_output)
        self._status = TaskLoopStatus.FINISHED

    def fail(self, reason: str) -> None:
        self._guard_not_terminal("fail")
        self._reason = reason
        self._status = TaskLoopStatus.FAILED

    def _advance(self, target: TaskLoopStatus) -> None:
        """Chuyển trạng thái có kiểm tra hợp lệ (distill thêm so với code thật)."""
        legal = _LEGAL_ADVANCE.get(self._status, set())
        if target not in legal:
            raise InvariantError(
                f"Chuyển trạng thái bất hợp lệ {self._status.value!r} -> {target.value!r}."
            )
        self._status = target


# ── biên giới persistence: encode/decode (state.py:114-145) ───────────────────────
def encode_taskloop_state(state: TaskLoopState) -> dict[str, Any]:
    return {
        "session_id": state.session_id,
        "task_id": state.task_id,
        "status": state._status.value,
        "round_no": state._round_no,
        "max_rounds": state.max_rounds,
        "selected_agents": list(state._selected_agents),
        "acceptance_checks": [c.as_dict() for c in state._acceptance_checks],
        "turns": [t.as_dict() for t in state._turns],
        "artifacts": {k: dict(v) for k, v in state._artifacts.items()},
        "final_output": dict(state._final_output) if state._final_output else None,
        "reason": state._reason,
    }


def decode_taskloop_state(data: dict[str, Any]) -> TaskLoopState:
    st = TaskLoopState(
        session_id=str(data["session_id"]),
        task_id=str(data["task_id"]),
        max_rounds=int(data.get("max_rounds", 5)),
    )
    st._status = TaskLoopStatus(str(data.get("status", "created")))
    st._round_no = int(data.get("round_no", 0))
    st._selected_agents = list(data.get("selected_agents") or [])
    st._acceptance_checks = [AcceptanceCheck.from_dict(c) for c in data.get("acceptance_checks") or []]
    st._turns = [AgentTurn.from_dict(t) for t in data.get("turns") or []]
    st._artifacts = {k: dict(v) for k, v in (data.get("artifacts") or {}).items()}
    st._final_output = dict(data["final_output"]) if data.get("final_output") else None
    st._reason = str(data.get("reason", ""))
    return st


# ── ĐỐI CHỨNG: "anemic" — data bag không có ranh giới ─────────────────────────────
class AnemicLoop:
    """Phản ví dụ: state phơi ra public, ai cũng sửa thẳng field => invariant bị bỏ qua.

    Đây là cái aggregate ĐƯỢC SINH RA để chống lại (xem 35_Aggregate.md, Vi phạm A & D).
    """
    def __init__(self) -> None:
        self.status = "created"
        self.acceptance_checks: list[dict[str, Any]] = []
        self.final_output: dict[str, Any] | None = None


def demo() -> None:
    print("=" * 72)
    print("CASE 01 — TaskLoopState aggregate (distill từ supervisor/state.py)")
    print("=" * 72)

    # 1) Tạo aggregate root
    loop = TaskLoopState(session_id="s-1", task_id="t-42", max_rounds=3)
    print(f"[1] Tạo loop: status={loop.status.value}, round={loop.round_no}")
    assert loop.status is TaskLoopStatus.CREATED

    # 2) Chọn team + nạp acceptance checks (qua command method, không sửa field trực tiếp)
    loop.select_team(["agent:builder", "agent:reviewer"])
    loop.add_acceptance_check("AC1", "Code chạy được")
    loop.add_acceptance_check("AC2", "Có test xanh")
    print(f"[2] Chọn team -> status={loop.status.value}; nạp 2 acceptance checks")
    assert loop.status is TaskLoopStatus.TEAM_SELECTED
    assert loop.all_accepted() is False  # chưa AC nào pass

    # 3) Chạy vài round, ghi turn + artifact
    loop.record_turn("agent:builder", "Viết module X", artifact_ids=["a-1"])
    loop.add_artifact("a-1", {"path": "x.py", "kind": "code"})
    print(f"[3] round {loop.round_no}: builder làm việc -> status={loop.status.value}, "
          f"turns={loop.turns_count()}")
    assert loop.status is TaskLoopStatus.IN_DISCUSSION

    # 4) Snapshot tiến độ (như domain event để loop guard so sánh)
    snap_before = loop.acceptance_snapshot()
    print(f"[4] snapshot trước khi pass: {snap_before}")

    # 5) Pass dần từng acceptance check — BẮT BUỘC kèm evidence
    loop.advance_round()
    loop.review_acceptance()
    loop.pass_check("AC1", evidence_id="a-1")
    print(f"[5] pass AC1 (kèm evidence a-1); all_accepted={loop.all_accepted()}")
    assert loop.all_accepted() is False  # AC2 chưa pass

    # 6) INVARIANT: cố finish khi chưa đủ AC -> bị chặn
    try:
        loop.finish({"summary": "done?"})
        raise AssertionError("Đáng lẽ phải bị chặn vì all_accepted=False")
    except InvariantError as e:
        print(f"[6] Bị chặn đúng như mong đợi: {e}")

    # 7) Pass nốt AC2 rồi finish hợp lệ
    loop.pass_check("AC2", evidence_id="a-2")
    assert loop.all_accepted() is True
    loop.finish({"summary": "tất cả AC đã đạt"})
    print(f"[7] finish OK -> status={loop.status.value}, all_accepted={loop.all_accepted()}")
    assert loop.is_terminal is True

    # 8) INVARIANT: vào terminal thì khoá mutation
    try:
        loop.record_turn("agent:builder", "thêm việc sau khi đã xong")
        raise AssertionError("Đáng lẽ phải bị chặn vì đã terminal")
    except InvariantError as e:
        print(f"[8] Terminal khoá mutation đúng như mong đợi: {e}")

    # 9) Persistence round-trip giữ nguyên consistency (encode -> decode)
    blob = encode_taskloop_state(loop)
    restored = decode_taskloop_state(blob)
    assert restored.status is TaskLoopStatus.FINISHED
    assert restored.all_accepted() is True
    assert restored.acceptance_snapshot() == loop.acceptance_snapshot()
    print(f"[9] encode/decode round-trip OK: snapshot khớp = "
          f"{restored.acceptance_snapshot() == loop.acceptance_snapshot()}")

    # 10) ĐỐI CHỨNG anemic: không ranh giới -> invariant bị phá im lặng
    print("-" * 72)
    print("[10] ĐỐI CHỨNG: AnemicLoop (không aggregate root)")
    bad = AnemicLoop()
    bad.status = "finished"          # set thẳng, bỏ qua mọi luật
    bad.final_output = {"summary": "fake"}  # finish dù 0 acceptance check pass
    print(f"     bad.status={bad.status!r} dù acceptance_checks={bad.acceptance_checks} "
          f"(invariant 'all_accepted' BỊ BỎ QUA -> data corruption)")
    assert bad.status == "finished" and bad.acceptance_checks == []

    print("=" * 72)
    print("PASS — mọi invariant của aggregate được giữ; anemic thì hỏng im lặng.")
    print("=" * 72)


if __name__ == "__main__":
    demo()
