"""
Case 01 — Event Storming ở quy mô control-plane: Event + Command + Registry
===========================================================================

Bản DISTILL TRUNG THỰC (chỉ dùng thư viện chuẩn Python 3) của cơ chế Event Storming
"đông cứng" trong hex_agent. Trong bài học gốc 38_EventStorming.md, kết quả của một
workshop là: glossary event past-tense (sticky orange), command imperative (sticky blue),
và "bức tường" buộc mọi người chỉ dùng đúng vocabulary đã thống nhất. hex_agent hiện
thực hoá đúng ba thứ đó trong code.

NGUỒN THẬT distill từ (đã mở & xác nhận line):
  - control/events.py:113-152      -> RuntimeEvent (envelope domain event, frozen + validate)
  - control/events.py:32-51        -> Actor(type, id) (ai gây ra event)
  - control/events.py:85-110       -> RedactionInfo(level,...) (phân lớp visibility)
  - control/events.py:193-212      -> SessionSeq (cấp seq tăng đơn điệu per-session)
  - control/commands.py:62-106     -> RuntimeCommand (envelope command, idempotency_key + issued_by)
  - control/commands.py:34-58      -> IssuedBy (attribution: ai phát command)
  - control/commands.py:156-166    -> parse_command (gate validate trước gateway)
  - control/event_registry.py:40-61   -> EventTypeRegistry.assert_known (reject event lạ)
  - control/command_registry.py:36-60 -> CommandTypeRegistry.assert_known (reject command lạ)
  - config/runtime_event_types.yaml:11-83   -> catalog 57 event (bức tường sticky orange)
  - config/runtime_command_types.yaml:9-36  -> catalog 16 command (sticky blue)
  - control/emitter.py:53-61       -> EventEmitter.emit_event (validate + seq + redact + fan-out)
  - control/redaction.py:65-73     -> Redactor.apply (che secret trước khi tới UI)

LƯỢC BỎ so với bản thật:
  - YAML thật thay bằng dict Python nhúng trong file (vẫn giữ ý "khai báo tập trung").
  - Bỏ trace_id/span_id, schema_version, datetime ISO -> dùng counter đơn giản.
  - Bỏ permission resolver thật + queue gateway thật -> chỉ minh hoạ reject ở mức registry.

Chạy: python3 control_plane_event_storming.py
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable


# =============================================================================
# [LỖI HỢP ĐỒNG] — tương ứng control.errors.ControlContractError
# =============================================================================
class ControlContractError(Exception):
    """Một event/command vi phạm hợp đồng (vd: event_type chưa khai báo trên 'tường')."""


# =============================================================================
# [BỨC TƯỜNG STICKY NOTE] — catalog declared tập trung
# control/events.py + config/runtime_event_types.yaml (bản thật là YAML)
# config/runtime_command_types.yaml
# =============================================================================
# Domain event = sticky ORANGE (past-tense fact). Mỗi event khai báo visibility +
# có phải checkpoint_candidate không. (Trích một phần của 57 event thật, nhóm theo
# bounded context ẩn để thấy rõ "discovery domain".)
EVENT_TYPES: dict[str, dict[str, Any]] = {
    # ── session lifecycle ──
    "session.started":     {"visibility": "ui_safe"},
    "session.paused":      {"visibility": "ui_safe"},
    "session.finished":    {"visibility": "ui_safe"},
    # ── agent lifecycle ──
    "agent.before_run":    {"visibility": "ui_safe"},
    "agent.after_run":     {"visibility": "ui_safe"},
    "agent.output.raw":    {"visibility": "internal"},   # thô, phải redact mạnh
    # ── tool lifecycle ──
    "tool.call_requested": {"visibility": "ui_safe", "checkpoint_candidate": True},
    "tool.after_call":     {"visibility": "ui_safe"},
    "tool.failed":         {"visibility": "ui_safe"},
    # ── permission / checkpoint ──
    "checkpoint.reached":  {"visibility": "ui_safe"},
    "approval.approved":   {"visibility": "ui_safe"},
    # ── command lifecycle ──
    "command.received":    {"visibility": "ui_safe"},
    "command.rejected":    {"visibility": "ui_safe"},
}

# Command = sticky BLUE (imperative). Mỗi command khai báo apply_at + permission cần.
COMMAND_TYPES: dict[str, dict[str, Any]] = {
    "PauseWorkflow":     {"apply_at": "next_checkpoint",      "requires_permission": None},
    "ResumeWorkflow":    {"apply_at": "next_checkpoint",      "requires_permission": None},
    "StopAgentTurn":     {"apply_at": "immediate",           "requires_permission": None},
    "SubmitPrompt":      {"apply_at": "next_checkpoint",      "requires_permission": None},
    "ApproveCheckpoint": {"apply_at": "immediate_if_waiting", "requires_permission": "checkpoint.approve"},
    "RejectCheckpoint":  {"apply_at": "immediate_if_waiting", "requires_permission": "checkpoint.reject"},
}

VISIBILITY_LEVELS = frozenset({"public", "ui_safe", "internal", "secret", "restricted"})
ACTOR_TYPES = frozenset({"human", "agent", "tool", "system", "runtime"})
ISSUER_TYPES = frozenset({"human", "agent", "system"})


# =============================================================================
# [REGISTRY] — gate "chỉ vocabulary đã thống nhất mới được dùng"
# control/event_registry.py:40-61 ; control/command_registry.py:36-60
# =============================================================================
class EventTypeRegistry:
    """Bức tường event: event_type chưa khai báo => bị reject ngay (assert_known)."""

    def __init__(self, specs: dict[str, dict[str, Any]]) -> None:
        self._specs = dict(specs)

    def __contains__(self, event_type: str) -> bool:
        return event_type in self._specs

    def assert_known(self, event_type: str) -> None:
        if event_type not in self._specs:
            raise ControlContractError(
                f"event_type chua khai bao: {event_type!r}. Hay khai trong EVENT_TYPES (tuong yaml)."
            )

    def visibility(self, event_type: str) -> str:
        self.assert_known(event_type)
        return self._specs[event_type].get("visibility", "ui_safe")

    def types(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))


class CommandTypeRegistry:
    """Bức tường command: command_type chưa khai báo => reject ở gateway."""

    def __init__(self, specs: dict[str, dict[str, Any]]) -> None:
        self._specs = dict(specs)

    def __contains__(self, command_type: str) -> bool:
        return command_type in self._specs

    def assert_known(self, command_type: str) -> None:
        if command_type not in self._specs:
            raise ControlContractError(
                f"command_type chua khai bao: {command_type!r}. Hay khai trong COMMAND_TYPES."
            )

    def requires_permission(self, command_type: str) -> str | None:
        self.assert_known(command_type)
        return self._specs[command_type].get("requires_permission")

    def types(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))


# =============================================================================
# [ENVELOPE] — RuntimeEvent (orange) + RuntimeCommand (blue)
# control/events.py:113-152 ; control/commands.py:62-106
# Frozen + validate trong __post_init__: event/command SAI không thể tồn tại.
# =============================================================================
@dataclass(frozen=True)
class Actor:
    """Ai/cái gì gây ra event. control/events.py:32-51 — sticky yellow (actor)."""
    type: str
    id: str

    def __post_init__(self) -> None:
        if self.type not in ACTOR_TYPES:
            raise ControlContractError(f"Actor.type phai thuoc {sorted(ACTOR_TYPES)}, gap {self.type!r}.")
        if not self.id:
            raise ControlContractError("Actor.id khong duoc rong.")


@dataclass(frozen=True)
class IssuedBy:
    """Ai phát command — ATTRIBUTION (audit), KHÔNG phải authz. control/commands.py:34-58."""
    type: str
    user_id: str | None = None
    agent_id: str | None = None

    def __post_init__(self) -> None:
        if self.type not in ISSUER_TYPES:
            raise ControlContractError(f"IssuedBy.type phai thuoc {sorted(ISSUER_TYPES)}, gap {self.type!r}.")
        if self.type == "human" and not self.user_id:
            raise ControlContractError("IssuedBy(type='human') can co user_id.")


@dataclass(frozen=True)
class RuntimeEvent:
    """Domain event bất biến (sticky orange). control/events.py:113-152.

    seq=0 nghĩa là 'chưa được emitter đóng dấu'. ui_payload=None tới khi Redactor điền.
    """
    event_type: str
    session_id: str
    actor: Actor
    payload: dict[str, Any] = field(default_factory=dict)
    visibility: str = "ui_safe"
    seq: int = 0
    ui_payload: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.event_type:
            raise ControlContractError("RuntimeEvent.event_type bat buoc.")
        if not self.session_id:
            raise ControlContractError("RuntimeEvent.session_id bat buoc.")
        if not isinstance(self.actor, Actor):
            raise ControlContractError("RuntimeEvent.actor phai la Actor.")
        if self.seq < 0:
            raise ControlContractError("RuntimeEvent.seq phai >= 0.")


@dataclass(frozen=True)
class RuntimeCommand:
    """Command imperative (sticky blue). control/commands.py:62-106.

    idempotency_key chống double-apply; issued_by ghi ai phát (attribution).
    """
    command_type: str
    session_id: str
    issued_by: IssuedBy
    idempotency_key: str
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("command_type", "session_id", "idempotency_key"):
            if not getattr(self, name):
                raise ControlContractError(f"RuntimeCommand.{name} bat buoc, khong duoc rong.")
        if not isinstance(self.issued_by, IssuedBy):
            raise ControlContractError("RuntimeCommand.issued_by phai la IssuedBy.")


def parse_command(data: dict[str, Any]) -> RuntimeCommand:
    """Gate validate command thô trước khi vào gateway. control/commands.py:156-166.
    Thiếu idempotency_key/issued_by => raise để gateway reject + emit command.rejected."""
    if not isinstance(data, dict):
        raise ControlContractError("Command phai la mapping.")
    if not data.get("idempotency_key"):
        raise ControlContractError("Command thieu 'idempotency_key' khong rong.")
    if not isinstance(data.get("issued_by"), dict):
        raise ControlContractError("Command thieu doi tuong 'issued_by'.")
    return RuntimeCommand(
        command_type=str(data.get("command_type", "")),
        session_id=str(data.get("session_id", "")),
        issued_by=IssuedBy(**data["issued_by"]),
        idempotency_key=str(data["idempotency_key"]),
        payload=dict(data.get("payload") or {}),
    )


# =============================================================================
# [REDACTOR] — biên an toàn secret trước khi tới UI
# control/redaction.py:65-73
# =============================================================================
SECRET_KEYS = frozenset({"api_key", "token", "password", "secret", "authorization"})
REDACTED = "[REDACTED]"


def redact(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Trả (ui_payload đã che, has_secret). Không mutate payload gốc."""
    out: dict[str, Any] = {}
    has_secret = False
    for key, value in payload.items():
        if key.lower() in SECRET_KEYS:
            out[key] = REDACTED
            has_secret = True
        else:
            out[key] = value
    return out, has_secret


