# -*- coding: utf-8 -*-
"""
Case 02 — SafeToolPort: Protection Proxy quanh tool executor

Bản DISTILL TRUNG THỰC của SafeToolPort trong hex_agent — ví dụ Proxy "một
class" rõ ràng nhất: cùng interface với RealSubject (.execute(request) -> dict),
giữ reference tới executor thật trong self._inner, chạy policy check TRƯỚC, rồi
hoặc trả về kết quả "blocked", hoặc DELEGATE nguyên vẹn cho self._inner.execute().

NGUỒN THẬT (đã mở file kiểm chứng):
  - safety/policy.py:13-18     SHELL_EXES / SHELL_TOKENS / DESTRUCTIVE_EXES / _ABS_PATH_RE
  - safety/policy.py:41-46     PolicyDecision (dataclass frozen)
  - safety/policy.py:53-71     classify_terminal — phân loại argv của terminal
  - safety/policy.py:77-102    ToolPolicy.check — cổng an toàn cross-cutting duy nhất
  - safety/policy.py:105-124   SafeToolPort — Protection Proxy: _inner + _policy, execute()
  - core/schemas.py:28-33      ToolRequest(name, args)

LƯỢC BỎ so với bản thật:
  - Bỏ kiểm tra path escape ngoài workspace (_argv_escapes_workspace) và git mutation
    để giữ ví dụ gọn; giữ lại shell-exe, shell-token, destructive làm minh hoạ chính.
  - Bỏ repair_mode / whole-file-write branch.
  - RealSubject (executor thật chạy lệnh) -> thay bằng EchoExecutor stdlib không
    chạm hệ thống thật.
  - Giữ NGUYÊN cấu trúc Proxy: cùng interface, _inner, pre-check policy, block-or-delegate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# ============================================================
# SUBJECT — ToolRequest (distill core/schemas.py:28-33)
# ============================================================
@dataclass(frozen=True)
class ToolRequest:
    name: str
    args: dict[str, Any]


# "Subject interface" ở đây là quy ước: mọi ToolPort có method
#   execute(request: ToolRequest) -> dict
# RealSubject và Proxy đều phơi ra ĐÚNG method này, cùng chữ ký.


# ============================================================
# Policy data + checker (distill safety/policy.py:13-18, 41-71, 77-102)
# ============================================================
SHELL_EXES = {"bash", "sh", "zsh", "cmd", "powershell", "pwsh"}
SHELL_TOKENS = ("|", "&", ";", ">", "<", "`", "$(", "&&", "||")
DESTRUCTIVE_EXES = {"rm", "del", "rmdir", "format", "mkfs", "dd"}


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str = ""
    code: str = ""
    risk: str = "low"


def classify_terminal(argv: Any) -> PolicyDecision:
    """distill safety/policy.py:53-71 — phân loại an toàn của một argv terminal."""
    if not isinstance(argv, list) or not argv:
        return PolicyDecision(False, "terminal requires a non-empty argv list", "bad_argv", "blocked")
    exe = str(argv[0]).replace("\\", "/").split("/")[-1].lower()
    if exe in SHELL_EXES:
        return PolicyDecision(False, "shell executables are not allowed; pass argv directly",
                              "shell_exe", "blocked")
    if any(tok in str(part) for part in argv for tok in SHELL_TOKENS):
        return PolicyDecision(False, "shell control/redirection tokens are not allowed",
                              "shell_token", "blocked")
    if exe in DESTRUCTIVE_EXES:
        return PolicyDecision(False, "destructive command blocked", "destructive", "blocked")
    return PolicyDecision(True, risk="low")


class ToolPolicy:
    """Cổng an toàn cross-cutting DUY NHẤT — distill safety/policy.py:77-102.
    Mở rộng ở đây, không rải rác từng server."""

    def check(self, tool_name: str, args: dict[str, Any]) -> PolicyDecision:
        if tool_name in {"terminal_run", "terminal.run", "terminal"}:
            return classify_terminal(args.get("argv"))
        return PolicyDecision(True)


# ============================================================
# REAL SUBJECT — executor "naive", không biết gì về policy
# (thay cho underlying tool executor ở bản thật)
# ============================================================
class EchoExecutor:
    """RealSubject: cứ nhận request là 'chạy'. KHÔNG có khái niệm an toàn.
    Đếm số lần thực thi để chứng minh proxy chặn TRƯỚC khi tới đây."""

    def __init__(self) -> None:
        self.name = "echo"
        self.executions: list[ToolRequest] = []

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        self.executions.append(request)
        return {"ok": True, "tool": request.name, "ran": True, "args": request.args}


# ============================================================
# PROXY — SafeToolPort (Protection Proxy) distill safety/policy.py:105-124
# ============================================================
class SafeToolPort:
    """Bọc một tool executor; chạy policy chokepoint TRƯỚC khi delegate.

    Đây là Proxy "sách giáo khoa":
      - cùng interface với RealSubject: method execute(request) -> dict
      - giữ reference tới real subject trong self._inner
      - pre-check (self._policy.check) -> block hoặc delegate self._inner.execute()
    """

    def __init__(self, name: str, inner: Any, policy: ToolPolicy | None = None) -> None:
        self.name = name
        self._inner = inner                    # reference tới RealSubject
        self._policy = policy or ToolPolicy()

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        decision = self._policy.check(request.name, request.args)   # pre-check
        if not decision.allowed:
            return {                                                # block: KHÔNG gọi _inner
                "ok": False,
                "tool": request.name,
                "policy_blocked": True,
                "policy_code": decision.code,
                "error": decision.reason,
                "metadata": {"risk": decision.risk},
            }
        return self._inner.execute(request)                         # delegate nguyên vẹn


# ============================================================
# DEMO
# ============================================================
def demo() -> None:
    print("=" * 64)
    print("CASE 02 — SafeToolPort: Protection Proxy (hex_agent)")
    print("=" * 64)

    real = EchoExecutor()
    safe = SafeToolPort("safe(echo)", real, ToolPolicy())

    print("\n[1] Lệnh terminal AN TOÀN (argv trực tiếp) -> đi qua proxy tới executor thật.")
    ok = safe.execute(ToolRequest("terminal_run", {"argv": ["python", "-V"]}))
    print("    ok =", ok["ok"], "| ran =", ok.get("ran"))
    assert ok["ok"] is True and ok["ran"] is True
    assert len(real.executions) == 1, "lệnh an toàn phải chạm tới RealSubject"
    print("    -> Client gọi SafeToolPort y như gọi executor thật (cùng interface).")

    print("\n[2] Lệnh dùng SHELL exe ('bash -c ...') -> bị chặn TRƯỚC khi tới executor.")
    blocked = safe.execute(ToolRequest("terminal_run", {"argv": ["bash", "-c", "echo hi"]}))
    print("    ok =", blocked["ok"], "| code =", blocked["policy_code"], "| error =", blocked["error"])
    assert blocked["ok"] is False and blocked["policy_code"] == "shell_exe"
    assert len(real.executions) == 1, "lệnh bị chặn KHÔNG được chạm RealSubject"
    print("    -> RealSubject vẫn chỉ chạy 1 lần: proxy là người gác cổng thật sự.")

    print("\n[3] Lệnh DESTRUCTIVE ('rm -rf') -> bị chặn bởi cùng policy chokepoint.")
    rm = safe.execute(ToolRequest("terminal_run", {"argv": ["rm", "-rf", "data"]}))
    print("    ok =", rm["ok"], "| code =", rm["policy_code"])
    assert rm["ok"] is False and rm["policy_code"] == "destructive"
    assert len(real.executions) == 1

    print("\n[4] Token redirection ('| ; > $(...)') -> chặn vì shell_token.")
    tok = safe.execute(ToolRequest("terminal_run", {"argv": ["cat", "f", ">", "out"]}))
    assert tok["ok"] is False and tok["policy_code"] == "shell_token"
    print("    code =", tok["policy_code"], "(injection bị bắt trước khi tới executor)")

    print("\n[5] Tool KHÔNG phải terminal -> policy cho qua, delegate bình thường.")
    other = safe.execute(ToolRequest("read_file", {"path": "a.txt"}))
    assert other["ok"] is True and other["ran"] is True
    print("    read_file.ok =", other["ok"], "(policy chỉ gác terminal_run)")

    # ----- ĐỐI CHỨNG: gọi thẳng RealSubject = BYPASS proxy -----
    print("\n[6] ĐỐI CHỨNG — 'bypass the proxy': gọi thẳng executor thật bỏ qua policy.")
    danger = real.execute(ToolRequest("terminal_run", {"argv": ["rm", "-rf", "/"]}))
    print("    real.execute('rm -rf /').ran =", danger["ran"], " <-- LỆNH HUỶ DIỆT ĐÃ CHẠY!")
    assert danger["ran"] is True  # RealSubject "naive" không kiểm tra gì cả
    print("    -> Bài học (12_Proxy.md mục III): để MỘT đường truy cập thẳng RealSubject")
    print("       = vô hiệu hoá Proxy. MỌI access phải đi qua SafeToolPort (encapsulation).")

    print("\nTẤT CẢ assert PASS. SafeToolPort chặn-trước / delegate-sau đúng pattern Proxy.")


if __name__ == "__main__":
    demo()
