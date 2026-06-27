# CATALOG — Mọi nơi Command pattern xuất hiện trong hex_agent

Bảng vét cạn các occurrence của Command pattern (Behavioral) trong `hex_agent`.
Mỗi dòng đã được **mở file kiểm chứng**; nơi nào tên lớp/mô tả trong plan lệch với code thật,
cột "Mô tả" đã được ghi lại cho đúng (số dòng giữ theo bản đã xác nhận).

Root thật của mọi path: `/Users/uspro/Desktop/namnson/hex_agent/`

## Flagship (đã dựng case con)

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `core/schemas.py:28-34` | `ToolRequest` (frozen dataclass): `name`+`args`+`context`+`request_id` — ConcreteCommand bất biến | cao |
| `core/ports.py:19-26` | `ToolPort` Protocol: `execute(request: ToolRequest) -> dict[str, Any]` — Command interface | cao |
| `core/kernel.py:106-226` | `AgentKernel.execute_tool()` — Invoker: tạo `ToolRequest`, resolve executor, chạy qua middleware chain, publish event | cao |
| `core/kernel.py:152-177` | hàm `core(req)`: `resolution.executor.execute(req)` (dòng 155) — điểm thực thi Command qua Receiver | cao |
| `control/commands.py:61-106` | `RuntimeCommand` (frozen): `command_type`/`session_id`/`payload`/`issued_by`/`idempotency_key` — ConcreteCommand ở control-plane; parse qua `parse_command()` | cao |
| `control/command_registry.py:22-96` | `CommandTypeSpec` + `CommandTypeRegistry`: ánh xạ `command_type → apply_at` — chiến lược lên lịch/queue mỗi loại command | cao |
| `ui/ide/server.py:127-175` | `IdeControlServer.submit_command()` validate `RuntimeCommand`, lưu dedup map (idempotency), gọi `_dispatch()` — Invoker; `_dispatch()` route `SubmitPrompt` → `runner.start()` | cao |
| `config/runtime_command_types.yaml:9-37` | Bảng command-type: khai báo `apply_at` (next_checkpoint/immediate_if_waiting/immediate) + `requires_permission` — chính sách lên lịch theo loại | cao |

## Catalog đầy đủ (mọi occurrence còn lại)

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `features/example_echo.py:16-25` | `EchoTool.execute(request: ToolRequest) -> dict` — Receiver cụ thể implement Command interface | cao |
| `toolbox/filesystem.py:16-60` | `FsRead`/`FsWrite`/`FsList`: mỗi lớp có `name` + `execute(request: ToolRequest)` — nhiều Receiver | cao |
| `toolbox/terminal.py:1-50` | Lớp `Terminal` (`name = "terminal_run"`) với `execute(request: ToolRequest)` — một Receiver khác (lưu ý: tên lớp là `Terminal`, không phải `TerminalRun`) | cao |
| `middleware/retry.py:23-33` | `Retry`: gọi `nxt(request)` lặp lại khi chưa `ok` — lớp retry/queue quanh command (chặn retry với effect không idempotent) | cao |
| `control/replay.py:23-82` | `EventReplayBuffer`: ring buffer các event (command/event), dedup theo `event_id`, replay khi reconnect — persistence/replay | cao |
| `ui/ide/session.py:63-90` | `IdeSession.emit()`: stamp seq, redact, append vào buffer, notify waiter — queue/publish các command/event | cao |
| `rag/feature.py:53-92` | `RagHealthTool`/`RagIngestTool`/`RagSearchTool` (kế thừa `_RagTool`): mỗi lớp có `execute(request: ToolRequest)` — Receiver cho command RAG | vừa |
| `safety/policy.py:1-55` | `classify_terminal()` + `PolicyDecision` + `SafeToolPort`: gate/filter chặn request trước khi execute — gate trong command chain | vừa |
| `graph/nodes.py:55-128` | `agent_node`/`tool_node`: gọi `session.execute_tool(name, args)` — phía client phát Command (qua kernel chokepoint) | vừa |
| `core/registry.py:43-122` | `CapabilityRegistry.resolve_tool()`: ánh xạ tên tool → executor — registry cho Receiver của command | vừa |
| `middleware/policy.py:1-22` | `PolicyGate`: deny/allow tên tool trước khi execute — policy middleware trong command chain | vừa |
| `ui/ide/runner.py:1-100` | `AgentRunner.start(prompt)`: thực thi command `SubmitPrompt`, chạy vòng lặp agent — Receiver của command | vừa |
| `control/authz.py:1-49` | Các predicate authz (`is_permission_escalating`, `command_needs_human_checkpoint`) kiểm tra trước khi áp command sửa quyền — permission gate trong pipeline command | thấp |

## Ghi chú khớp nguồn

- `core/kernel.py:152-177` — `core()` định nghĩa ở dòng 152; `resolution.executor.execute(req)` ở dòng **155**; chain dựng ở dòng 192-194 (`handler = _wrap(mw, handler, ...)`), gọi ở dòng 196.
- `control/command_registry.py` — plan ghi 23-96; trong file `CommandTypeSpec` ở 22-33, `CommandTypeRegistry` ở 36-60, `parse_command_registry`/`load_command_registry` ở 63-95.
- `toolbox/terminal.py` — plan ghi lớp `TerminalRun`; thực tế lớp tên `Terminal` với `name = "terminal_run"` (`execute` ở dòng 15-49).
- `rag/feature.py` — plan ghi `EmbedSearch/Retrieve/Rerank`; thực tế các tool là `RagHealthTool`/`RagIngestTool`/`RagSearchTool` (kế thừa `_RagTool`, dòng 53-92) có `execute(request)`.
- `safety/policy.py` — `PolicyGate` của plan thực chất nằm ở `middleware/policy.py`; còn `safety/policy.py` cung cấp `classify_terminal()`/`PolicyDecision`/`SafeToolPort` làm gate trước execute.
- `control/authz.py` — file dài 49 dòng; nội dung khớp (predicate thuần, chưa có call-site enforcement — DEC-7).
