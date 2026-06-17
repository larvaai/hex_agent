run_smoke.py (line 1) là script kiểm tra nhanh toàn hệ nền Sprint 0. Nó chạy offline, không gọi LLM, không cần network. Nếu mọi thứ ổn, nó in:
CORE_AGENT_SMOKE_OK run_id=<run_id>

Luồng chạy:
Tạo kernel
kernel = create_kernel()
create_kernel() đọc config/features.yaml, tạo AgentKernel, CapabilityRegistry, EventBus, StateStore, rồi nạp feature example_echo. Sau bước này kernel có tool echo.
Tạo logger và gắn vào event bus
logger = EventLogger()
attach_to_bus(logger, kernel.events)
EventLogger tạo một run log mới trong var/agent_runs/<run_id>/. attach_to_bus() làm logger subscribe vào kernel.events, nên các event như tool.requested, tool.completed, tool.failed sẽ được ghi lại.
Nhận task giả lập
kernel.accept_task("smoke: echo + discipline")
logger.count("steps")
Kernel tạo TaskEnvelope, lưu vào state dưới key current_task, rồi publish event task.accepted.
Test tool hợp lệ
ok = kernel.execute_tool("echo", {"msg": "hi"})
assert ok["ok"] and ok["data"]["echo"] == {"msg": "hi"}, ok
Đoạn này kiểm tra feature loader + registry + kernel execute path. Nếu echo chạy đúng, kết quả phải có ok=True và data echo lại args.
Test missing tool fallback
missing = kernel.execute_tool("does_not_exist")
assert missing["ok"] is False and missing["data"].get("missing_capability") is True, missing
Kiểm tra tool không tồn tại không làm crash kernel. Registry phải trả NullToolPort, và kết quả phải là failure có cấu trúc với missing_capability=True.
Test JSON discipline
action = parse_action('```json\n{"action": "final", "message": "done",}\n```')
assert action["action"] == "final", action
Kiểm tra parse_action() có thể xử lý output kiểu LLM hay mắc lỗi: JSON nằm trong markdown fence và có trailing comma. Nếu parse được, action là "final".
Test finish gate
gate = check_finish({"code_changed": True, "validation_passed": False}, finish_reason="validated")
assert gate["allowed"] is False, gate
Kiểm tra rule an toàn: nếu code đã thay đổi nhưng validation chưa pass, agent không được final với lý do "validated".

Kết thúc logger và in success
summary = logger.finish("completed")
print("CORE_AGENT_SMOKE_OK run_id=" + summary["run_id"])
Logger ghi summary.json, append index.jsonl, rồi script in success marker.

Tóm lại: run_smoke.py là bài kiểm tra end-to-end nhỏ nhất cho nền agent: bootstrap config, nạp feature, chạy tool thành công, fallback tool thiếu, parse JSON action, finish gate, và observability log.