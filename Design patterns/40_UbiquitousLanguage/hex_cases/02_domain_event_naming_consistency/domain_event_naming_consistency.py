"""domain_event_naming_consistency.py — Event đặt tên bằng Ubiquitous Language.

Bản DISTILL TRUNG THỰC của cách hex_agent đặt tên event/metadata theo NGÔN NGỮ
NGHIỆP VỤ (Published Language) thay vì jargon kỹ thuật. Một business expert đọc
`loop.team_composed` hiểu ngay; đọc `agent_array_built` thì không.

NGUỒN THẬT distill từ (đã mở file xác minh path:line):
  - supervisor/graph.py:103   emit("loop.team_composed", {"selected": ...})  (S10.1)
  - supervisor/graph.py:117   emit("loop.parse_error", {"round":..,"count":..})
  - supervisor/graph.py:122   emit("loop.decision", {"round":.., "decision":..}) (S10.8)
  - supervisor/graph.py:209   emit("loop.turn", {"agent_id":.., "outcome":..})
  - delegation/manager.py:52-60  publish("delegation.finished",
                              {"outcome":.., "artifact_count":.., "error":..})
  - delegation/manager.py:91-94, 114-117  publish("delegation.started", ...)
  - control/events.py:23-25  ACTOR_TYPES={human,agent,tool,system,runtime}
                             VISIBILITY_LEVELS={public,ui_safe,internal,secret,restricted}
  - control/events.py:32-50  Actor.__post_init__ ép type ∈ ACTOR_TYPES → ControlContractError
  - bài học gốc 40_UbiquitousLanguage.md §1.6 (event name = UL của producing BC).

KHÔNG dùng gì ngoài thư viện chuẩn Python 3.14. KHÔNG import hex_agent.
Thay EventBus/SSE thật bằng list in-memory; payload là dict thường.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ─────────────────────────────────────────────────────────────────────────────
# 1. VOCABULARY METADATA theo domain (gốc: control/events.py:23-25, 32-50)
#    Ngay cả metadata cũng nói ngôn ngữ domain — không phải debug/info/warn.
# ─────────────────────────────────────────────────────────────────────────────
ACTOR_TYPES = frozenset({"human", "agent", "tool", "system", "runtime"})
VISIBILITY_LEVELS = frozenset({"public", "ui_safe", "internal", "secret", "restricted"})


class ControlContractError(ValueError):
    """Gốc: control/errors.ControlContractError — vi phạm vocabulary là lỗi hợp đồng."""


@dataclass(frozen=True)
class Actor:
    """Gốc: control/events.py:32-50. type PHẢI thuộc ACTOR_TYPES — UL enforced bằng validation."""
    type: str
    id: str

    def __post_init__(self) -> None:
        if self.type not in ACTOR_TYPES:
            raise ControlContractError(
                f"Actor.type phải thuộc {sorted(ACTOR_TYPES)}, nhận {self.type!r}.")
        if not self.id:
            raise ControlContractError("Actor.id không được rỗng.")


# ─────────────────────────────────────────────────────────────────────────────
# 2. EVENT BUS tối thiểu (gốc: kernel.events.publish / ctx.emit)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Event:
    topic: str                       # vd "loop.team_composed", "delegation.finished"
    payload: dict = field(default_factory=dict)
    actor: Actor | None = None


class EventBus:
    """Bus in-memory thay cho EventBus/SSE thật."""
    def __init__(self) -> None:
        self.events: list[Event] = []

    def publish(self, topic: str, payload: dict, actor: Actor | None = None) -> None:
        self.events.append(Event(topic=topic, payload=dict(payload), actor=actor))

    def topics(self) -> list[str]:
        return [e.topic for e in self.events]


# ─────────────────────────────────────────────────────────────────────────────
# 3. SUPERVISOR + DELEGATION phát event bằng UL (gốc: graph.py, manager.py)
#    Topic = "<bounded-context>.<phase-nghiệp-vụ>". Tiền tố mirror BC boundary.
# ─────────────────────────────────────────────────────────────────────────────
def supervisor_run(bus: EventBus) -> None:
    """Distill 1 vòng supervisor — mỗi phase phát đúng event UL (gốc graph.py)."""
    runtime = Actor(type="runtime", id="supervisor")
    # S10.1 compose_team → loop.team_composed (KHÔNG 'agents_selected')
    bus.publish("loop.team_composed", {"selected": ["agent:planner", "agent:coder"]}, runtime)
    # S10.8 o_decide → loop.decision (KHÔNG 'orchestrator_output')
    bus.publish("loop.decision", {"round": 1, "decision": "continue"}, runtime)
    # S10.2 run_round → loop.turn (KHÔNG 'agent_dispatched'), kèm domain context outcome
    bus.publish("loop.turn", {"agent_id": "agent:coder", "outcome": "success"}, runtime)


def delegation_run(bus: EventBus) -> None:
    """Distill 1 delegation — lifecycle event UL (gốc manager.py:91-94, 52-60)."""
    runtime = Actor(type="agent", id="agent:coder")
    # delegation.started (KHÔNG 'job_queued')
    bus.publish("delegation.started", {"target": "agent:tester", "delegation_id": "d1"}, runtime)
    # delegation.finished kèm domain semantics: outcome + artifact_count (KHÔNG 'execution_done')
    bus.publish("delegation.finished",
                {"target": "agent:tester", "outcome": "success", "artifact_count": 3, "error": None},
                runtime)


# ─────────────────────────────────────────────────────────────────────────────
# 4. KIỂM TRA tính nhất quán UL của event (mô phỏng kỷ luật naming)
# ─────────────────────────────────────────────────────────────────────────────
# Vocabulary phase nghiệp vụ được phép cho từng BC (mirror spec slice S10.x).
_UL_VOCAB = {
    "loop": {"team_composed", "decision", "parse_error", "turn", "tool"},        # supervisor BC (E10)
    "delegation": {"started", "finished", "progress"},                            # delegation BC
}
# Tên jargon kỹ thuật bị cấm — đối chứng của bài học (Ví dụ 2: dev jargon).
_BANNED_JARGON = {
    "agents_selected", "agent_array_built", "orchestrator_output", "json_parse_fail",
    "agent_dispatched", "job_queued", "execution_done", "log_entry",
}


@dataclass
class UlReport:
    well_named: list[str] = field(default_factory=list)
    jargon: list[str] = field(default_factory=list)
    unknown_phase: list[str] = field(default_factory=list)

    @property
    def consistent(self) -> bool:
        return not (self.jargon or self.unknown_phase)


def audit_event_naming(bus: EventBus) -> UlReport:
    """Mỗi topic phải có dạng <bc>.<phase-UL>; phase phải thuộc vocabulary BC đó."""
    report = UlReport()
    for topic in bus.topics():
        if topic in _BANNED_JARGON:
            report.jargon.append(topic)
            continue
        if "." not in topic:
            report.jargon.append(topic)   # tên phẳng kiểu log_entry → jargon
            continue
        bc, _, phase = topic.partition(".")
        if bc not in _UL_VOCAB or phase not in _UL_VOCAB[bc]:
            report.unknown_phase.append(topic)
        else:
            report.well_named.append(topic)
    return report


# ─────────────────────────────────────────────────────────────────────────────
# 5. UL MAP — event ↔ phase/slice nghiệp vụ (gốc: traceability spec S10.x)
# ─────────────────────────────────────────────────────────────────────────────
def build_ul_map() -> dict[str, str]:
    """Ánh xạ event UL → phase nghiệp vụ + spec slice. Business expert đọc hiểu ngay."""
    return {
        "loop.team_composed": "S10.1 compose_team — chốt team",
        "loop.decision":      "S10.8 o_decide — O ra quyết định vòng",
        "loop.turn":          "S10.2 run_round — một worker chạy xong lượt",
        "delegation.started": "delegate() — bắt đầu uỷ thác tuần tự",
        "delegation.finished":"_finish() — uỷ thác xong, kèm outcome + artifact_count",
    }


# ─────────────────────────────────────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────────────────────────────────────
def demo() -> None:
    print("=" * 72)
    print("CASE 02 — Domain event naming bằng Ubiquitous Language (hex_agent)")
    print("=" * 72)

    bus = EventBus()
    supervisor_run(bus)
    delegation_run(bus)

    print("\n[1] Event đã phát (topic = <bounded-context>.<phase-nghiệp-vụ>):")
    for e in bus.events:
        print(f"    {e.topic:<22} payload={e.payload}")

    print("\n[2] Metadata cũng nói ngôn ngữ domain (gốc control/events.py:23-25):")
    print(f"    ACTOR_TYPES      = {sorted(ACTOR_TYPES)}")
    print(f"    VISIBILITY_LEVELS= {sorted(VISIBILITY_LEVELS)}")
    print("    → không phải debug/info/warn; mỗi giá trị là một khái niệm domain.")

    print("\n[3] UL enforced bằng validation (gốc Actor.__post_init__):")
    try:
        Actor(type="superuser", id="x")   # 'superuser' không thuộc ACTOR_TYPES
    except ControlContractError as exc:
        print(f"    Actor(type='superuser') bị từ chối: {exc}")
    ok = Actor(type="human", id="user:uspro")
    print(f"    Actor(type='human', id='user:uspro') hợp lệ: {ok}")
    assert ok.type in ACTOR_TYPES

    print("\n[4] Audit naming — event hex_agent dùng đúng UL:")
    report = audit_event_naming(bus)
    print(f"    well_named   = {report.well_named}")
    print(f"    jargon       = {report.jargon}")
    print(f"    unknown_phase= {report.unknown_phase}")
    assert report.consistent, "Event hex_agent phải nhất quán UL."
    print("    OK — mọi topic đúng dạng <bc>.<phase-UL> và phase thuộc vocabulary BC.")

    print("\n[5] ĐỐI CHỨNG — khi đặt tên bằng JARGON kỹ thuật:")
    bad_bus = EventBus()
    runtime = Actor(type="runtime", id="supervisor")
    bad_bus.publish("agents_selected", {"x": 1}, runtime)     # đáng lẽ loop.team_composed
    bad_bus.publish("job_queued", {"x": 1}, runtime)          # đáng lẽ delegation.started
    bad_bus.publish("log_entry", {"level": "info"}, runtime)  # tên phẳng vô nghĩa nghiệp vụ
    bad_report = audit_event_naming(bad_bus)
    print(f"    jargon bị bắt = {bad_report.jargon}")
    assert not bad_report.consistent, "Tên jargon PHẢI bị audit bắt."
    assert "agents_selected" in bad_report.jargon
    assert "job_queued" in bad_report.jargon
    print("    → Business expert đọc 'job_queued' KHÔNG biết chuyện gì xảy ra trong nghiệp vụ.")
    print("    → Rename 'loop.team_composed' đòi cập nhật test + docs + observability + replay.")

    print("\n[6] UL map — event ↔ phase nghiệp vụ (traceability):")
    for topic, phase in build_ul_map().items():
        print(f"    {topic:<22} ⇒ {phase}")

    print("\nKẾT: Event name là Published Language của BC. Đặt bằng UL ⇒ một câu nói")
    print("     của business expert và một dòng log nói CÙNG ngôn ngữ.")


if __name__ == "__main__":
    demo()
