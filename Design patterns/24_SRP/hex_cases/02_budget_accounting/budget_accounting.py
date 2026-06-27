"""
SRP case 02 — Loop Budget Tracker (chỉ phục vụ Run-orchestration team).

Distill TRUNG THỰC từ codebase hex_agent:
  - discipline/budget.py:1-68   (toàn bộ @dataclass Budget)
      * các field max_*/steps/parse_errors/consecutive_parse_errors/_tool_calls
                                  -> budget.py:20-26
      * from_env (StaticFactory)  -> budget.py:28-35
      * record_step               -> budget.py:37-39
      * step_exceeded             -> budget.py:41-42
      * record_parse_error        -> budget.py:44-46
      * record_parse_success      -> budget.py:48-51
      * parse_exceeded            -> budget.py:53-54
      * record_tool_call          -> budget.py:56-58
      * same_tool_exceeded        -> budget.py:60-61
      * tool_key (static)         -> budget.py:63-67

Ý NGHĨA SRP:
  Budget chỉ có MỘT actor: đội điều phối vòng lặp (orchestrator/loop.py là reader/writer
  duy nhất). Nó chỉ ĐẾM và GÁC: "tôi đã vượt ngân sách chưa?". Không đụng permission,
  không đụng event, không đụng kernel. Mọi field đều được ít nhất 1 method dùng tới
  (cohesion cao, LCOM4 = 1). Không I/O, không business logic -> test cô lập dễ.

Vai trò pattern:
  - StateHolder : các field max_* + counter + _reset logic.
  - QueryPort   : step_exceeded / parse_exceeded / same_tool_exceeded -> trả bool.
  - MutationPort: record_* -> đẩy counter.
  - StaticFactory: from_env -> đọc cấu hình từ "môi trường" (ở đây dùng dict thay os.environ
                   để self-contained, KHÔNG cần env thật).

Bản distill:
  - Giữ NGUYÊN cấu trúc dataclass + API.
  - LƯỢC BỎ os.getenv thật -> nhận một dict `env` (mặc định rỗng). Đây là điểm tiêm cấu hình,
    giống hệt vai trò from_env() gốc nhưng không phụ thuộc môi trường ngoài.
  - Chỉ dùng stdlib (dataclasses, json).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Budget:
    """Điều khiển vòng lặp. Parse-error retry KHÔNG tiêu step.

    parse_errors là counter trọn đời (telemetry); consecutive_parse_errors (reset mỗi lần
    parse tốt) mới là cái trip gate — model lỡ tay 1 lần rồi hồi phục thì KHÔNG bị giết,
    chỉ model kẹt đẻ rác N lần LIÊN TIẾP mới bị chặn.
    """

    # ── StateHolder ──
    max_steps: int = 30
    max_parse_errors: int = 8           # số lần lỗi LIÊN TIẾP chịu được trước khi bỏ cuộc
    max_same_tool_calls: int = 3
    steps: int = 0
    parse_errors: int = 0               # trọn đời — chỉ để telemetry
    consecutive_parse_errors: int = 0   # reset mỗi lần parse tốt — cái lái gate
    _tool_calls: dict[str, int] = field(default_factory=dict)

    # ── StaticFactory ──
    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Budget":
        """Ngân sách mặc định, chỉnh được KHÔNG cần đổi code (núm vặn của orchestrator).

        Bản gốc đọc os.getenv; ở đây nhận dict để chạy độc lập — vẫn đúng vai StaticFactory.
        """
        env = env or {}
        return cls(
            max_steps=int(env.get("AGENT_MAX_STEPS", "30")),
            max_parse_errors=int(env.get("AGENT_MAX_PARSE_ERRORS", "8")),
            max_same_tool_calls=int(env.get("AGENT_MAX_SAME_TOOL", "3")),
        )

    # ── MutationPort ──
    def record_step(self) -> None:
        self.steps += 1
        self.consecutive_parse_errors = 0  # một step xong = model đã hồi phục

    def record_parse_error(self) -> None:
        self.parse_errors += 1
        self.consecutive_parse_errors += 1

    def record_parse_success(self) -> None:
        """Một action đúng dạng đã tới. Xoá streak lỗi liên tiếp ngay cả khi action không
        tiêu step (vd: một quyết định orchestrator trong supervisor loop)."""
        self.consecutive_parse_errors = 0

    def record_tool_call(self, key: str) -> int:
        self._tool_calls[key] = self._tool_calls.get(key, 0) + 1
        return self._tool_calls[key]

    # ── QueryPort ──
    def step_exceeded(self) -> bool:
        return self.steps > self.max_steps

    def parse_exceeded(self) -> bool:
        return self.consecutive_parse_errors >= self.max_parse_errors

    def same_tool_exceeded(self, key: str) -> bool:
        return self._tool_calls.get(key, 0) > self.max_same_tool_calls

    @staticmethod
    def tool_key(tool_name: str, args: dict[str, Any]) -> str:
        return tool_name + ":" + json.dumps(args, sort_keys=True, ensure_ascii=False)


# ============================================================================
# DEMO
# ============================================================================

def demo() -> None:
    print("=" * 72)
    print("SRP case 02 — Loop Budget Tracker (discipline/budget.py)")
    print("Actor DUY NHẤT: đội điều phối vòng lặp. Chỉ đếm & gác ngân sách.")
    print("=" * 72)

    # (1) StaticFactory: tiêm cấu hình qua 'env' giả, KHÔNG đổi code.
    b = Budget.from_env({"AGENT_MAX_STEPS": "5", "AGENT_MAX_SAME_TOOL": "2"})
    print(f"\n(1) from_env -> max_steps={b.max_steps}, max_same_tool={b.max_same_tool_calls}")
    assert b.max_steps == 5 and b.max_same_tool_calls == 2

    # (2) record_step 6 lần -> step_exceeded bật đúng tại step thứ 6 (vì > max_steps=5).
    print("\n(2) đếm step tới ngưỡng:")
    for i in range(1, 7):
        b.record_step()
        flag = b.step_exceeded()
        print(f"    step={b.steps}  step_exceeded={flag}")
        if i <= 5:
            assert not flag, f"chưa nên vượt ở step {b.steps}"
    assert b.step_exceeded(), "step 6 phải vượt max_steps=5"
    print("    -> bật tại step 6. PASS")

    # (3) consecutive parse error: 2 lỗi rồi 1 success -> streak reset về 0.
    print("\n(3) streak lỗi parse liên tiếp & reset:")
    b2 = Budget.from_env({"AGENT_MAX_PARSE_ERRORS": "3"})
    b2.record_parse_error()
    b2.record_parse_error()
    print(f"    sau 2 lỗi: consecutive={b2.consecutive_parse_errors}, lifetime={b2.parse_errors}, "
          f"parse_exceeded={b2.parse_exceeded()}")
    assert b2.consecutive_parse_errors == 2 and not b2.parse_exceeded()
    b2.record_parse_success()
    print(f"    sau 1 success: consecutive={b2.consecutive_parse_errors}, lifetime={b2.parse_errors}")
    assert b2.consecutive_parse_errors == 0, "success phải reset streak"
    assert b2.parse_errors == 2, "lifetime telemetry KHÔNG bị reset"
    print("    -> success reset streak nhưng giữ lifetime. PASS")

    # (4) tool_key + same_tool_exceeded: cùng tool+args lặp tới ngưỡng thì vượt.
    print("\n(4) chống lặp tool y hệt:")
    b3 = Budget.from_env({"AGENT_MAX_SAME_TOOL": "2"})
    key = Budget.tool_key("fs_read", {"path": "/a", "n": 1})
    same_key = Budget.tool_key("fs_read", {"n": 1, "path": "/a"})  # thứ tự args đảo
    assert key == same_key, "tool_key phải ổn định bất kể thứ tự args (sort_keys)"
    for _ in range(3):
        cnt = b3.record_tool_call(key)
        print(f"    gọi fs_read lần {cnt}, same_tool_exceeded={b3.same_tool_exceeded(key)}")
    assert b3.same_tool_exceeded(key), "gọi 3 lần với max=2 phải vượt"
    print("    -> tool_key chuẩn-hoá args; vượt tại lần thứ 3. PASS")

    # ---- ĐỐI CHỨNG: nếu trộn việc đếm ngân sách vào trong loop orchestrator (God) ----
    print("\n--- ĐỐI CHỨNG: nếu KHÔNG tách Budget mà nhét counter rải rác trong loop ---")
    print("  * Muốn test 'parse streak reset' phải dựng cả loop + LLM giả + tool giả.")
    print("  * Đổi quy tắc 'streak vs lifetime' phải mò trong file loop dài, dễ regress.")
    print("  Ở đây test toàn bộ hợp đồng Budget mà KHÔNG cần loop/LLM/tool nào.")

    print("\nKẾT: mọi field đều được >=1 method dùng (cohesion cao). Đổi luật ngân sách")
    print("chỉ đụng budget.py; orchestrator chỉ hỏi 'tôi vượt chưa?' và nhận bool.")


if __name__ == "__main__":
    demo()
