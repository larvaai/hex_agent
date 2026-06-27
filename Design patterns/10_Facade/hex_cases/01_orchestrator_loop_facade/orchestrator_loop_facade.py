"""
Case 01 — Orchestrator Loop Facade: hàm run()/resume() che cả một subsystem chạy graph.

NGUỒN THẬT (đã mở & kiểm chứng trong hex_agent):
  - orchestrator/loop.py:1        -> docstring module: "Public run/resume facade backed by
                                     the single compiled LangGraph." (tên 'facade' ghi rõ).
  - orchestrator/loop.py:93-147   -> def run(): tạo session, build graph (kèm/không checkpoint),
                                     stream tới terminal state, sync budget, trả _outcome().
  - orchestrator/loop.py:217-273  -> def resume(): khôi phục state đã lưu rồi chạy tiếp.
  - orchestrator/loop.py:40-48    -> _config(): tính recursion_limit theo budget.
  - orchestrator/loop.py:51-59    -> _outcome(): chuẩn hoá envelope kết quả.
  - orchestrator/loop.py:62-66    -> _sync_budget(): đồng bộ budget từ state đã persist.
  - orchestrator/loop.py:69-90    -> _stream(): chạy graph, lưu projection từng bước.
  - graph/runtime.py:31-66        -> build_agent_graph(): builder dựng StateGraph 6 node
                                     (guard, agent, tool, delegate, finish, fail) + routing.
  - core/session.py               -> SessionFactory / KernelSession (per-run isolation).
  - orchestrator/checkpoint.py    -> open_checkpointer() (persist/resume state).
  - discipline.Budget             -> Budget (giới hạn steps/parse_errors/tool_calls).

VAI TRÒ FACADE Ở ĐÂY:
  Facade        = hàm run() / resume() (STATELESS facade — là hàm, không phải class).
  Subsystem 1   = AgentKernel (registry năng lực + event bus, dùng chung, đóng băng).
  Subsystem 2   = SessionFactory / KernelSession (tạo & cô lập state mỗi lần chạy).
  Subsystem 3   = build_agent_graph() (biên dịch graph nhiều node + định tuyến).
  Subsystem 4   = Checkpointer (lưu & nạp lại state để resume).
  Subsystem 5   = Budget (đếm/giới hạn step, parse error, tool call).
  Client        = chỉ gọi run(kernel, prompt) — KHÔNG import session/graph/checkpoint.

Bản distill này thay LangGraph/LLM/SQLite-checkpoint thật bằng fake tối thiểu bằng
stdlib, nhưng GIỮ NGUYÊN choreography: session -> build graph -> stream -> sync budget
-> outcome, và đường resume nạp lại state từ checkpoint rồi chạy tiếp.

Chỉ dùng thư viện chuẩn Python. KHÔNG import hex_agent, KHÔNG bên thứ ba.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

# ──────────────────────────────────────────────────────────────────────────────
# SUBSYSTEM 5 — Budget (discipline.Budget thật)
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class Budget:
    """Giới hạn run. Distill của discipline.Budget (max_steps/max_parse_errors)."""

    max_steps: int = 6
    steps: int = 0

    def tick(self) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise RuntimeError("Budget exhausted: vượt max_steps.")


# ──────────────────────────────────────────────────────────────────────────────
# SUBSYSTEM 1 — AgentKernel (core.kernel.AgentKernel thật)
# ──────────────────────────────────────────────────────────────────────────────


class EventBus:
    def __init__(self) -> None:
        self.log: list[tuple[str, dict]] = []

    def publish(self, topic: str, fields: dict) -> None:
        self.log.append((topic, fields))


class AgentKernel:
    """Năng lực dùng chung, đóng băng giữa các run. (core.kernel.AgentKernel)"""

    def __init__(self, tools: dict[str, Callable[[dict], str]]) -> None:
        self.tools = dict(tools)
        self.events = EventBus()


# ──────────────────────────────────────────────────────────────────────────────
# SUBSYSTEM 2 — Session (core.session.KernelSession / SessionFactory thật)
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class KernelSession:
    kernel: AgentKernel
    run_id: str
    user_request: str
    state: dict[str, Any] = field(default_factory=dict)


class SessionFactory:
    """create_root() / restore() — cô lập state cho mỗi run. (core.session)"""

    def __init__(self, kernel: AgentKernel) -> None:
        self.kernel = kernel

    def create_root(self, user_request: str, run_id: str | None = None) -> KernelSession:
        rid = run_id or uuid.uuid4().hex[:8]
        return KernelSession(kernel=self.kernel, run_id=rid, user_request=user_request)

    def restore(self, run_id: str, state: dict[str, Any]) -> KernelSession:
        sess = KernelSession(
            kernel=self.kernel,
            run_id=run_id,
            user_request=state.get("user_request", ""),
        )
        sess.state = dict(state)
        return sess


# ──────────────────────────────────────────────────────────────────────────────
# SUBSYSTEM 3 — Graph (graph/runtime.build_agent_graph thật)
# ──────────────────────────────────────────────────────────────────────────────


class CompiledGraph:
    """
    Distill của LangGraph đã biên dịch. Các node thật là guard/agent/tool/finish/fail.
    Ở đây mô phỏng vòng lặp agent: mỗi step gọi 'agent' quyết định tool hay final,
    rồi 'tool' chạy, tới khi 'final'. Hỗ trợ resume từ state dở dang.
    """

    def __init__(self, session: KernelSession, checkpointer: "Checkpointer | None") -> None:
        self._session = session
        self._checkpointer = checkpointer
        # "Kịch bản" agent đã định sẵn để demo có tính xác định.
        self._plan: list[tuple[str, str]] = [
            ("tool", "search"),
            ("tool", "read"),
            ("final", "Đã tổng hợp xong câu trả lời."),
        ]

    def stream(self, graph_input: dict[str, Any] | None, budget: Budget) -> Iterator[dict[str, Any]]:
        kernel = self._session.kernel
        state = dict(graph_input) if graph_input else dict(self._session.state)
        cursor = int(state.get("cursor", 0))
        state.setdefault("status", "running")
        state.setdefault("transcript", [])
        while cursor < len(self._plan):
            budget.tick()  # node "guard" thật: chặn khi vượt budget
            action, payload = self._plan[cursor]
            if action == "tool":
                result = kernel.tools[payload]({"q": self._session.user_request})
                state["transcript"] = state["transcript"] + [f"{payload} -> {result}"]
                kernel.events.publish("tool.done", {"run_id": self._session.run_id, "tool": payload})
            else:  # final
                state["status"] = "completed"
                state["final"] = payload
            cursor += 1
            state["cursor"] = cursor
            if self._checkpointer is not None:
                self._checkpointer.save(self._session.run_id, dict(state))
            yield dict(state)


def build_agent_graph(
    *, session: KernelSession, checkpointer: "Checkpointer | None" = None
) -> CompiledGraph:
    """graph/runtime.py:31 — Build the sole orchestration graph around an isolated session."""
    return CompiledGraph(session, checkpointer)


# ──────────────────────────────────────────────────────────────────────────────
# SUBSYSTEM 4 — Checkpointer (orchestrator/checkpoint.py thật)
# ──────────────────────────────────────────────────────────────────────────────


class Checkpointer:
    """open_checkpointer()/save_graph_projection() — distill bằng dict in-memory."""

    def __init__(self) -> None:
        self._db: dict[str, dict[str, Any]] = {}

    def save(self, run_id: str, state: dict[str, Any]) -> None:
        self._db[run_id] = dict(state)

    def get(self, run_id: str) -> dict[str, Any] | None:
        snap = self._db.get(run_id)
        return dict(snap) if snap is not None else None

    def exists(self, run_id: str) -> bool:
        return run_id in self._db


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS NỘI BỘ của facade (orchestrator/loop.py:40-90 thật)
# ──────────────────────────────────────────────────────────────────────────────


def _outcome(state: dict[str, Any]) -> dict[str, Any]:
    """orchestrator/loop.py:51 — chuẩn hoá envelope kết quả."""
    return {
        "run_id": state.get("run_id"),
        "status": state.get("status", "incomplete"),
        "result": state.get("final"),
        "steps": state.get("cursor", 0),
    }


def _stream(graph: CompiledGraph, graph_input: dict[str, Any] | None, budget: Budget) -> dict[str, Any]:
    """orchestrator/loop.py:69 — chạy graph, giữ state cuối cùng."""
    final_state: dict[str, Any] = dict(graph_input) if graph_input else {}
    for values in graph.stream(graph_input, budget):
        final_state = values
    return final_state


# ──────────────────────────────────────────────────────────────────────────────
# FACADE — run() / resume() (orchestrator/loop.py:93 và :217 thật)
# ──────────────────────────────────────────────────────────────────────────────


def run(
    kernel: AgentKernel,
    user_request: str,
    *,
    budget: Budget | None = None,
    run_id: str | None = None,
    checkpoint: bool = True,
    checkpointer: Checkpointer | None = None,
) -> dict[str, Any]:
    """
    FACADE: 1 lời gọi -> điều phối toàn bộ subsystem (orchestrator/loop.py:93).
    Bên trong: tạo session -> build graph (kèm/không checkpoint) -> stream tới
    terminal -> trả outcome. Client KHÔNG cần biết tới session/graph/checkpoint.
    """
    active_budget = budget or Budget()
    session = SessionFactory(kernel=kernel).create_root(user_request, run_id=run_id)
    session.state["run_id"] = session.run_id
    session.state["user_request"] = user_request

    if not checkpoint:
        graph = build_agent_graph(session=session)
        initial = {"run_id": session.run_id, "user_request": user_request, "cursor": 0}
        state = _stream(graph, initial, active_budget)
        return _outcome(state)

    saver = checkpointer or Checkpointer()
    graph = build_agent_graph(session=session, checkpointer=saver)
    initial = {"run_id": session.run_id, "user_request": user_request, "cursor": 0}
    state = _stream(graph, initial, active_budget)
    return _outcome(state)


def resume(
    kernel: AgentKernel,
    run_id: str,
    *,
    checkpointer: Checkpointer,
    budget: Budget | None = None,
) -> dict[str, Any]:
    """
    FACADE: tiếp tục một run dở dang (orchestrator/loop.py:217).
    Bên trong: đọc checkpoint -> khôi phục session -> build graph -> stream tiếp.
    """
    persisted = checkpointer.get(run_id)
    if persisted is None:
        raise FileNotFoundError(f"No checkpoint for run_id={run_id!r}")
    if persisted.get("status") != "running":
        return _outcome(persisted)  # đã xong từ trước, không chạy lại

    session = SessionFactory(kernel=kernel).restore(run_id, persisted)
    graph = build_agent_graph(session=session, checkpointer=checkpointer)
    state = _stream(graph, persisted, budget or Budget())
    return _outcome(state)


# ──────────────────────────────────────────────────────────────────────────────
# ĐỐI CHỨNG — client KHÔNG có facade phải tự lắp ráp mọi subsystem
# ──────────────────────────────────────────────────────────────────────────────


def run_without_facade(
    kernel: AgentKernel, user_request: str, *, run_id: str | None = None
) -> dict[str, Any]:
    """
    'Ngây thơ': client tự làm hết — biết tên SessionFactory, build_agent_graph,
    Checkpointer, Budget, _stream, _outcome, và đúng thứ tự. Mỗi nơi gọi lặp lại
    choreography này; đổi 1 subsystem là sửa MỌI client.
    """
    budget = Budget()
    factory = SessionFactory(kernel=kernel)            # phải biết SessionFactory
    session = factory.create_root(user_request, run_id=run_id)
    session.state["run_id"] = session.run_id
    session.state["user_request"] = user_request
    saver = Checkpointer()                              # phải biết Checkpointer
    graph = build_agent_graph(session=session, checkpointer=saver)  # phải biết builder
    initial = {"run_id": session.run_id, "user_request": user_request, "cursor": 0}
    final_state: dict[str, Any] = initial
    for values in graph.stream(initial, budget):       # phải tự stream
        final_state = values
    # phải tự chuẩn hoá envelope, dễ lệch shape giữa các client
    return {
        "run_id": final_state.get("run_id"),
        "status": final_state.get("status"),
        "result": final_state.get("final"),
        "steps": final_state.get("cursor"),
    }


# ──────────────────────────────────────────────────────────────────────────────
# DEMO
# ──────────────────────────────────────────────────────────────────────────────


def _make_kernel() -> AgentKernel:
    return AgentKernel(
        tools={
            "search": lambda args: f"hits(3) cho {args['q']!r}",
            "read": lambda args: "đọc tài liệu top-1",
        }
    )


def demo() -> None:
    print("=" * 72)
    print("CASE 01 — Orchestrator Loop Facade (run/resume)")
    print("=" * 72)

    kernel = _make_kernel()

    print("\n[1] DÙNG FACADE: client chỉ gọi run(kernel, prompt).")
    outcome = run(kernel, "Tóm tắt báo cáo Q2", checkpoint=False)
    print("    outcome =", outcome)
    assert outcome["status"] == "completed"
    assert outcome["result"] == "Đã tổng hợp xong câu trả lời."
    assert outcome["steps"] == 3, "phải đi đủ 3 node theo kịch bản"
    print("    -> Client KHÔNG hề import SessionFactory/build_agent_graph/Checkpointer.")

    print("\n[2] ĐỐI CHỨNG: client tự lắp ráp (run_without_facade).")
    naive = run_without_facade(kernel, "Tóm tắt báo cáo Q2")
    print("    outcome =", naive)
    assert naive["status"] == "completed" and naive["result"] == outcome["result"]
    print("    -> Cùng kết quả, nhưng client phải biết 5 subsystem & đúng thứ tự.")
    print("       Đổi 1 subsystem = sửa mọi client kiểu này.")

    print("\n[3] FACADE absorb checkpoint + RESUME giữa chừng.")
    saver = Checkpointer()
    # Budget cố tình nhỏ để run() dừng dở dang ở node thứ 2.
    small = Budget(max_steps=2)
    try:
        run(kernel, "Phân tích dữ liệu", run_id="job-7", checkpointer=saver, budget=small)
        raise AssertionError("đáng lẽ phải hết budget")
    except RuntimeError as exc:
        print("    run() dừng vì:", exc)
    snap = saver.get("job-7")
    assert snap is not None and snap["status"] == "running", "checkpoint phải còn dở dang"
    print("    checkpoint job-7 còn dở: cursor =", snap["cursor"], ", status =", snap["status"])

    print("    -> Gọi resume(kernel, 'job-7'): facade nạp state cũ rồi chạy tiếp.")
    done = resume(kernel, "job-7", checkpointer=saver, budget=Budget(max_steps=6))
    print("    outcome =", done)
    assert done["status"] == "completed"
    assert done["steps"] == 3, "resume phải hoàn tất nốt tới node cuối"
    print("    -> Client gọi resume() y hệt; toàn bộ logic checkpoint nằm trong facade.")

    print("\n[4] Đổi subsystem (checkpoint backend) KHÔNG đụng client.")
    # Hoán đổi checkpointer khác — chữ ký run() không đổi, client như cũ.
    other = Checkpointer()
    out2 = run(kernel, "Việc khác", run_id="job-9", checkpointer=other)
    assert out2["status"] == "completed"
    assert other.exists("job-9") and not saver.exists("job-9")
    print("    -> Thay saver chỉ là tham số nội bộ; client run(kernel, prompt) bất biến.")

    print("\nTẤT CẢ ASSERT QUA. Facade run/resume che trọn subsystem chạy graph.")


if __name__ == "__main__":
    demo()
