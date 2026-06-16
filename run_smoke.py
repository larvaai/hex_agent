"""Deterministic Sprint 0 smoke — no LLM, no network. Prints CORE_AGENT_SMOKE_OK on success."""
from __future__ import annotations

from core.bootstrap import create_kernel
from discipline import check_finish, parse_action
from observability import EventLogger, attach_to_bus


def main() -> int:
    kernel = create_kernel()
    logger = EventLogger()
    attach_to_bus(logger, kernel.events)

    kernel.accept_task("smoke: echo + discipline")
    logger.count("steps")

    ok = kernel.execute_tool("echo", {"msg": "hi"})
    assert ok["ok"] and ok["data"]["echo"] == {"msg": "hi"}, ok

    missing = kernel.execute_tool("does_not_exist")
    assert missing["ok"] is False and missing["data"].get("missing_capability") is True, missing

    action = parse_action('```json\n{"action": "final", "message": "done",}\n```')
    assert action["action"] == "final", action

    gate = check_finish({"code_changed": True, "validation_passed": False}, finish_reason="validated")
    assert gate["allowed"] is False, gate

    summary = logger.finish("completed")
    print("CORE_AGENT_SMOKE_OK run_id=" + summary["run_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
