"""
Case 02 — SupervisorContext + TaskLoop: Multi-Agent Orchestration Mediator.

Bản DISTILL TRUNG THỰC từ codebase hex_agent. Nguồn thật:
  - supervisor/graph.py:39-80    (SupervisorContext — giữ orchestrator/broker/
                                  delegation_service/checkpoint = ConcreteMediator)
  - supervisor/graph.py:87-104   (compose_team — O chọn team, ghi lên Blackboard)
  - supervisor/graph.py:108-123  (o_decide — O đọc state_view, phát 1 decision)
  - supervisor/graph.py:137-211  (run_round — phân việc qua broker + delegation,
                                  agent ghi artifact/turn lên Blackboard)
  - supervisor/graph.py:231-256  (judge_acceptance — đọc acceptance + artifacts)
  - supervisor/loop.py:71-105    (run_task_loop — facade: compose_team -> _drive)
  - supervisor/loop.py:148-201   (_drive — vòng lặp o_decide -> run_round -> judge)
  - supervisor/state.py:80-111   (TaskLoopState — Blackboard tuần tự hoá được)
  - supervisor/state.py:114-145  (encode/decode — checkpoint & resume)
  - supervisor/orchestrator.py:21-39 (ScriptedOrchestrator — O xác định, canned)
  - supervisor/broker.py:24-55   (DeterministicBroker — shape context, không đổi scope)

Ý tưởng pattern (Mediator):
  Các agent (colleague) KHÔNG bao giờ gọi nhau trực tiếp. Mọi phối hợp đi qua
  supervisor: O (Orchestrator) đọc Blackboard (TaskLoopState) và quyết next_agent
  -> Broker shape context -> DelegationService chạy agent -> agent ghi artifact/turn
  trở lại Blackboard -> Judge đọc Blackboard. N agent -> 1 mediator, không N×N.
  Vì toàn bộ state là TaskLoopState tuần tự hoá được nên có thể checkpoint & resume.

Bản rút gọn này bỏ: LLM, SQLite thật, json-gate/repair, budget, event-envelope,
nhiều status. Giữ ĐÚNG: Blackboard tuần tự hoá, O quyết qua state_view, agent ghi
artifact (không gọi nhau), Broker shape-only (không đổi scope), checkpoint/resume,
và bằng chứng "thêm agent thứ 3 = 0 dòng sửa ở agent cũ".

Chạy: python3 supervisor_taskloop_mediator.py   (exit code 0, không traceback)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable


# ── BLACKBOARD: state tuần tự hoá được (≈ supervisor/state.py:80-111) ──────────
@dataclass
class AgentTurn:
    round_no: int
    agent_id: str
    output_summary: str = ""
    artifact_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"round_no": self.round_no, "agent_id": self.agent_id,
                "output_summary": self.output_summary, "artifact_ids": list(self.artifact_ids)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AgentTurn":
        return cls(int(d["round_no"]), str(d["agent_id"]),
                   str(d.get("output_summary", "")), list(d.get("artifact_ids") or []))


@dataclass
class AcceptanceCheck:
    id: str
    text: str
    status: str = "pending"          # pending | passed | failed
    evidence_ids: list[str] = field(default_factory=list)

    @property
    def is_satisfied(self) -> bool:
        return self.status == "passed" and bool(self.evidence_ids)

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "text": self.text, "status": self.status,
                "evidence_ids": list(self.evidence_ids)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AcceptanceCheck":
        return cls(str(d["id"]), str(d.get("text", "")), str(d.get("status", "pending")),
                   list(d.get("evidence_ids") or []))


TERMINAL = {"finished", "blocked", "failed"}


@dataclass
class TaskLoopState:
    """Blackboard: agent ghi artifact/turn vào đây; mediator đọc & route tiếp.
    Chỉ chứa primitive nên checkpoint được (≈ state.py:80-111)."""
    task_id: str
    status: str = "created"
    selected_agents: list[str] = field(default_factory=list)
    acceptance_checks: list[AcceptanceCheck] = field(default_factory=list)
    round_no: int = 0
    max_rounds: int = 5
    turns: list[AgentTurn] = field(default_factory=list)
    artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    final_output: dict[str, Any] | None = None
    reason: str = ""

    def add_artifact(self, artifact_id: str, payload: dict[str, Any]) -> None:
        self.artifacts[artifact_id] = payload

    def acceptance_by_id(self, check_id: str) -> AcceptanceCheck | None:
        return next((c for c in self.acceptance_checks if c.id == check_id), None)

    def all_accepted(self) -> bool:
        return bool(self.acceptance_checks) and all(c.is_satisfied for c in self.acceptance_checks)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL


def encode_state(s: TaskLoopState) -> dict[str, Any]:
    """≈ state.py:114-128 — snapshot toàn bộ Blackboard ra dict thuần."""
    return {"task_id": s.task_id, "status": s.status, "selected_agents": list(s.selected_agents),
            "acceptance_checks": [c.as_dict() for c in s.acceptance_checks],
            "round_no": s.round_no, "max_rounds": s.max_rounds,
            "turns": [t.as_dict() for t in s.turns],
            "artifacts": {k: dict(v) for k, v in s.artifacts.items()},
            "final_output": dict(s.final_output) if s.final_output else None, "reason": s.reason}


def decode_state(d: dict[str, Any]) -> TaskLoopState:
    """≈ state.py:131-145 — dựng lại Blackboard từ checkpoint."""
    return TaskLoopState(
        task_id=str(d["task_id"]), status=str(d.get("status", "created")),
        selected_agents=list(d.get("selected_agents") or []),
        acceptance_checks=[AcceptanceCheck.from_dict(c) for c in d.get("acceptance_checks") or []],
        round_no=int(d.get("round_no", 0)), max_rounds=int(d.get("max_rounds", 5)),
        turns=[AgentTurn.from_dict(t) for t in d.get("turns") or []],
        artifacts={k: dict(v) for k, v in (d.get("artifacts") or {}).items()},
        final_output=dict(d["final_output"]) if d.get("final_output") else None,
        reason=str(d.get("reason", "")))


# ── COLLEAGUE: Orchestrator (O) — quyết routing, KHÔNG chạy tool/agent ─────────
class ScriptedOrchestrator:
    """O xác định: canned compose + queue decisions (≈ orchestrator.py:21-39).
    O CHỈ đọc state_view rồi phát JSON; nó không gọi agent nào trực tiếp."""
    def __init__(self, *, compose: list[str], decisions: list[str]) -> None:
        self._compose = list(compose)
        self._decisions = list(decisions)

    def compose_team(self, *, task: str) -> str:
        return json.dumps({"selected_agents": [{"agent_id": a} for a in self._compose]})

    def decide(self, *, state_view: dict[str, Any]) -> str:
        if self._decisions:
            return self._decisions.pop(0)
        return json.dumps({"decision": "blocked", "reason": "script exhausted"})


# ── COLLEAGUE: Broker — shape context, KHÔNG được đổi/widen scope ──────────────
class DeterministicBroker:
    """Viết briefing chỉ từ slice được trao, kèm provenance (≈ broker.py:24-55).
    Bất biến S10.14: Broker không có field scope -> không thể widen quyền worker."""
    def write_packet(self, *, agent_id: str, objective: str,
                     store_slice: list[dict[str, Any]]) -> dict[str, Any]:
        source_ids = [str(i["id"]) for i in store_slice if i.get("id")]
        briefing = f"Objective: {objective}\n" + "\n".join(
            f"[{i['id']}] {i.get('text', '')}" for i in store_slice if i.get("id"))
        return {"target_agent_id": agent_id, "objective": objective,
                "briefing": briefing, "source_ids": source_ids}


# ── COLLEAGUE: DelegationService — chạy 1 agent, trả artifact (≈ delegation) ───
# Mỗi "agent" là 1 hàm thuần: nhận packet -> trả (summary, artifacts). Agent
# KHÔNG nhận tham chiếu tới agent khác; chỉ thấy packet do Broker shape.
AgentFn = Callable[[dict[str, Any]], dict[str, Any]]


class DelegationService:
    def __init__(self, agents: dict[str, AgentFn]) -> None:
        self._agents = agents

    def delegate(self, agent_id: str, packet: dict[str, Any]) -> dict[str, Any]:
        fn = self._agents[agent_id]
        return fn(packet)   # agent thực thi cô lập, chỉ thấy packet


# ── CONCRETE MEDIATOR: SupervisorContext (≈ supervisor/graph.py:39-80) ─────────
@dataclass
class SupervisorContext:
    orchestrator: ScriptedOrchestrator
    broker: DeterministicBroker
    delegation_service: DelegationService
    checkpoint: Callable[[TaskLoopState], None] | None = None
    events: list = field(default_factory=list)

    def emit(self, topic: str, payload: dict[str, Any]) -> None:
        self.events.append({"topic": topic, **payload})

    def save(self, state: TaskLoopState) -> None:
        if self.checkpoint is not None:
            self.checkpoint(state)


def _next_id(prefix: str, state: TaskLoopState) -> str:
    return f"{prefix}-{len(state.artifacts):04d}"


# ── NODES: chỉ thao tác trên Blackboard + ctx, không bao giờ agent->agent ──────
def compose_team(state: TaskLoopState, ctx: SupervisorContext, *, task: str) -> None:
    """O chọn team, mediator ghi lên Blackboard (≈ graph.py:87-104)."""
    plan = json.loads(ctx.orchestrator.compose_team(task=task))
    state.selected_agents = [a["agent_id"] for a in plan["selected_agents"]]
    state.add_artifact(_next_id("session_plan", state),
                       {"kind": "session_plan", "selected": list(state.selected_agents)})
    state.status = "team_selected"
    ctx.emit("loop.team_composed", {"selected": list(state.selected_agents)})


def _state_view(state: TaskLoopState) -> dict[str, Any]:
    """O chỉ thấy 1 view của Blackboard, không thấy session thô của worker
    (≈ graph.py:126-133)."""
    return {"round_no": state.round_no, "selected_agents": list(state.selected_agents),
            "acceptance": [c.as_dict() for c in state.acceptance_checks],
            "artifact_ids": list(state.artifacts)}


def o_decide(state: TaskLoopState, ctx: SupervisorContext) -> dict[str, Any]:
    """O đọc state_view -> phát đúng 1 decision (≈ graph.py:108-123)."""
    decision = json.loads(ctx.orchestrator.decide(state_view=_state_view(state)))
    ctx.emit("loop.decision", {"round": state.round_no, "decision": decision["decision"]})
    return decision


def run_round(state: TaskLoopState, ctx: SupervisorContext, decision: dict[str, Any]) -> None:
    """Phân việc cho từng agent đúng 1 lần; gộp kết quả vào Blackboard
    (≈ graph.py:137-211). Agent ghi artifact, KHÔNG gọi agent khác."""
    selected = set(state.selected_agents)
    for call in decision.get("next_agent_calls", []):
        agent_id = call["agent_id"]
        # Authority check: assignment phải nhắm 1 agent đã được compose chọn.
        if agent_id not in selected:
            raise PermissionError(f"Assignment targets unselected agent '{agent_id}'.")

        # Broker shape context từ artifacts hiện có trên Blackboard.
        store_slice = [{"id": k, "text": str(v)} for k, v in state.artifacts.items()]
        packet = ctx.broker.write_packet(
            agent_id=agent_id, objective=call.get("objective", ""), store_slice=store_slice)
        # Bất biến: Broker không được đổi đích turn sang agent khác.
        if packet["target_agent_id"] != agent_id:
            raise PermissionError("Broker packet target does not match assigned agent.")

        # DelegationService chạy agent cô lập; agent trả artifacts.
        result = ctx.delegation_service.delegate(agent_id, packet)
        artifact_ids: list[str] = []
        for art in result.get("artifacts", []):
            aid = art["artifact_id"]
            state.add_artifact(aid, {"kind": art["kind"], "agent_id": agent_id, **art.get("payload", {})})
            artifact_ids.append(aid)
        state.turns.append(AgentTurn(round_no=state.round_no, agent_id=agent_id,
                                     output_summary=result.get("outcome", ""), artifact_ids=artifact_ids))
        ctx.emit("loop.turn", {"agent_id": agent_id, "outcome": result.get("outcome")})
        ctx.save(state)   # checkpoint sau mỗi turn (≈ graph.py:210)
    state.status = "in_discussion"


def judge_acceptance(state: TaskLoopState, ctx: SupervisorContext, decision: dict[str, Any]) -> None:
    """Áp trạng thái acceptance O báo; 'passed' chỉ tính khi evidence_ids đều
    nằm trên Blackboard (≈ graph.py:231-256)."""
    for row in decision.get("acceptance_status", []):
        check = state.acceptance_by_id(str(row.get("id", "")))
        if check is None:
            continue
        claimed = str(row.get("status", "pending"))
        evidence = [str(e) for e in (row.get("evidence_ids") or [])]
        if claimed == "passed" and evidence and all(e in state.artifacts for e in evidence):
            check.status, check.evidence_ids = "passed", evidence
        elif claimed == "failed":
            check.status, check.evidence_ids = "failed", evidence
        else:
            check.status = "pending"
    state.status = "reviewing_ac"


# ── FACADE + DRIVER (≈ loop.py:71-105 / 148-201) ──────────────────────────────
def _terminate(state: TaskLoopState, ctx: SupervisorContext, status: str, reason: str) -> None:
    state.status, state.reason = status, reason
    ctx.emit(f"loop.{status}", {"reason": reason, "rounds": state.round_no})
    ctx.save(state)


def _drive(state: TaskLoopState, ctx: SupervisorContext) -> TaskLoopState:
    """Vòng lặp mediator: o_decide -> run_round -> judge -> guard (≈ loop.py:148-201)."""
    while not state.is_terminal:
        if state.round_no >= state.max_rounds:
            _terminate(state, ctx, "blocked", "max_rounds reached")
            break
        decision = o_decide(state, ctx)
        kind = decision["decision"]
        if kind == "finished":
            judge_acceptance(state, ctx, decision)
            if state.all_accepted():
                state.final_output = decision.get("final_output") or {}
                _terminate(state, ctx, "finished", decision.get("reason", "all criteria passed"))
                break
            state.reason = "finish denied: acceptance incomplete"
        elif kind == "continue":
            run_round(state, ctx, decision)
            judge_acceptance(state, ctx, decision)
        elif kind in {"blocked", "failed"}:
            _terminate(state, ctx, kind, decision.get("reason", kind))
            break
        state.round_no += 1
        ctx.save(state)
    return state


def run_task_loop(task: str, *, acceptance_criteria: list[tuple[str, str]],
                  ctx: SupervisorContext, max_rounds: int = 5) -> TaskLoopState:
    """Facade công khai (≈ loop.py:71-105)."""
    state = TaskLoopState(task_id="task-1", max_rounds=max_rounds)
    state.acceptance_checks = [AcceptanceCheck(id=c, text=t) for c, t in acceptance_criteria]
    compose_team(state, ctx, task=task)
    ctx.save(state)
    return _drive(state, ctx)


def resume_task_loop(checkpoint: dict[str, Any], *, ctx: SupervisorContext) -> TaskLoopState:
    """Khôi phục Blackboard từ checkpoint và chạy tiếp (≈ loop.py:108-145)."""
    state = decode_state(checkpoint)
    if state.is_terminal:
        return state
    return _drive(state, ctx)


# ── AGENT IMPLEMENTATIONS (colleague, cô lập, KHÔNG biết nhau) ─────────────────
def gather_agent(packet: dict[str, Any]) -> dict[str, Any]:
    return {"outcome": "gathered", "artifacts": [
        {"artifact_id": "facts-1", "kind": "evidence", "payload": {"text": "doanh thu Q2 = 120 tỉ"}}]}


def summarize_agent(packet: dict[str, Any]) -> dict[str, Any]:
    # Chỉ thấy briefing (do Broker ráp từ Blackboard). KHÔNG gọi gather_agent.
    grounded = "facts-1" in packet["briefing"]
    return {"outcome": "summarized", "artifacts": [
        {"artifact_id": "summary-1", "kind": "report",
         "payload": {"text": "Tóm tắt: tăng trưởng tốt", "grounded": grounded}}]}


def critic_agent(packet: dict[str, Any]) -> dict[str, Any]:
    # Agent THỨ BA thêm vào sau — agent cũ KHÔNG đổi 1 dòng nào.
    return {"outcome": "reviewed", "artifacts": [
        {"artifact_id": "review-1", "kind": "evidence", "payload": {"text": "Đã kiểm tra, đạt"}}]}


def demo() -> None:
    print("=" * 70)
    print("CASE 02 — SupervisorContext + TaskLoop: Orchestration Mediator")
    print("=" * 70)

    # 1) Hai agent: gather -> summarize. O xác định luồng; agent không gọi nhau.
    agents = {"gather": gather_agent, "summarize": summarize_agent}
    delegation = DelegationService(agents)
    broker = DeterministicBroker()
    orch = ScriptedOrchestrator(
        compose=["gather", "summarize"],
        decisions=[
            # Vòng 1: chạy gather
            json.dumps({"decision": "continue",
                        "next_agent_calls": [{"agent_id": "gather", "objective": "thu thập số liệu"}]}),
            # Vòng 2: chạy summarize (grounded trên facts-1 của gather)
            json.dumps({"decision": "continue",
                        "next_agent_calls": [{"agent_id": "summarize", "objective": "tóm tắt"}]}),
            # Vòng 3: O tuyên bố xong + cung cấp evidence từ Blackboard
            json.dumps({"decision": "finished",
                        "acceptance_status": [{"id": "AC1", "status": "passed",
                                               "evidence_ids": ["summary-1"]}],
                        "final_output": {"report": "summary-1"}, "reason": "đủ tiêu chí"}),
        ])
    ctx = SupervisorContext(orchestrator=orch, broker=broker, delegation_service=delegation)

    print("\n[1] Chạy TaskLoop 2-agent. O quyết -> Broker shape -> Delegation chạy -> agent ghi Blackboard.")
    state = run_task_loop("Báo cáo doanh thu", acceptance_criteria=[("AC1", "Có bản tóm tắt")], ctx=ctx)
    print(f"    -> status cuối: {state.status}, reason: {state.reason}")
    print(f"    -> selected_agents: {state.selected_agents}")
    print(f"    -> turns: {[(t.agent_id, t.output_summary) for t in state.turns]}")
    print(f"    -> artifacts: {sorted(state.artifacts)}")
    assert state.status == "finished"
    assert state.all_accepted()

    print("\n[2] BẤT BIẾN — summarize_agent grounded trên artifact của gather, NHƯNG qua Broker:")
    grounded = state.artifacts["summary-1"]["grounded"]
    print(f"    -> summary grounded trên facts-1 = {grounded} (đi qua briefing, KHÔNG gọi gather trực tiếp)")
    assert grounded is True

    print("\n[3] BẤT BIẾN — không có lời gọi agent->agent. Mọi turn do mediator phân phát:")
    n_turns = len(state.turns)
    print(f"    -> số turn = {n_turns}; mỗi turn 1 agent, do run_round phân, không agent tự spawn agent.")
    assert n_turns == 2

    # 2) Authority check: O cố gọi agent ngoài team -> bị chặn.
    print("\n[4] Authority check — O nhắm agent KHÔNG nằm trong team -> PermissionError:")
    orch_bad = ScriptedOrchestrator(
        compose=["gather"],
        decisions=[json.dumps({"decision": "continue",
                               "next_agent_calls": [{"agent_id": "summarize", "objective": "x"}]})])
    ctx_bad = SupervisorContext(orchestrator=orch_bad, broker=broker, delegation_service=delegation)
    raised = False
    try:
        run_task_loop("x", acceptance_criteria=[("AC1", "y")], ctx=ctx_bad)
    except PermissionError as exc:
        raised = True
        print(f"    -> chặn đúng: {exc}")
    assert raised

    # 3) Checkpoint & resume: tuần tự hoá Blackboard, dựng lại, chạy tiếp.
    print("\n[5] CHECKPOINT & RESUME — vì Blackboard tuần tự hoá, có thể lưu rồi tiếp:")
    saved: list[dict[str, Any]] = []
    # Chạy ngắt: O chỉ phát đúng 1 decision (chạy gather) rồi cạn script -> 'blocked'.
    # Nhưng MỖI turn đã được checkpoint (≈ graph.py:210), nên có 1 snapshot NON-TERMINAL
    # ngay sau khi gather ghi facts-1 vào Blackboard.
    ctx2_stop = SupervisorContext(orchestrator=ScriptedOrchestrator(
        compose=["gather", "summarize"],
        decisions=[json.dumps({"decision": "continue",
                               "next_agent_calls": [{"agent_id": "gather", "objective": "thu thập"}]})]),
        broker=broker, delegation_service=delegation,
        checkpoint=lambda s: saved.append(encode_state(s)))
    partial = run_task_loop("báo cáo", acceptance_criteria=[("AC1", "có tóm tắt")], ctx=ctx2_stop, max_rounds=5)
    print(f"    -> chạy ngắt: status={partial.status}, đã có {len(saved)} checkpoint, "
          f"artifacts={sorted(partial.artifacts)}")
    assert "facts-1" in partial.artifacts  # gather đã chạy & ghi Blackboard
    # Lấy snapshot NON-TERMINAL gần nhất có facts-1 (mô phỏng máy chết giữa run).
    mid_ckpt = next(c for c in reversed(saved)
                    if "facts-1" in c["artifacts"] and c["status"] not in TERMINAL)
    print(f"    -> checkpoint phục hồi: status={mid_ckpt['status']}, round_no={mid_ckpt['round_no']}, "
          f"artifacts={sorted(mid_ckpt['artifacts'])}")

    # Resume từ checkpoint NON-TERMINAL với O đầy đủ phần còn lại -> hoàn tất.
    saved2: list[dict[str, Any]] = []
    ctx_resume = SupervisorContext(
        orchestrator=ScriptedOrchestrator(
            compose=["gather", "summarize"],
            decisions=[
                json.dumps({"decision": "continue",
                            "next_agent_calls": [{"agent_id": "summarize", "objective": "tóm tắt"}]}),
                json.dumps({"decision": "finished",
                            "acceptance_status": [{"id": "AC1", "status": "passed",
                                                   "evidence_ids": ["summary-1"]}],
                            "final_output": {}, "reason": "xong sau resume"}),
            ]),
        broker=broker, delegation_service=delegation,
        checkpoint=lambda s: saved2.append(encode_state(s)))
    resumed = resume_task_loop(mid_ckpt, ctx=ctx_resume)
    print(f"    -> sau resume: status={resumed.status}, reason={resumed.reason}")
    print(f"    -> Blackboard giữ nguyên facts-1 từ trước + thêm summary-1: {sorted(resumed.artifacts)}")
    assert resumed.status == "finished"
    assert "facts-1" in resumed.artifacts and "summary-1" in resumed.artifacts

    # 4) OPEN/CLOSED: thêm agent thứ ba — agent cũ KHÔNG đổi dòng nào.
    print("\n[6] OPEN/CLOSED — thêm agent 'critic' (thứ 3). Code gather/summarize KHÔNG đổi:")
    agents3 = {"gather": gather_agent, "summarize": summarize_agent, "critic": critic_agent}
    orch3 = ScriptedOrchestrator(
        compose=["gather", "summarize", "critic"],
        decisions=[
            json.dumps({"decision": "continue",
                        "next_agent_calls": [{"agent_id": "gather", "objective": "thu thập"}]}),
            json.dumps({"decision": "continue",
                        "next_agent_calls": [{"agent_id": "summarize", "objective": "tóm tắt"}]}),
            json.dumps({"decision": "continue",
                        "next_agent_calls": [{"agent_id": "critic", "objective": "rà soát"}]}),
            json.dumps({"decision": "finished",
                        "acceptance_status": [{"id": "AC1", "status": "passed",
                                               "evidence_ids": ["summary-1", "review-1"]}],
                        "final_output": {}, "reason": "đủ + đã rà soát"}),
        ])
    ctx3 = SupervisorContext(orchestrator=orch3, broker=broker,
                             delegation_service=DelegationService(agents3))
    state3 = run_task_loop("báo cáo có rà soát", acceptance_criteria=[("AC1", "có tóm tắt + rà soát")],
                           ctx=ctx3)
    print(f"    -> status: {state3.status}, agents chạy: {[t.agent_id for t in state3.turns]}")
    print("    -> Chỉ Orchestrator (quyết định) đổi; agent code cũ tái dùng nguyên vẹn.")
    assert state3.status == "finished"
    assert [t.agent_id for t in state3.turns] == ["gather", "summarize", "critic"]

    print("\n[BẤT BIẾN] Agent là colleague cô lập: chỉ thấy packet, ghi artifact vào Blackboard.")
    print("           O đọc state_view & quyết; Broker shape-only; Delegation chạy; Judge đọc.")
    print("           N agent -> 1 mediator (SupervisorContext + TaskLoopState), không N×N.")
    print("           State tuần tự hoá => checkpoint & resume tự nhiên.")
    print("\nTẤT CẢ ASSERT PASS. ✔")


if __name__ == "__main__":
    demo()
