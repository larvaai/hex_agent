"""
Case 02 — Graph Node Orchestration: pipeline cố định, mỗi node có handler riêng.

NGUỒN THẬT (distill từ hex_agent):
  - graph/runtime.py:31-66     -> build_agent_graph(): dựng KHUNG cố định
                                  START -> guard -> agent -> {tool|delegate|finish} -> END
                                  qua StateGraph; _route() (runtime.py:27-28) quyết định cạnh.
  - graph/nodes.py:20-37       -> _restore_session / _emit: concrete operations DÙNG CHUNG
                                  cho mọi node.
  - graph/nodes.py:40-48       -> guard_node: kiểm tra budget rồi route.
  - graph/nodes.py:51-103      -> agent_node: gọi LLM, parse 1 action, set route theo verb.
  - graph/nodes.py:106-138     -> tool_node: thực thi tool qua kernel.
  - graph/nodes.py:202-240     -> finish_node: cổng finish + đóng lifecycle.
  - graph/nodes.py:243-255     -> fail_node: đóng run thất bại.

Ý TƯỞNG PATTERN (Template Method ở scale kiến trúc):
  KHUNG (skeleton) = thứ tự topo cố định của các node, do StateGraph "ép" qua các
  cạnh có điều kiện. Mỗi node là MỘT hook hiện thực CÙNG hợp đồng:
        node(state) -> dict update  (luôn có khoá "route")
  Mọi node theo cùng mẫu nội bộ: _restore_session -> xử lý chuyên biệt -> _emit ->
  return update. Phần xử lý chuyên biệt là điểm biến thiên (guard check budget, agent
  gọi LLM, tool chạy request...). _route() đảm bảo THỨ TỰ khung không bao giờ bị phá:
  một node KHÔNG tự gọi node kế — nó chỉ trả "route", còn engine mới là người gọi
  node tiếp theo. Đúng Hollywood principle.

Phiên bản rút gọn này dùng STDLIB thuần. "LangGraph StateGraph" được thay bằng một
MiniStateGraph tự viết (~30 dòng): add_node + add_conditional_edges + compile + run.
"LLM" và "kernel.execute_tool" được thay bằng fake tất định.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


# ─────────────────────────────────────────────────────────────────────────────
# Engine rút gọn — thay cho langgraph.StateGraph (runtime.py import dòng 7-8)
# ─────────────────────────────────────────────────────────────────────────────
END = "__end__"
START = "__start__"

State = dict[str, Any]
NodeFn = Callable[[State], dict[str, Any]]
RouteFn = Callable[[State], str]


class MiniStateGraph:
    """Bản tí hon của StateGraph: giữ node + cạnh có điều kiện, ép thứ tự khi chạy.

    Đây là "skeleton enforcer": node không được tự nhảy sang node khác; nó chỉ
    return một update có khoá 'route', và CHÍNH engine tra bảng cạnh để chọn node
    kế. Subclass/handler không thể reorder khung."""

    def __init__(self) -> None:
        self._nodes: dict[str, NodeFn] = {}
        self._edges: dict[str, Any] = {}          # name -> next_name (cạnh thẳng)
        self._cond: dict[str, tuple[RouteFn, dict[str, str]]] = {}
        self._entry: str | None = None

    def add_node(self, name: str, fn: NodeFn) -> None:
        self._nodes[name] = fn

    def add_edge(self, src: str, dst: str) -> None:
        if src == START:
            self._entry = dst
        else:
            self._edges[src] = dst

    def add_conditional_edges(self, src: str, router: RouteFn, mapping: dict[str, str]) -> None:
        self._cond[src] = (router, mapping)

    def compile(self) -> "CompiledGraph":
        if self._entry is None:
            raise ValueError("thiếu cạnh START -> node đầu")
        return CompiledGraph(self._nodes, self._edges, self._cond, self._entry)


class CompiledGraph:
    def __init__(self, nodes, edges, cond, entry) -> None:
        self._nodes, self._edges, self._cond, self._entry = nodes, edges, cond, entry

    def stream(self, initial: State, *, recursion_limit: int = 100, trace: list[str] | None = None) -> State:
        """Đi theo khung cho tới END. Mỗi vòng: gọi node -> merge update -> chọn node kế."""
        state: State = dict(initial)
        current = self._entry
        steps = 0
        while current != END:
            if steps > recursion_limit:
                raise RuntimeError("recursion_limit vượt — khung có vòng lặp vô hạn?")
            steps += 1
            if trace is not None:
                trace.append(current)
            update = self._nodes[current](state)
            state.update(update)
            current = self._next(current, state)
        return state

    def _next(self, current: str, state: State) -> str:
        if current in self._edges:
            return self._edges[current]
        if current in self._cond:
            router, mapping = self._cond[current]
            key = router(state)
            if key not in mapping:
                raise KeyError(f"route {key!r} từ node {current!r} không có trong bảng cạnh")
            return mapping[key]
        raise KeyError(f"node {current!r} không có cạnh ra")


# ─────────────────────────────────────────────────────────────────────────────
# Hạ tầng fake (thay KernelSession / LLM / tool execution)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Budget:
    steps: int = 0
    max_steps: int = 6

    def record_step(self) -> None:
        self.steps += 1


@dataclass
class FakeSession:
    """Thay KernelSession: chỉ giữ events để minh hoạ _emit, và một script LLM."""
    events: list[tuple[str, dict]] = field(default_factory=list)
    llm_script: list[dict] = field(default_factory=list)
    _i: int = 0

    def next_action(self) -> dict:
        """Thay agent_node gọi LLM rồi parse_action: trả action kế trong script."""
        act = self.llm_script[self._i] if self._i < len(self.llm_script) else {"action": "final", "message": "done"}
        self._i += 1
        return act

    def run_tool(self, name: str, args: dict) -> dict:
        """Thay session.execute_tool: tool tất định trả envelope ok."""
        return {"ok": True, "data": {"tool": name, "args": args, "result": f"ran:{name}"}}


# ─────────────────────────────────────────────────────────────────────────────
# Concrete operations DÙNG CHUNG cho mọi node  (nodes.py:20-37)
# ─────────────────────────────────────────────────────────────────────────────
def _restore_budget(state: State) -> Budget:
    b = state.get("budget") or {}
    return Budget(steps=b.get("steps", 0), max_steps=b.get("max_steps", 6))


def _emit(session: FakeSession, topic: str, **payload: Any) -> None:
    session.events.append((topic, payload))


def _route(state: State) -> str:
    """runtime.py:27-28 — đọc route từ state, mặc định 'fail'."""
    return str(state.get("route") or "fail")


# ─────────────────────────────────────────────────────────────────────────────
# HOOKS — mỗi node hiện thực CÙNG hợp đồng node(state) -> {..., "route": ...}
# ─────────────────────────────────────────────────────────────────────────────
def guard_node(state: State, *, session: FakeSession) -> dict[str, Any]:
    """nodes.py:40-48 — dừng trước LLM call kế nếu hết budget."""
    budget = _restore_budget(state)              # restore (chung)
    if budget.steps >= budget.max_steps:         # xử lý chuyên biệt
        _emit(session, "graph.budget_blocked", reason="step budget exceeded")
        return {"route": "fail", "error": "step budget exceeded"}
    return {"route": "agent"}


def agent_node(state: State, *, session: FakeSession) -> dict[str, Any]:
    """nodes.py:51-103 — gọi LLM, parse 1 action, set route theo verb."""
    budget = _restore_budget(state)
    action = session.next_action()               # thay LLM call + parse_action
    budget.record_step()
    verb = str(action.get("action", ""))
    _emit(session, "graph.step", action=verb, next_step=budget.steps)
    update: dict[str, Any] = {
        "budget": {"steps": budget.steps, "max_steps": budget.max_steps},
        "last_action": action,
    }
    if verb == "tool":
        update["route"] = "tool"
    elif verb == "final":
        update["route"] = "finish"
    else:
        update["route"] = "guard"               # verb lạ -> quay lại guard
    return update


def tool_node(state: State, *, session: FakeSession) -> dict[str, Any]:
    """nodes.py:106-138 — chạy tool qua 'kernel' rồi quay lại guard."""
    action = dict(state.get("last_action") or {})
    name = str(action.get("tool", ""))
    args = action.get("args") or {}
    result = session.run_tool(name, args)        # xử lý chuyên biệt
    _emit(session, "graph.tool_ran", tool=name, ok=result["ok"])
    history = list(state.get("tool_history") or [])
    history.append(result["data"]["result"])
    return {"tool_history": history, "route": "guard"}


def finish_node(state: State, *, session: FakeSession) -> dict[str, Any]:
    """nodes.py:202-240 — cổng finish (rút gọn) rồi đóng run."""
    action = dict(state.get("last_action") or {})
    final = str(action.get("message", ""))
    _emit(session, "graph.completed", status="completed")
    return {"final": final, "status": "completed", "route": "end"}


def fail_node(state: State, *, session: FakeSession) -> dict[str, Any]:
    """nodes.py:243-255 — đóng run thất bại qua cùng lifecycle."""
    reason = str(state.get("error") or "agent run failed")
    _emit(session, "graph.completed", status="failed", reason=reason)
    return {"status": "failed", "final": None, "route": "end"}


# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATE METHOD FACTORY — build_agent_graph()  (runtime.py:31-66)
# ─────────────────────────────────────────────────────────────────────────────
def build_agent_graph(session: FakeSession) -> CompiledGraph:
    """Dựng KHUNG cố định. Thứ tự cạnh ở đây CHÍNH là skeleton — không node nào
    được tự ý nhảy ngoài bảng này."""
    def bind(fn):
        return lambda state: fn(state, session=session)

    builder = MiniStateGraph()
    builder.add_node("guard", bind(guard_node))
    builder.add_node("agent", bind(agent_node))
    builder.add_node("tool", bind(tool_node))
    builder.add_node("finish", bind(finish_node))
    builder.add_node("fail", bind(fail_node))

    builder.add_edge(START, "guard")
    builder.add_conditional_edges("guard", _route, {"agent": "agent", "fail": "fail"})
    builder.add_conditional_edges("agent", _route,
                                  {"tool": "tool", "finish": "finish", "guard": "guard", "fail": "fail"})
    builder.add_conditional_edges("tool", _route, {"guard": "guard", "fail": "fail"})
    builder.add_conditional_edges("finish", _route, {"guard": "guard", "end": END})
    builder.add_edge("fail", END)
    return builder.compile()


# ─────────────────────────────────────────────────────────────────────────────
# Đối chứng: viết loop thủ công không có khung -> dễ phá thứ tự, khó thêm node
# ─────────────────────────────────────────────────────────────────────────────
def run_loop_NO_PATTERN(session: FakeSession, *, max_steps: int = 6) -> State:
    """Cùng hành vi nhưng viết tay vòng lặp: thứ tự bước nằm rải rác trong if/elif,
    KHÔNG có ai 'ép' khung. Thêm node 'delegate' = phải sửa lõi vòng lặp này, và
    rất dễ vô tình gọi sai thứ tự (vd quên guard giữa hai tool call)."""
    state: State = {"budget": {"steps": 0, "max_steps": max_steps}}
    steps = 0
    while True:
        steps += 1
        if steps > 100:
            raise RuntimeError("loop runaway")
        budget = _restore_budget(state)
        if budget.steps >= budget.max_steps:
            return {**state, "status": "failed", "final": None}
        action = session.next_action()
        budget.record_step()
        state["budget"] = {"steps": budget.steps, "max_steps": budget.max_steps}
        verb = action.get("action")
        if verb == "tool":
            res = session.run_tool(action.get("tool", ""), action.get("args") or {})
            hist = list(state.get("tool_history") or [])
            hist.append(res["data"]["result"])
            state["tool_history"] = hist
            # LƯU Ý: ở đây rất dễ QUÊN kiểm tra budget trước vòng kế (bug thật)
            continue
        if verb == "final":
            return {**state, "status": "completed", "final": action.get("message", "")}
        # verb lạ: không rõ phải làm gì -> lặp tiếp (dễ vô hạn)


# ─────────────────────────────────────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────────────────────────────────────
def demo() -> None:
    print("=" * 74)
    print("CASE 02 — Graph Node Pipeline: khung cố định, mỗi node là một hook")
    print("=" * 74)

    # --- A. Đường thường: agent -> tool -> guard -> agent -> finish ----------
    print("\n[A] Run thành công (1 tool call rồi final):")
    session = FakeSession(llm_script=[
        {"action": "tool", "tool": "read_file", "args": {"path": "a.txt"}},
        {"action": "final", "message": "xong"},
    ])
    graph = build_agent_graph(session)
    trace: list[str] = []
    final = graph.stream({"budget": {"steps": 0, "max_steps": 6}}, trace=trace)
    print(f"  trace khung: {' -> '.join(trace)} -> END")
    print(f"  status={final['status']} final={final['final']!r} tool_history={final.get('tool_history')}")
    assert final["status"] == "completed"
    # Bất biến KHUNG: luôn bắt đầu bằng guard, agent đứng sau guard, finish là node áp chót.
    assert trace[0] == "guard", "khung PHẢI bắt đầu ở guard"
    assert trace[-1] == "finish", "node cuối trước END phải là finish (đường thành công)"
    # Mỗi tool đều phải có guard ngay trước lần agent kế (thứ tự bất biến):
    for i, n in enumerate(trace):
        if n == "tool":
            assert trace[i + 1] == "guard", "sau tool BẮT BUỘC quay về guard"

    # --- B. Budget chặn: hết step -> guard route sang fail -------------------
    print("\n[B] Budget cạn (max_steps=1, nhưng cần 2 step) -> fail:")
    session_b = FakeSession(llm_script=[
        {"action": "tool", "tool": "x", "args": {}},
        {"action": "final", "message": "không bao giờ tới"},
    ])
    graph_b = build_agent_graph(session_b)
    trace_b: list[str] = []
    final_b = graph_b.stream({"budget": {"steps": 0, "max_steps": 1}}, trace=trace_b)
    print(f"  trace khung: {' -> '.join(trace_b)} -> END")
    print(f"  status={final_b['status']} error={final_b.get('error')!r}")
    assert final_b["status"] == "failed"
    assert trace_b[-1] == "fail", "đường lỗi PHẢI kết thúc ở fail"

    # --- C. Bất biến hợp đồng: mọi node trả update có 'route' hợp lệ ---------
    print("\n[C] Bất biến hợp đồng node: mọi update có khoá 'route':")
    probe_session = FakeSession(llm_script=[{"action": "final", "message": "ok"}])
    st0: State = {"budget": {"steps": 0, "max_steps": 6}}
    for name, fn in [("guard", guard_node), ("fail", fail_node)]:
        upd = fn(st0, session=probe_session)
        assert "route" in upd, f"{name} thiếu khoá 'route'"
        print(f"  {name:8s} -> route={upd['route']!r}")

    # --- D. Mở rộng: thêm node 'finish' đã có sẵn — khung KHÔNG đổi handler --
    print("\n[D] Engine ép thứ tự: node KHÔNG tự gọi node kế, chỉ trả 'route'.")
    print("    -> Thêm/bớt node = sửa bảng cạnh ở build_agent_graph, handler giữ nguyên hợp đồng.")

    # --- E. ĐỐI CHỨNG: vòng lặp thủ công dễ phá thứ tự ----------------------
    print("\n[E] ĐỐI CHỨNG — run_loop_NO_PATTERN (thứ tự nằm rải trong if/elif):")
    session_e = FakeSession(llm_script=[
        {"action": "tool", "tool": "read_file", "args": {}},
        {"action": "final", "message": "xong"},
    ])
    out_e = run_loop_NO_PATTERN(session_e)
    print(f"  kết quả vẫn chạy: status={out_e['status']} (nhưng KHÔNG có ai bảo đảm")
    print("  guard luôn chen giữa hai tool call — thứ tự dựa vào kỷ luật lập trình viên).")
    print("  Thêm node 'delegate' = phải mổ lõi vòng lặp này; khung StateGraph chỉ cần thêm 1 cạnh.")

    # So sánh kết quả 2 cách trên cùng script -> giống nhau, nhưng khung an toàn hơn
    session_f1 = FakeSession(llm_script=[{"action": "tool", "tool": "t", "args": {}},
                                         {"action": "final", "message": "z"}])
    session_f2 = FakeSession(llm_script=[{"action": "tool", "tool": "t", "args": {}},
                                         {"action": "final", "message": "z"}])
    r1 = build_agent_graph(session_f1).stream({"budget": {"steps": 0, "max_steps": 6}})
    r2 = run_loop_NO_PATTERN(session_f2)
    assert r1["final"] == r2["final"] == "z"
    print("  Cùng script -> cùng final ('z'); khác biệt là TÍNH BẢO ĐẢM thứ tự, không phải output.")

    print("\nKẾT LUẬN: build_agent_graph dựng skeleton (thứ tự node cố định) qua bảng")
    print("cạnh; mỗi node là hook cùng hợp đồng state->update(route). Engine (StateGraph)")
    print("là 'skeleton enforcer' — node không tự gọi node kế. Đây là Template Method")
    print("ở scale kiến trúc: khung điều phối cố định, hành vi từng bước thì thay đổi.")


if __name__ == "__main__":
    demo()
