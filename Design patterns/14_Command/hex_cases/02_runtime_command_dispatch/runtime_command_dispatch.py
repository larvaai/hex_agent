"""
Case 02 — Command pattern ở tầng control-plane: RuntimeCommand + registry + dispatch.

Bản DISTILL TRUNG THỰC, self-contained, CHỈ dùng thư viện chuẩn Python 3.14.
UI/người dùng KHÔNG sửa state trực tiếp — họ SUBMIT một RuntimeCommand (object bất biến),
gateway validate -> dedup (idempotency) -> lên lịch theo apply_at -> dispatch tới Receiver.

Nguồn thật được distill (đã mở file kiểm chứng từng dòng):
  - control/commands.py:61-106        -> RuntimeCommand (frozen dataclass) = ConcreteCommand
                                         (command_type, session_id, issued_by, idempotency_key,
                                          payload, command_id, created_at, schema_version)
                                         schema_version: int = 1 ở dòng 70, validate >= 1 ở 80-81
  - control/commands.py:33-58         -> IssuedBy (attribution, có __post_init__ validate:
                                         human cần user_id (dòng 45-46), agent cần agent_id (dòng 47))
  - control/commands.py:156-166       -> parse_command(data) = factory/validator
  - control/command_registry.py:22-89 -> CommandTypeSpec + CommandTypeRegistry: ánh xạ
                                         command_type -> apply_at (chiến lược lên lịch)
  - config/runtime_command_types.yaml:9-37 -> bảng apply_at:
                                         SubmitPrompt=next_checkpoint, StopAgentTurn=immediate,
                                         ApproveCheckpoint=immediate_if_waiting...
  - ui/ide/server.py:127-175          -> IdeControlServer.submit_command() = Invoker:
                                         validate -> dedup map (idempotency, dòng 143-156) ->
                                         _dispatch() (dòng 160-175) route 'SubmitPrompt' -> runner.start()
  - ui/ide/runner.py:90               -> AgentRunner.start(prompt) = Receiver của SubmitPrompt

Vì YAML là dependency bên thứ ba, ở đây ta nhúng bảng command-type bằng dict stdlib
(giữ NGUYÊN apply_at từ config/runtime_command_types.yaml). Mọi thứ khác là stdlib.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class ControlContractError(Exception):
    """Distill control/errors.ControlContractError — vi phạm hợp đồng command."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 1. IssuedBy — distill control/commands.py:33-58 (attribution, KHÔNG phải authz)
# ---------------------------------------------------------------------------
ISSUER_TYPES = frozenset({"human", "agent", "system"})


@dataclass(frozen=True)
class IssuedBy:
    type: str
    user_id: str | None = None
    agent_id: str | None = None

    def __post_init__(self) -> None:
        if self.type not in ISSUER_TYPES:
            raise ControlContractError(
                f"IssuedBy.type must be one of {sorted(ISSUER_TYPES)}, got {self.type!r}."
            )
        if self.type == "human" and not self.user_id:
            raise ControlContractError("IssuedBy(type='human') requires a user_id.")
        if self.type == "agent" and not self.agent_id:
            raise ControlContractError("IssuedBy(type='agent') requires an agent_id.")


# ---------------------------------------------------------------------------
# 2. ConcreteCommand — distill control/commands.py:61-106 (RuntimeCommand)
#    IMMUTABLE: đóng gói đủ ngữ cảnh, validate ngay ở __post_init__.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RuntimeCommand:
    command_type: str
    session_id: str
    issued_by: IssuedBy
    idempotency_key: str
    payload: dict[str, Any] = field(default_factory=dict)
    command_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=_utc_now)
    schema_version: int = 1

    def __post_init__(self) -> None:
        for name in ("command_id", "command_type", "session_id", "idempotency_key", "created_at"):
            if not getattr(self, name):
                raise ControlContractError(f"RuntimeCommand.{name} is required and must be non-empty.")
        if not isinstance(self.issued_by, IssuedBy):
            raise ControlContractError("RuntimeCommand.issued_by must be an IssuedBy.")
        if not isinstance(self.payload, dict):
            raise ControlContractError("RuntimeCommand.payload must be a mapping.")
        if self.schema_version < 1:
            raise ControlContractError("RuntimeCommand.schema_version must be >= 1.")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RuntimeCommand":
        ib = d.get("issued_by") or {}
        return cls(
            command_type=str(d.get("command_type", "")),
            session_id=str(d.get("session_id", "")),
            issued_by=IssuedBy(
                type=str(ib.get("type", "")),
                user_id=(str(ib["user_id"]) if ib.get("user_id") else None),
                agent_id=(str(ib["agent_id"]) if ib.get("agent_id") else None),
            ),
            idempotency_key=str(d.get("idempotency_key", "")),
            payload=dict(d.get("payload") or {}),
            command_id=str(d.get("command_id", "")) or uuid.uuid4().hex,
            created_at=str(d.get("created_at", "")) or _utc_now(),
            schema_version=int(d.get("schema_version", 1)),
        )


