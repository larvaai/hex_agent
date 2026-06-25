# GLOSSARY — ngôn ngữ chung của hex_agent

> Mỗi thuật ngữ load-bearing dùng một lần được định nghĩa ở đây để plan/code không tự đặt lại tên. Thêm hàng khi một plan đặt thuật ngữ mới.

| Thuật ngữ | Nghĩa |
|---|---|
| chokepoint | Cửa duy nhất mọi LLM+tool call phải đi qua: `AgentKernel.execute_tool` ([core/kernel.py:63](../core/kernel.py)). Delegation là chokepoint thứ hai, tách riêng ([delegation/manager.py:63](../delegation/manager.py)). |
| roster-growth | Thêm một agent/role vào team của một TaskLoop ĐANG chạy, qua command `AddAgentToLoop`, áp tại safe checkpoint. Đối lập với compose-team (chốt một lần lúc khởi tạo). |
| department alias | Một nhóm role có tên (gom theo `RoleSpec.department`, [roles/spec.py:45](../roles/spec.py)) mà Agent-O target được; expand thành một `delegate()` mỗi member, tuần tự, trước authority gate. Không phải sub-loop lồng, không parallel. |
| to-admit member | Member của một department chưa nằm trong `selected_agents`; được enqueue `AddAgentToLoop` và chạy ở round kế (không same-round admit). |
| safe checkpoint | Điểm cuối round trong `_drive` — một `ctx.save` atomic duy nhất nơi pending commands được áp (gộp `round_no`, roster, `applied_command_keys`, clear `pending_commands`). |
| pending command | Một `RuntimeCommand` do O phát (trong `OrchestratorDecision.commands`), xếp hàng trong `TaskLoopState.pending_commands`, áp tại safe checkpoint kế. |
| command bridge | `supervisor/command_bridge.py` — cầu nối supervisor↔control-plane: dịch ý định command của O thành `RuntimeCommand`, enqueue, và apply. |
| trust-O | O-issued command bỏ qua `requires_permission` (O là actor được tin; chấp nhận O fail trong rào cấu trúc: catalog-bound, scope-narrow, authority gate). Human-issued vẫn gate riêng (ngoài scope v1). |
| authority gate | Kiểm tra trong `run_round` ([supervisor/graph.py:142-147](../supervisor/graph.py)): mọi assignment phải target agent đã có trong `selected_agents`, nếu không → `PermissionError`. Nguồn chân lý cuối, chạy SAU department expansion + SAU apply command. |
