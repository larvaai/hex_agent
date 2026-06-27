"""
Case 01 — Builder pattern: StateGraph builder lắp ráp graph điều phối agent.

DISTILL TRUNG THỰC TỪ CODE THẬT:
  - hex_agent/graph/runtime.py:31-66  -> hàm build_agent_graph():
        builder = StateGraph(AgentState)              # tạo builder rỗng
        builder.add_node("guard", ...)                # tích lũy node qua method
        builder.add_node("agent", ...)
        builder.add_node("tool", ...)
        builder.add_node("delegate", ...)
        builder.add_node("finish", ...)
        builder.add_node("fail", ...)
        builder.add_edge(START, "guard")              # tích lũy cạnh
        builder.add_conditional_edges("guard", _route, {...})
        ...
        return builder.compile(...)                   # finalize -> product immutable
  - hex_agent/graph/__init__.py:1-4 -> export build_agent_graph như public API.

Trong code thật, StateGraph (của LangGraph) đóng vai BUILDER: nó là object trung
gian giữ state đang-build (danh sách node + cạnh), mỗi lần gọi add_node/add_edge/
add_conditional_edges là một BƯỚC build cập nhật state nội bộ. Khi gọi .compile()
nó VALIDATE toàn bộ graph (mọi node phải có cạnh ra hợp lệ, mọi đích phải tồn tại,
phải reach được END) rồi trả về PRODUCT immutable — một compiled graph chạy được.

File này thay LangGraph + LLM + AgentState nặng bằng fake tối thiểu bằng stdlib:
  - StateGraph -> lớp `GraphBuilder` tự cài (giữ nodes, edges, conditional edges).
  - Compiled graph -> lớp `CompiledGraph` immutable (frozen), có .run() đi qua các node.
  - Node function -> hàm Python thuần đơn giản, không gọi LLM.
Giữ NGUYÊN vai trò pattern: builder tích lũy bước -> validate tại compile -> product
immutable.

Chỉ dùng thư viện chuẩn Python 3.14. Không import hex_agent, không thư viện ngoài.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

# ---------------------------------------------------------------------------
# Hằng số marker cho điểm vào / điểm ra của graph (tương ứng START / END của
# LangGraph trong graph/runtime.py:8).
# ---------------------------------------------------------------------------
START = "__start__"
END = "__end__"

# Kiểu state đi qua graph: ở code thật là AgentState (TypedDict lớn). Ở đây ta
# dùng dict đơn giản để minh họa.
State = dict
NodeFn = Callable[[State], State]      # node nhận state, trả state đã cập nhật
RouteFn = Callable[[State], str]       # hàm định tuyến trả về tên nhánh


# ===========================================================================
# PRODUCT — graph đã compile, IMMUTABLE.
# Tương ứng: giá trị trả về của builder.compile() (graph/runtime.py:66).
# ===========================================================================
@dataclass(frozen=True)
class CompiledGraph:
    """Sản phẩm cuối: graph bất biến đã qua validate. Chỉ còn việc chạy."""

    name: str
    nodes: Mapping[str, NodeFn]
    # cạnh tĩnh: node -> đích cố định
    static_edges: Mapping[str, str]
    # cạnh điều kiện: node -> (route_fn, {nhánh -> đích})
    conditional_edges: Mapping[str, tuple[RouteFn, Mapping[str, str]]]
    entry: str

    def run(self, initial: State, *, max_hops: int = 100) -> State:
        """Đi qua graph từ START tới END theo cạnh đã được wire sẵn."""
        current = self.entry
        state = dict(initial)
        hops = 0
        while current != END:
            hops += 1
            if hops > max_hops:
                raise RuntimeError("Vượt giới hạn bước — có thể graph bị lặp vô hạn.")
            # Thực thi node (nếu là node thật, không phải START)
            if current in self.nodes:
                state = self.nodes[current](state)
            current = self._next(current, state)
        return state

    def _next(self, node: str, state: State) -> str:
        if node in self.conditional_edges:
            route_fn, mapping = self.conditional_edges[node]
            branch = route_fn(state)
            if branch not in mapping:
                raise RuntimeError(
                    f"Node {node!r} định tuyến tới nhánh không tồn tại: {branch!r}"
                )
            return mapping[branch]
        if node in self.static_edges:
            return self.static_edges[node]
        raise RuntimeError(f"Node {node!r} không có cạnh ra — graph kẹt.")


# ===========================================================================
# BUILDER — object trung gian, STATEFUL, giữ cấu hình đang-build.
# Tương ứng: StateGraph trong graph/runtime.py:38 (builder = StateGraph(...)).
# ===========================================================================
class GraphBuilder:
    """Tích lũy node + cạnh qua các method, validate khi compile()."""

    def __init__(self, state_type: type) -> None:
        self.state_type = state_type
        self._nodes: dict[str, NodeFn] = {}
        self._static_edges: dict[str, str] = {}
        self._conditional_edges: dict[str, tuple[RouteFn, dict[str, str]]] = {}
        self._compiled = False  # chốt: không cho mutate sau khi compile

    # --- mỗi method dưới đây là MỘT BƯỚC BUILD, cập nhật state nội bộ -------
    def add_node(self, name: str, fn: NodeFn) -> "GraphBuilder":
        self._guard_open()
        if name in (START, END):
            raise ValueError(f"{name!r} là marker dành riêng, không thể làm node.")
        if name in self._nodes:
            raise ValueError(f"Node trùng tên: {name!r}")
        self._nodes[name] = fn
        return self  # trả self -> cho phép chaining (fluent)

    def add_edge(self, src: str, dst: str) -> "GraphBuilder":
        self._guard_open()
        self._static_edges[src] = dst
        return self

    def add_conditional_edges(
        self, src: str, route_fn: RouteFn, mapping: dict[str, str]
    ) -> "GraphBuilder":
        self._guard_open()
        self._conditional_edges[src] = (route_fn, dict(mapping))
        return self

    # --- FINALIZATION — validate cross-component rồi tạo product immutable ---
    def compile(self, *, name: str = "graph") -> CompiledGraph:
        self._guard_open()
        entry = self._static_edges.get(START)
        if entry is None:
            raise ValueError("Graph thiếu cạnh từ START — không biết bắt đầu ở đâu.")

        # Validate: mọi đích của mọi cạnh phải là node đã khai báo hoặc END.
        known = set(self._nodes) | {END}
        for src, dst in self._static_edges.items():
            if src == START:
                if dst not in known:
                    raise ValueError(f"START trỏ tới đích lạ: {dst!r}")
                continue
            if src not in self._nodes:
                raise ValueError(f"Cạnh xuất phát từ node lạ: {src!r}")
            if dst not in known:
                raise ValueError(f"Cạnh {src}->{dst}: đích {dst!r} không tồn tại.")
        for src, (_route, mapping) in self._conditional_edges.items():
            if src not in self._nodes:
                raise ValueError(f"Cạnh điều kiện từ node lạ: {src!r}")
            for branch, dst in mapping.items():
                if dst not in known:
                    raise ValueError(
                        f"Nhánh {src}--{branch}-->{dst}: đích {dst!r} không tồn tại."
                    )

        # Validate: mọi node phải có ít nhất một cạnh ra (tránh node kẹt).
        for node in self._nodes:
            has_out = node in self._static_edges or node in self._conditional_edges
            if not has_out:
                raise ValueError(f"Node {node!r} không có cạnh ra — sẽ kẹt khi chạy.")

        self._compiled = True
        return CompiledGraph(
            name=name,
            nodes=dict(self._nodes),
            static_edges=dict(self._static_edges),
            conditional_edges={
                k: (rf, dict(m)) for k, (rf, m) in self._conditional_edges.items()
            },
            entry=entry,
        )

    def _guard_open(self) -> None:
        if self._compiled:
            raise RuntimeError(
                "Builder đã compile — không thể sửa graph sau khi finalize."
            )


# ===========================================================================
# NODE FUNCTIONS — fake tối thiểu thay cho guard/agent/tool/finish/fail thật.
# Trong code thật chúng là partial(guard_node, session=...) v.v. có gọi LLM,
# kernel, registry... Ở đây chỉ là hàm thuần xử lý dict.
# ===========================================================================
def guard_node(state: State) -> State:
    """Kiểm tra ngân sách trước khi cho agent chạy (mô phỏng guard_node thật)."""
    if state["steps"] >= state["max_steps"]:
        return {**state, "route": "fail", "error": "Hết ngân sách."}
    return {**state, "route": "agent"}


def agent_node(state: State) -> State:
    """Agent quyết định: gọi tool hay kết thúc (mô phỏng agent_node thật)."""
    state = {**state, "steps": state["steps"] + 1}
    plan = state["plan"]
    idx = state["steps"] - 1
    if idx < len(plan):
        return {**state, "route": "tool", "next_tool": plan[idx]}
    return {**state, "route": "finish"}


def tool_node(state: State) -> State:
    """Thực thi tool rồi quay lại guard (mô phỏng tool_node thật)."""
    results = list(state.get("results", []))
    results.append(f"ran:{state['next_tool']}")
    return {**state, "route": "guard", "results": results}


def finish_node(state: State) -> State:
    return {**state, "route": "end", "status": "completed", "final": state["results"]}


def fail_node(state: State) -> State:
    return {**state, "status": "failed", "final": None}


def _route(state: State) -> str:
    """Đọc nhánh tiếp theo từ state (mô phỏng _route trong runtime.py:27-28)."""
    return str(state.get("route") or "fail")


# ===========================================================================
# DIRECTOR-LIKE FACTORY — tương ứng build_agent_graph() trong runtime.py:31-66.
# Đóng gói TRÌNH TỰ wire node + cạnh quen thuộc thành một sản phẩm.
# ===========================================================================
def build_agent_graph(*, max_steps: int = 12) -> CompiledGraph:
    """Lắp ráp graph điều phối agent — distill của graph/runtime.py:31-66."""
    builder = GraphBuilder(State)
    builder.add_node("guard", guard_node)
    builder.add_node("agent", agent_node)
    builder.add_node("tool", tool_node)
    builder.add_node("finish", finish_node)
    builder.add_node("fail", fail_node)

    builder.add_edge(START, "guard")
    builder.add_conditional_edges("guard", _route, {"agent": "agent", "fail": "fail"})
    builder.add_conditional_edges(
        "agent",
        _route,
        {"tool": "tool", "finish": "finish", "fail": "fail"},
    )
    builder.add_conditional_edges("tool", _route, {"guard": "guard", "fail": "fail"})
    builder.add_conditional_edges("finish", _route, {"guard": "guard", "end": END})
    builder.add_edge("fail", END)
    return builder.compile(name="core-agent")


# ===========================================================================
# DEMO
# ===========================================================================
def demo() -> None:
    print("=" * 70)
    print("CASE 01 — Builder: StateGraph builder lắp ráp graph điều phối agent")
    print("=" * 70)

    print("\n[1] Builder tích lũy từng bước (add_node, add_edge, ...) rồi compile().")
    graph = build_agent_graph(max_steps=12)
    print(f"    -> Product: CompiledGraph(name={graph.name!r}), "
          f"{len(graph.nodes)} node, entry={graph.entry!r}")
    print("    (Bản rút gọn còn 5 node — đã lược node 'delegate' so với 6 node của")
    print("     code thật runtime.py:42-45; vai trò pattern không đổi, xem README mục 4.)")

    print("\n[2] Chạy graph đã compile với một kế hoạch 2 tool.")
    initial: State = {
        "steps": 0,
        "max_steps": 12,
        "plan": ["search", "summarize"],
        "results": [],
    }
    final = graph.run(initial)
    print(f"    -> status={final['status']!r}, final={final['final']!r}")
    assert final["status"] == "completed"
    assert final["final"] == ["ran:search", "ran:summarize"]

    print("\n[3] BẤT BIẾN: product immutable — sửa graph đã compile sẽ bị chặn.")
    try:
        graph.name = "hacked"  # type: ignore[misc]  # frozen dataclass -> chặn gán
    except Exception as exc:  # noqa: BLE001
        print(f"    -> Gán graph.name bị chặn: {type(exc).__name__}: {exc}")
    assert graph.name == "core-agent"

    print("\n[4] BẤT BIẾN: builder đã compile thì không cho mutate thêm.")
    b = GraphBuilder(State)
    b.add_node("only", lambda s: {**s, "route": "end"})
    b.add_edge(START, "only")
    b.add_conditional_edges("only", _route, {"end": END})
    b.compile()
    try:
        b.add_node("late", lambda s: s)
    except RuntimeError as exc:
        print(f"    -> add_node sau compile bị chặn: {exc}")

    print("\n[5] VALIDATE tại compile(): cạnh trỏ tới đích không tồn tại -> fail-fast.")
    bad = GraphBuilder(State)
    bad.add_node("a", lambda s: {**s, "route": "go"})
    bad.add_edge(START, "a")
    bad.add_conditional_edges("a", _route, {"go": "ghost"})  # 'ghost' không có
    try:
        bad.compile()
    except ValueError as exc:
        print(f"    -> compile() chặn graph hỏng ngay: {exc}")

    print("\n[6] ĐỐI CHỨNG — KHÔNG dùng Builder: dựng dict tay, quên cạnh ra.")
    print("    Không có khâu validate tập trung -> lỗi chỉ lộ ra LÚC CHẠY, khó truy.")
    naive_nodes = {"agent": agent_node}          # quên wire cạnh ra cho 'agent'
    naive_edges: dict[str, str] = {START: "agent"}
    naive = CompiledGraph(
        name="naive", nodes=naive_nodes, static_edges=naive_edges,
        conditional_edges={}, entry="agent",
    )
    try:
        naive.run({"steps": 0, "max_steps": 5, "plan": [], "results": []})
    except RuntimeError as exc:
        print(f"    -> Sập khi chạy (đáng lẽ Builder bắt ở compile): {exc}")

    print("\n" + "=" * 70)
    print("KẾT LUẬN: Builder (StateGraph) tách QUY TRÌNH LẮP RÁP graph phức tạp")
    print("khỏi BIỂU DIỄN (AgentState), validate tập trung tại compile(), sản phẩm")
    print("immutable. Cùng builder dựng được nhiều biến thể graph khác nhau.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