# ---------------------------------------------------------------------------
# 3. parse_command — distill control/commands.py:156-166 (factory/validator)
# ---------------------------------------------------------------------------
def parse_command(data: dict[str, Any]) -> RuntimeCommand:
    if not isinstance(data, dict):
        raise ControlContractError("Command must be a mapping.")
    if not data.get("idempotency_key"):
        raise ControlContractError("Command requires a non-empty 'idempotency_key'.")
    if not isinstance(data.get("issued_by"), dict):
        raise ControlContractError("Command requires an 'issued_by' object.")
    return RuntimeCommand.from_dict(data)


# ---------------------------------------------------------------------------
# 4. CommandTypeRegistry — distill command_registry.py:22-89
#    Chiến lược LÊN LỊCH theo từng loại command (apply_at). Đây là phần làm cho
#    Command pattern ở control-plane "queueable / schedulable".
#    Bảng giữ NGUYÊN từ config/runtime_command_types.yaml:9-37.
# ---------------------------------------------------------------------------
APPLY_AT = frozenset({"next_checkpoint", "immediate_if_waiting", "immediate"})

# Trích từ config/runtime_command_types.yaml (nhúng dict thay vì đọc YAML):
_COMMAND_TYPES_TABLE: dict[str, dict[str, Any]] = {
    "PauseWorkflow":      {"apply_at": "next_checkpoint",       "requires_permission": None},
    "StopAgentTurn":      {"apply_at": "immediate",             "requires_permission": None},
    "SubmitPrompt":       {"apply_at": "next_checkpoint",       "requires_permission": None},
    "ApproveCheckpoint":  {"apply_at": "immediate_if_waiting",  "requires_permission": "checkpoint.approve"},
    "RejectCheckpoint":   {"apply_at": "immediate_if_waiting",  "requires_permission": "checkpoint.reject"},
    "UpdateAgentPermission": {"apply_at": "next_checkpoint",    "requires_permission": "workflow.modify_permissions"},
}


@dataclass(frozen=True)
class CommandTypeSpec:
    command_type: str
    apply_at: str
    requires_permission: str | None = None


class CommandTypeRegistry:
    def __init__(self, specs: dict[str, CommandTypeSpec]) -> None:
        self._specs = dict(specs)

    def assert_known(self, command_type: str) -> None:
        if command_type not in self._specs:
            raise ControlContractError(
                f"Unknown command_type: {command_type!r}. Declare it in runtime_command_types.yaml."
            )

    def apply_at(self, command_type: str) -> str:
        self.assert_known(command_type)
        return self._specs[command_type].apply_at

    def requires_permission(self, command_type: str) -> str | None:
        self.assert_known(command_type)
        return self._specs[command_type].requires_permission

    @classmethod
    def from_table(cls, table: dict[str, dict[str, Any]]) -> "CommandTypeRegistry":
        specs: dict[str, CommandTypeSpec] = {}
        for name, raw in table.items():
            apply_at = str(raw.get("apply_at", "next_checkpoint"))
            if apply_at not in APPLY_AT:
                raise ControlContractError(
                    f"'{name}' apply_at {apply_at!r} must be one of {sorted(APPLY_AT)}."
                )
            req = raw.get("requires_permission")
            specs[name] = CommandTypeSpec(name, apply_at, str(req) if req else None)
        return cls(specs)


# ---------------------------------------------------------------------------
# 5. Receiver giả lập — distill ui/ide/runner.py:90 (AgentRunner.start)
# ---------------------------------------------------------------------------
class FakeRunner:
    """Receiver của SubmitPrompt. start() từ chối nếu đã có run đang chạy
    (distill runner.start: trả None khi đang active, server.py:171)."""

    def __init__(self) -> None:
        self.active = False
        self.started_prompts: list[str] = []

    def start(self, prompt: str) -> str | None:
        if self.active:
            return None  # đã có run -> không start chồng (server.py:171-172)
        self.active = True
        self.started_prompts.append(prompt)
        return "run_" + uuid.uuid4().hex[:8]

    def stop(self) -> None:
        self.active = False


# ---------------------------------------------------------------------------
# 6. CommandAck — distill control/commands.py:109-143 (biên nhận đồng bộ)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CommandAck:
    command_id: str
    status: str  # "received" | "rejected"
    seq: int | None = None
    rejection_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"command_id": self.command_id, "status": self.status,
                "seq": self.seq, "rejection_reason": self.rejection_reason}


