# CATALOG — Mọi occurrence của Builder pattern trong hex_agent

Bảng vét cạn các nơi Builder (Creational) xuất hiện trong codebase hex_agent,
gom từ bước discover. Cột `path:line` đã được mở file kiểm chứng.

## Flagships (đã dựng case riêng)

| # | path:line | Mô tả | Độ rõ |
|---|---|---|---|
| 01 | `graph/runtime.py:31-66` | `build_agent_graph()` dùng `StateGraph` builder dựng dần graph có hướng phức tạp: 6 node (guard, agent, tool, delegate, finish, fail) + cạnh điều kiện, rồi `.compile()` trả product immutable. | cao |
| 02 | `orchestrator/loop.py:130-147`, `:246-273` | `run()`/`resume()` là Director: gọi `build_agent_graph()` với cấu hình khác nhau (có/không checkpointer) để tạo biến thể graph phù hợp yêu cầu persistence. | cao |

## Catalog đầy đủ (mọi occurrence)

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `graph/runtime.py:31-66` | **[Flagship 01]** `build_agent_graph()`: builder `StateGraph(AgentState)` tích lũy node/cạnh qua `add_node`/`add_edge`/`add_conditional_edges`, finalize bằng `builder.compile(...)` -> graph immutable. | cao |
| `orchestrator/loop.py:130-147` | **[Flagship 02]** `run()`: nhánh `if not checkpoint` dựng graph không saver (`:131-134`); nhánh `with open_checkpointer(...)` dựng graph có saver (`:139-144`). Cùng builder, hai biến thể product. | cao |
| `orchestrator/loop.py:246-273` | **[Flagship 02]** `resume()`: đọc checkpoint rồi dựng lại graph bền bỉ bằng `build_agent_graph(session=..., checkpointer=saver, ...)` tại `:255-259`. | cao |
| `adapters/agents/langgraph_agent.py:45-49` | Dùng `build_agent_graph(session=child_session, checkpointer=InMemorySaver(), delegation_service=None)` để dựng graph cho child agent trong ngữ cảnh delegation. | cao |
| `graph/__init__.py:1-4` | Export `build_agent_graph` như public API, cho thấy builder này là abstraction lõi của hex_agent. | cao |
| `graph/runtime.py:85-127` | `run_agent()` (facade tương thích ngược) cũng gọi `build_agent_graph(session=session, checkpointer=InMemorySaver())` tại `:116`, minh họa builder hỗ trợ nhiều ngữ cảnh thực thi. | trung bình |

## Ghi chú độ rõ

- **cao**: dùng builder rõ ràng (`StateGraph` + `compile`, hoặc gọi
  `build_agent_graph` trực tiếp với cấu hình quyết định product).
- **trung bình**: dùng builder gián tiếp qua facade tương thích ngược; vai trò
  pattern vẫn đúng nhưng bị che bởi lớp wrapper.
