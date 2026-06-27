"""
Case 02 — Builder pattern: Director điều phối Builder để tạo biến thể product.

DISTILL TRUNG THỰC TỪ CODE THẬT:
  - hex_agent/orchestrator/loop.py:130-147  -> hàm run():
        if not checkpoint:
            graph = build_agent_graph(                       # BIẾN THỂ "đơn giản"
                session=active_session,
                delegation_service=delegation_service,
            )
            state = _stream(graph, initial, config=config, projection=False)
            ...
        with open_checkpointer(rid) as saver:
            graph = build_agent_graph(                       # BIẾN THỂ "bền bỉ"
                session=active_session,
                checkpointer=saver,                          # <- thêm checkpointer
                delegation_service=delegation_service,
            )
            state = _stream(graph, initial, config=config, projection=True)
            ...
  - hex_agent/orchestrator/loop.py:246-273 -> hàm resume(): cũng gọi
        build_agent_graph(session=..., checkpointer=saver, ...)  (dòng 255-259)
        để dựng lại graph bền bỉ khi tiếp tục một run đang dở.
  - hex_agent/graph/runtime.py:31-66 -> chính là build_agent_graph (BUILDER).
  - hex_agent/adapters/agents/langgraph_agent.py:45-49 -> cũng dùng cùng builder
        với InMemorySaver để dựng graph cho child agent (một biến thể nữa).

Ý chính: CÙNG MỘT BUILDER (build_agent_graph) tạo ra NHIỀU BIẾN THỂ PRODUCT tùy
cờ runtime: graph "không checkpoint" (nhanh, không bền) vs graph "có checkpoint"
(bền, resume được). Hàm run()/resume() đóng vai DIRECTOR: chúng quyết định gọi
builder với cấu hình nào, KHÁCH HÀNG (client) không cần biết chi tiết wiring.

File này thay LangGraph + checkpointer DB (SQLite) + session nặng bằng fake stdlib:
  - build_agent_graph -> builder đơn giản nhận cờ checkpointer.
  - open_checkpointer (SQLite) -> SaverInMemory (dict trong RAM).
  - run()/resume()  -> director chọn biến thể "simple" vs "resilient".

Chỉ dùng thư viện chuẩn Python 3.14. Không import hex_agent, không thư viện ngoài.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

State = dict


# ===========================================================================
# Hạ tầng checkpoint fake — thay open_checkpointer()/SQLite trong code thật.
# ===========================================================================
class Saver:
    """Giao diện checkpointer tối thiểu: lưu/đọc state theo run_id."""

    def save(self, run_id: str, state: State) -> None:
        raise NotImplementedError

    def load(self, run_id: str) -> Optional[State]:
        raise NotImplementedError


class InMemorySaver(Saver):
    """Checkpointer trong RAM — đủ minh họa tính 'bền' giữa run và resume."""

    def __init__(self) -> None:
        self._store: dict[str, State] = {}

    def save(self, run_id: str, state: State) -> None:
        self._store[run_id] = dict(state)

    def load(self, run_id: str) -> Optional[State]:
        snap = self._store.get(run_id)
        return dict(snap) if snap is not None else None


# ===========================================================================
# PRODUCT — graph đã compile. checkpointer được "nướng" vào product:
# nếu có -> mỗi bước được save (bền, resume được); nếu None -> chạy thoáng qua.
# Tương ứng giá trị trả về của build_agent_graph (runtime.py:66).
# ===========================================================================
@dataclass(frozen=True)
class CompiledGraph:
    name: str
    checkpointer: Optional[Saver]      # None -> simple ; Saver -> resilient
    step_fn: Callable[[State], State]  # một bước xử lý (mô phỏng chuỗi node)

    @property
    def resilient(self) -> bool:
        return self.checkpointer is not None

    def run(self, run_id: str, initial: State, *, max_steps: int = 12) -> State:
        state = dict(initial)
        while not state.get("done"):
            if state["steps"] >= max_steps:
                state["status"] = "incomplete"
                break
            state = self.step_fn(state)
            if self.checkpointer is not None:
                self.checkpointer.save(run_id, state)  # bền: lưu sau mỗi bước
        return state


# ===========================================================================
# BUILDER — build_agent_graph: CÙNG quy trình, khác cấu hình -> khác product.
# Tương ứng graph/runtime.py:31-66.
# ===========================================================================
def step_fn(state: State) -> State:
    """Một bước điều phối: làm 1 việc trong plan, đếm step (fake node chain)."""
    state = {**state, "steps": state["steps"] + 1}
    plan = state["plan"]
    done_count = state["steps"]
    if done_count >= len(plan):
        results = [f"ran:{t}" for t in plan]
        return {**state, "done": True, "status": "completed",
                "results": results, "final": results}
    return state


def build_agent_graph(*, checkpointer: Optional[Saver] = None) -> CompiledGraph:
    """BUILDER: dựng graph; có/không checkpointer -> hai biến thể product.

    Distill của graph/runtime.py:31-66 — ở code thật builder tích lũy node/cạnh
    rồi builder.compile(checkpointer=checkpointer). Cờ checkpointer chính là điểm
    rẽ tạo biến thể (loop.py:131 vs loop.py:140).
    """
    name = "core-agent" if checkpointer is None else "core-agent+ckpt"
    return CompiledGraph(name=name, checkpointer=checkpointer, step_fn=step_fn)


# ===========================================================================
# DIRECTOR — run()/resume(): quyết định gọi builder với cấu hình nào.
# Tương ứng orchestrator/loop.py:93-147 (run) và :217-273 (resume).
# ===========================================================================
def run(run_id: str, user_request: list[str], *, checkpoint: bool = True) -> State:
    """Distill của orchestrator/loop.py run(): chọn biến thể theo cờ checkpoint."""
    initial: State = {"steps": 0, "plan": user_request, "done": False,
                      "status": "running", "results": []}
    if not checkpoint:
        # loop.py:130-137 — biến thể "đơn giản", không bền.
        graph = build_agent_graph()
        return graph.run(run_id, initial)
    # loop.py:139-147 — biến thể "bền bỉ", dùng chung 1 saver toàn cục.
    graph = build_agent_graph(checkpointer=_GLOBAL_SAVER)
    return graph.run(run_id, initial)


def resume(run_id: str) -> State:
    """Distill của orchestrator/loop.py resume() (:217-273, build ở :255-259).

    Đọc checkpoint đã lưu, dựng LẠI graph bền bỉ bằng CÙNG builder, chạy tiếp.
    """
    persisted = _GLOBAL_SAVER.load(run_id)
    if persisted is None:
        raise FileNotFoundError(f"Không có checkpoint cho run_id={run_id!r}")
    if persisted.get("done"):
        return persisted  # đã xong từ trước, không cần chạy tiếp
    graph = build_agent_graph(checkpointer=_GLOBAL_SAVER)  # cùng builder, biến thể bền
    return graph.run(run_id, persisted)


# Saver toàn cục mô phỏng DB checkpoint trên đĩa (open_checkpointer trong code thật).
_GLOBAL_SAVER = InMemorySaver()


# ===========================================================================
# DEMO
# ===========================================================================
def demo() -> None:
    print("=" * 70)
    print("CASE 02 — Builder + Director: cùng builder, nhiều biến thể product")
    print("=" * 70)

    print("\n[1] Director run() với checkpoint=False -> biến thể 'simple'.")
    simple = build_agent_graph()
    print(f"    -> product name={simple.name!r}, resilient={simple.resilient}")
    out_simple = run("run-simple", ["fetch", "parse"], checkpoint=False)
    print(f"    -> kết quả: status={out_simple['status']!r}, "
          f"final={out_simple['final']!r}")
    assert out_simple["status"] == "completed"
    assert simple.resilient is False

    print("\n[2] Director run() với checkpoint=True -> biến thể 'resilient'.")
    resilient = build_agent_graph(checkpointer=_GLOBAL_SAVER)
    print(f"    -> product name={resilient.name!r}, resilient={resilient.resilient}")
    assert resilient.resilient is True

    print("\n[3] BẤT BIẾN: cùng MỘT builder tạo ra HAI product khác nhau theo cờ.")
    assert simple.name != resilient.name
    assert type(simple) is type(resilient) is CompiledGraph
    print(f"    -> cùng kiểu {CompiledGraph.__name__}, khác cấu hình "
          f"({simple.name!r} vs {resilient.name!r}).")

    print("\n[4] Biến thể 'resilient' lưu checkpoint sau mỗi bước -> resume được.")
    # Chạy GIỚI HẠN 1 bước để mô phỏng run bị ngắt giữa chừng.
    partial_state = build_agent_graph(checkpointer=_GLOBAL_SAVER).run(
        "run-ckpt", {"steps": 0, "plan": ["a", "b", "c"], "done": False,
                     "status": "running", "results": []},
        max_steps=1,
    )
    print(f"    -> sau khi bị ngắt: steps={partial_state['steps']}, "
          f"done={partial_state['done']}, status={partial_state['status']!r}")
    assert partial_state["done"] is False
    saved = _GLOBAL_SAVER.load("run-ckpt")
    assert saved is not None and saved["steps"] == 1
    print(f"    -> checkpoint đã lưu: steps={saved['steps']}")

    print("\n[5] Director resume() dựng LẠI graph bền bỉ bằng cùng builder, chạy tiếp.")
    finished = resume("run-ckpt")
    print(f"    -> resume xong: status={finished['status']!r}, "
          f"final={finished['final']!r}")
    assert finished["status"] == "completed"
    assert finished["final"] == ["ran:a", "ran:b", "ran:c"]

    print("\n[6] ĐỐI CHỨNG — biến thể 'simple' (không checkpoint) KHÔNG resume được.")
    build_agent_graph().run(
        "run-nockpt", {"steps": 0, "plan": ["x", "y", "z"], "done": False,
                       "status": "running", "results": []},
        max_steps=1,
    )
    try:
        resume("run-nockpt")
    except FileNotFoundError as exc:
        print(f"    -> resume thất bại như dự đoán: {exc}")
    print("    -> Đây là cái GIÁ của biến thể nhanh: không có state để khôi phục.")

    print("\n" + "=" * 70)
    print("KẾT LUẬN: Director (run/resume) phối hợp cùng MỘT Builder")
    print("(build_agent_graph) để tạo nhiều biến thể product theo cờ runtime.")
    print("Client không cần biết wiring; mở rộng biến thể không sửa client.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