# =============================================================================
# [SessionSeq] — cấp seq tăng đơn điệu per-session. control/events.py:193-212
# =============================================================================
class SessionSeq:
    def __init__(self) -> None:
        self._counters: dict[str, int] = {}

    def next(self, session_id: str) -> int:
        value = self._counters.get(session_id, 0) + 1
        self._counters[session_id] = value
        return value


# =============================================================================
# [FACILITATOR] — EventEmitter: đường publish DUY NHẤT đã validate
# control/emitter.py:53-61
# 1) check registry  2) stamp seq  3) redact ui_payload  4) fan-out tới sinks
# =============================================================================
EventSink = Callable[[RuntimeEvent], None]


class EventEmitter:
    def __init__(self, registry: EventTypeRegistry, sinks: list[EventSink]) -> None:
        self._registry = registry
        self._sinks = list(sinks)
        self._seq = SessionSeq()

    def emit_event(self, event: RuntimeEvent) -> RuntimeEvent:
        # (1) GATE: event_type lạ -> reject TRƯỚC khi publish bất cứ thứ gì.
        self._registry.assert_known(event.event_type)
        visibility = self._registry.visibility(event.event_type)
        # (2) stamp seq nếu chưa có
        staged = event if event.seq else replace(event, seq=self._seq.next(event.session_id))
        # (3) redact ui_payload theo visibility
        ui_payload, _ = redact(staged.payload)
        final = replace(staged, ui_payload=ui_payload, visibility=visibility)
        # (4) fan-out
        for sink in self._sinks:
            sink(final)
        return final