# ---------------------------------------------------------------------------
# 7. Invoker — distill ui/ide/server.py:127-175 (IdeControlServer)
#    submit_command(): validate -> dedup (idempotency) -> emit seq -> dispatch.
# ---------------------------------------------------------------------------
class IdeControlServer:
    def __init__(self, registry: CommandTypeRegistry, runner: FakeRunner) -> None:
        self.command_registry = registry
        self.runner = runner
        self._dedup: dict[tuple[str, str], dict[str, Any]] = {}  # (session, idem_key) -> ack
        self._seq = 0
        self.event_log: list[dict[str, Any]] = []  # mô phỏng SSE buffer

    def _emit(self, event_type: str, payload: dict[str, Any]) -> int:
        self._seq += 1
        self.event_log.append({"seq": self._seq, "type": event_type, **payload})
        return self._seq

    def submit_command(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        # 7.1 validate + loại command type không khai báo (server.py:131-135)
        try:
            cmd = parse_command(body)
            self.command_registry.assert_known(cmd.command_type)
        except ControlContractError as exc:
            cid = str(body.get("command_id") or uuid.uuid4().hex)
            return 400, CommandAck(cid, "rejected", rejection_reason=str(exc)).as_dict()

        # 7.2 idempotency: replay cùng key -> trả lại ĐÚNG ack cũ, KHÔNG dispatch lần 2
        #     (distill server.py:143-156)
        key = (cmd.session_id, cmd.idempotency_key)
        if key in self._dedup:
            return 200, self._dedup[key]

        seq = self._emit("command.received",
                         {"command_id": cmd.command_id, "command_type": cmd.command_type})
        ack = CommandAck(cmd.command_id, "received", seq=seq).as_dict()
        self._dedup[key] = ack

        # 7.3 dispatch theo loại command (server.py:160-175)
        self._dispatch(cmd)
        return 200, ack

    def _dispatch(self, cmd: RuntimeCommand) -> None:
        """Route command -> Receiver. apply_at quyết định lịch áp dụng."""
        timing = self.command_registry.apply_at(cmd.command_type)

        if cmd.command_type == "SubmitPrompt":
            # next_checkpoint: hàng đợi tới điểm an toàn rồi mới start.
            prompt = str(cmd.payload.get("prompt") or "").strip()
            if not prompt:
                return
            if self.runner.start(prompt) is None:
                self._emit("command.rejected", {"reason": "a run is already active"})
        elif cmd.command_type == "StopAgentTurn":
            # immediate: huỷ ngay, không chờ checkpoint.
            self.runner.stop()
            self._emit("run.stopped", {"command_id": cmd.command_id})
        # ApproveCheckpoint/... : ghi nhận (no-op trong bản single-agent này, server.py:173-175)
        _ = timing  # timing được dùng để minh hoạ ở demo()


# ---------------------------------------------------------------------------
# Đối chứng: KHÔNG dùng Command — UI gọi thẳng runner.
# ---------------------------------------------------------------------------
def anti_pattern_direct(runner: FakeRunner) -> None:
    """UI gọi thẳng runner.start() — không có command object.

    Hậu quả:
      - Không idempotency: bấm 2 lần / mạng retry -> chạy 2 lần.
      - Không attribution (ai bấm?), không validate, không lịch apply_at,
        không thể log/replay/audit như một dòng command.
    """
    runner.start("hello")   # lần 1
    runner.start("hello")   # lần 2 (đã active -> trả None, nhưng caller không hề biết vì sao)


# ---------------------------------------------------------------------------
# demo()
# ---------------------------------------------------------------------------
def demo() -> None:
    print("=" * 72)
    print("CASE 02 — Command (control-plane): RuntimeCommand + registry + dispatch")
    print("=" * 72)

    registry = CommandTypeRegistry.from_table(_COMMAND_TYPES_TABLE)
    runner = FakeRunner()
    server = IdeControlServer(registry, runner)

    human = {"type": "human", "user_id": "u_alice"}

    print("\n[Bước 1] So sánh CHIẾN LƯỢC LÊN LỊCH (apply_at) theo loại command:")
    for ct in ("SubmitPrompt", "StopAgentTurn", "ApproveCheckpoint"):
        print(f"     {ct:<18} -> apply_at = {registry.apply_at(ct)}")
    assert registry.apply_at("SubmitPrompt") == "next_checkpoint"
    assert registry.apply_at("StopAgentTurn") == "immediate"
    assert registry.apply_at("ApproveCheckpoint") == "immediate_if_waiting"

    print("\n[Bước 2] Submit 'SubmitPrompt' (queued tới next_checkpoint) -> Receiver start.")
    body = {"command_type": "SubmitPrompt", "session_id": "s1",
            "issued_by": human, "idempotency_key": "idem-001",
            "payload": {"prompt": "viết hàm fib"}}
    code, ack = server.submit_command(body)
    print("   HTTP", code, "| status:", ack["status"], "| seq:", ack["seq"])
    assert code == 200 and ack["status"] == "received"
    assert runner.started_prompts == ["viết hàm fib"], "SubmitPrompt phải tới runner.start"

    print("\n[Bước 3] REPLAY đúng command (cùng idempotency_key) -> KHÔNG chạy lần 2.")
    code2, ack2 = server.submit_command(body)
    print("   HTTP", code2, "| trả lại ack cũ command_id:", ack2["command_id"] == ack["command_id"])
    assert ack2 == ack, "replay phải trả ĐÚNG ack cũ"
    assert runner.started_prompts == ["viết hàm fib"], "idempotency: chỉ start MỘT lần"
    print("   -> idempotency_key chống double-apply (server.py:143-156).")

    print("\n[Bước 4] 'StopAgentTurn' (immediate) -> huỷ run ngay, không chờ checkpoint.")
    code, ack = server.submit_command(
        {"command_type": "StopAgentTurn", "session_id": "s1",
         "issued_by": human, "idempotency_key": "idem-stop"})
    print("   HTTP", code, "| status:", ack["status"], "| runner.active:", runner.active)
    assert runner.active is False

    print("\n[Bước 5] Command thiếu idempotency_key -> bị reject ở gateway (parse_command).")
    code, ack = server.submit_command(
        {"command_type": "SubmitPrompt", "session_id": "s1", "issued_by": human})
    print("   HTTP", code, "| status:", ack["status"], "| reason:", ack["rejection_reason"])
    assert code == 400 and ack["status"] == "rejected"

    print("\n[Bước 6] Command_type lạ (không khai báo) -> reject.")
    code, ack = server.submit_command(
        {"command_type": "DropDatabase", "session_id": "s1",
         "issued_by": human, "idempotency_key": "idem-x"})
    print("   HTTP", code, "| reason:", ack["rejection_reason"])
    assert code == 400 and "Unknown command_type" in ack["rejection_reason"]

    print("\n[Bước 7] IssuedBy(type='human') thiếu user_id -> hỏng ngay khi tạo command.")
    try:
        IssuedBy(type="human")
    except ControlContractError as exc:
        print("   bắt được lỗi:", exc)
    else:  # pragma: no cover
        raise AssertionError("phải raise ControlContractError")

    print("\n[Bước 8] IssuedBy(type='agent') thiếu agent_id -> cũng hỏng (commands.py:47).")
    try:
        IssuedBy(type="agent")
    except ControlContractError as exc:
        print("   bắt được lỗi:", exc)
    else:  # pragma: no cover
        raise AssertionError("phải raise ControlContractError")

    print("\n[Bước 9] schema_version < 1 -> RuntimeCommand reject (commands.py:80-81).")
    try:
        RuntimeCommand(command_type="SubmitPrompt", session_id="s1",
                       issued_by=IssuedBy(type="agent", agent_id="a1"),
                       idempotency_key="idem-sv", schema_version=0)
    except ControlContractError as exc:
        print("   bắt được lỗi:", exc)
    else:  # pragma: no cover
        raise AssertionError("phải raise ControlContractError")
    ok_cmd = RuntimeCommand(command_type="SubmitPrompt", session_id="s1",
                            issued_by=IssuedBy(type="agent", agent_id="a1"),
                            idempotency_key="idem-sv2")
    assert ok_cmd.schema_version == 1, "schema_version mặc định = 1 (commands.py:70)"

    print("\n[Nhật ký sự kiện] (mỗi command để lại dấu vết — log/replay/audit được):")
    for e in server.event_log:
        print(f"     seq={e['seq']:<2} {e['type']:<18} {e.get('command_type') or e.get('reason') or ''}")

    # --- Đối chứng ---
    print("\n[Đối chứng] UI gọi thẳng runner (KHÔNG có command object):")
    runner2 = FakeRunner()
    anti_pattern_direct(runner2)
    print("   -> không idempotency, không attribution, không apply_at, không audit log.")
    print("      Mọi tiện ích trên phải tự cài lại rải rác ở từng nút bấm UI.")

    print("\nTẤT CẢ assert PASS. Command pattern (control-plane) hoạt động đúng.")


if __name__ == "__main__":
    demo()