# =============================================================================
# [GATEWAY] — nơi command đi vào: validate + check registry
# (distill của control/commands.py:156-166 + command_registry, ở quy mô nhỏ)
# =============================================================================
class CommandGateway:
    def __init__(self, registry: CommandTypeRegistry, emitter: EventEmitter) -> None:
        self._registry = registry
        self._emitter = emitter
        self._seen_keys: set[str] = set()

    def submit(self, data: dict[str, Any]) -> str:
        """Trả 'received' nếu chấp nhận, raise ControlContractError nếu reject.
        Mọi nhánh đều emit event tương ứng — vì 'command đã được xử lý' cũng là một fact."""
        cmd = parse_command(data)  # có thể raise (thiếu idempotency_key/issued_by)
        # GATE: command lạ -> reject ở gateway + emit command.rejected
        if cmd.command_type not in self._registry:
            self._emitter.emit_event(RuntimeEvent(
                event_type="command.rejected",
                session_id=cmd.session_id,
                actor=Actor("system", "gateway"),
                payload={"command_type": cmd.command_type, "reason": "unknown_command_type"},
            ))
            raise ControlContractError(f"command_type bi tu choi o gateway: {cmd.command_type!r}.")
        # idempotency: cùng key lần 2 -> bỏ qua, không apply lần nữa
        if cmd.idempotency_key in self._seen_keys:
            return "duplicate_ignored"
        self._seen_keys.add(cmd.idempotency_key)
        self._emitter.emit_event(RuntimeEvent(
            event_type="command.received",
            session_id=cmd.session_id,
            actor=Actor(cmd.issued_by.type, cmd.issued_by.user_id or cmd.issued_by.agent_id or "?"),
            payload={"command_type": cmd.command_type, **cmd.payload},
        ))
        return "received"


# =============================================================================
# DEMO
# =============================================================================
def demo() -> None:
    print("=" * 74)
    print("CASE 01 — EVENT STORMING O QUY MO CONTROL-PLANE (hex_agent E21)")
    print("=" * 74)

    event_reg = EventTypeRegistry(EVENT_TYPES)
    cmd_reg = CommandTypeRegistry(COMMAND_TYPES)

    # ---- Bước 1: "bức tường sticky note" — discovery domain ----
    print("\n[1] BUC TUONG STICKY NOTE — vocabulary domain da khai bao tap trung")
    print("    Domain EVENT (sticky orange, past-tense fact):")
    # nhóm theo bounded context ẩn (tiền tố trước dấu chấm)
    by_ctx: dict[str, list[str]] = {}
    for et in event_reg.types():
        by_ctx.setdefault(et.split(".")[0], []).append(et)
    for ctx, evs in by_ctx.items():
        print(f"      [bounded context an: {ctx:11s}] {', '.join(evs)}")
    print(f"    -> {len(event_reg.types())} event (ban that: 57). Day la 'discovery domain' dong cung vao code.")
    print("    Domain COMMAND (sticky blue, imperative):")
    for ct in cmd_reg.types():
        perm = cmd_reg.requires_permission(ct)
        print(f"      {ct:18s} requires_permission={perm}")

    # ---- Bước 2: facilitator (emitter) — publish event hợp lệ ----
    print("\n[2] FACILITATOR (EventEmitter): validate + stamp seq + redact + fan-out")
    log: list[RuntimeEvent] = []
    emitter = EventEmitter(event_reg, sinks=[log.append])

    e1 = emitter.emit_event(RuntimeEvent(
        event_type="session.started",
        session_id="sess-1",
        actor=Actor("human", "alice"),
        payload={"goal": "viet bao cao Q4"},
    ))
    e2 = emitter.emit_event(RuntimeEvent(
        event_type="agent.before_run",
        session_id="sess-1",
        actor=Actor("agent", "writer"),
        payload={"prompt": "soan dan y", "api_key": "sk-SUPER-SECRET"},  # cố tình nhét secret
    ))
    for e in (e1, e2):
        print(f"      emit {e.event_type:18s} seq={e.seq} visibility={e.visibility} ui_payload={e.ui_payload}")
    print("    -> Secret 'api_key' da bi che thanh [REDACTED] trong ui_payload (Redactor).")

    # ---- Bước 3: command đi qua gateway ----
    print("\n[3] COMMAND qua GATEWAY: chi command DA KHAI BAO moi duoc nhan")
    gw = CommandGateway(cmd_reg, emitter)
    status = gw.submit({
        "command_type": "PauseWorkflow",
        "session_id": "sess-1",
        "issued_by": {"type": "human", "user_id": "alice"},
        "idempotency_key": "k-1",
    })
    print(f"      submit PauseWorkflow -> {status}  (emit command.received)")
    # idempotency: gửi lại cùng key
    status_dup = gw.submit({
        "command_type": "PauseWorkflow",
        "session_id": "sess-1",
        "issued_by": {"type": "human", "user_id": "alice"},
        "idempotency_key": "k-1",
    })
    print(f"      submit lai cung idempotency_key=k-1 -> {status_dup}  (khong apply lan 2)")

    # ---- Bước 4: ĐỐI CHỨNG — khi KHÔNG có registry (không có 'bức tường') ----
    print("\n[4] DOI CHUNG: khi KHONG dung registry, term tu phat bi lot luoi")
    print("    (a) Emit event LA 'sessionn.startd' (go nham) -> bi tu choi:")
    try:
        emitter.emit_event(RuntimeEvent(
            event_type="sessionn.startd",   # typo của session.started
            session_id="sess-1",
            actor=Actor("human", "alice"),
        ))
        print("      !!! da publish event go nham — DOMAIN VOCABULARY bi o nhiem")
    except ControlContractError as exc:
        print(f"      OK bi chan: {exc}")
    print("    (b) Submit COMMAND la 'DeleteEverything' -> gateway reject + emit command.rejected:")
    try:
        gw.submit({
            "command_type": "DeleteEverything",
            "session_id": "sess-1",
            "issued_by": {"type": "human", "user_id": "mallory"},
            "idempotency_key": "k-evil",
        })
    except ControlContractError as exc:
        print(f"      OK bi chan: {exc}")
    print("    (c) Submit command THIEU idempotency_key -> bi reject ngay tu parse:")
    try:
        gw.submit({
            "command_type": "PauseWorkflow",
            "session_id": "sess-1",
            "issued_by": {"type": "human", "user_id": "alice"},
        })
    except ControlContractError as exc:
        print(f"      OK bi chan: {exc}")

    # ---- Bước 5: asserts chứng minh bất biến của pattern ----
    print("\n[5] ASSERT — bat bien cua pattern")

    # (i) seq tăng đơn điệu trong cùng session
    seqs = [e.seq for e in log if e.session_id == "sess-1"]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs), "seq phai tang don dieu, khong trung"
    assert seqs == list(range(1, len(seqs) + 1)), f"seq phai 1..n lien tuc, gap {seqs}"
    print(f"      (i) seq tang don dieu lien tuc per-session: {seqs}  -> OK")

    # (ii) mọi event trong log đều thuộc vocabulary đã khai báo
    assert all(e.event_type in event_reg for e in log), "co event lot luoi ngoai registry"
    print("      (ii) moi event trong log deu nam trong registry (vocabulary dong)  -> OK")

    # (iii) secret không bao giờ rò vào ui_payload
    for e in log:
        for k, v in (e.ui_payload or {}).items():
            if k.lower() in SECRET_KEYS:
                assert v == REDACTED, f"secret {k} ro ra UI!"
    print("      (iii) khong secret nao ro vao ui_payload  -> OK")

    # (iv) command bị reject vẫn để lại fact 'command.rejected' (audit trail)
    rejected = [e for e in log if e.event_type == "command.rejected"]
    assert len(rejected) == 1, "command bi reject phai de lai dung 1 fact command.rejected"
    print("      (iv) command bi reject van de lai fact 'command.rejected' (audit)  -> OK")

    print("\n" + "=" * 74)
    print("KET LUAN: Registry = 'buc tuong sticky note' ep vocabulary domain;")
    print("Emitter = facilitator validate+seq+redact; Command/Event tach bach ro rang.")
    print("Khong co buc tuong -> term tu phat o nhiem domain, khong replay/audit duoc.")
    print("=" * 74)


if __name__ == "__main__":
    demo()
