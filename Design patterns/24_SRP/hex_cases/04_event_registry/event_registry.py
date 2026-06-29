"""
SRP case 04 — Event-Type Catalog with Visibility (chỉ phục vụ Control-plane team).

Distill TRUNG THỰC từ codebase hex_agent:
  - control/event_registry.py:1-100
      * EventTypeSpec (frozen dataclass) -> event_registry.py:22-37
      * EventTypeRegistry.__init__       -> event_registry.py:41-42
      * __contains__                     -> event_registry.py:44-45
      * assert_known (Validator/gate)    -> event_registry.py:47-51
      * get                              -> event_registry.py:53-55
      * visibility                       -> event_registry.py:57-58
      * types                            -> event_registry.py:60-61
      * parse_event_registry (Parser)    -> event_registry.py:64-93
  - control/emitter.py:53-61  (emit_event gọi registry.get TRƯỚC khi publish — registry là gate)
  - control/errors.py         (ControlContractError)
  - control/events.py         (VISIBILITY_LEVELS)

Ý NGHĨA SRP:
  Registry là NGUỒN SỰ THẬT khai báo "event type nào hợp lệ + ai được thấy". Tách ĐỊNH NGHĨA
  khỏi THỰC THI: EventEmitter gọi registry.get(event_type) trước khi publish; nếu lạ thì
  REGISTRY ném lỗi, KHÔNG phải emitter. Thêm event type mới = sửa YAML/cấu hình, KHÔNG đụng
  code emitter/authz/redactor. Một actor: đội control-plane / deployment eng.

Vai trò pattern:
  - Catalog   : dict specs theo event_type.
  - QueryPort : contains/get/visibility/types -> trả dữ liệu spec, thuần đọc.
  - Validator : assert_known ném khi gặp type lạ -> chính là cổng gác emitter.
  - Parser    : parse_event_registry kiểm tra cấu trúc cấu hình rồi dựng registry.

Bản distill:
  - Giữ NGUYÊN API + vai trò gate.
  - THAY việc đọc YAML từ đĩa bằng một dict Python in-memory (Parser nhận dict, y như
    parse_event_registry gốc vốn nhận `data: dict` đã parse). KHÔNG cần pyyaml, KHÔNG đọc file.
  - ControlContractError là Exception tự định nghĩa thay cho control/errors.py.
  - Chỉ dùng stdlib (dataclasses).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Tương ứng control/events.py:25 — VISIBILITY_LEVELS (5 mức, chép NGUYÊN VĂN từ codebase
# gốc): ai được thấy event. Đã đối chiếu: {'public','ui_safe','internal','secret','restricted'}.
VISIBILITY_LEVELS = frozenset({"public", "ui_safe", "internal", "secret", "restricted"})


class ControlContractError(ValueError):
    """Thay cho control/errors.py:ControlContractError — vi phạm hợp đồng control-plane."""


# ── Catalog item ──
@dataclass(frozen=True)
class EventTypeSpec:
    event_type: str
    visibility: str
    durable: bool = True
    redact_for_ui: bool = False
    checkpoint_candidate: bool = False


class EventTypeRegistry:
    def __init__(self, specs: dict[str, EventTypeSpec]) -> None:
        self._specs = dict(specs)

    # ── QueryPort ──
    def __contains__(self, event_type: str) -> bool:
        return event_type in self._specs

    # ── Validator / gate ──
    def assert_known(self, event_type: str) -> None:
        if event_type not in self._specs:
            raise ControlContractError(
                f"Unknown event_type: {event_type!r}. Declare it in runtime_event_types.yaml."
            )

    def get(self, event_type: str) -> EventTypeSpec:
        self.assert_known(event_type)
        return self._specs[event_type]

    def visibility(self, event_type: str) -> str:
        return self.get(event_type).visibility

    def types(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))


# ── Parser ──
def parse_event_registry(data: dict[str, Any], *, source: str = "<event-registry>") -> EventTypeRegistry:
    if not isinstance(data, dict):
        raise ControlContractError(f"Event registry '{source}' must be a mapping.")
    rows = data.get("event_types")
    if not isinstance(rows, dict) or not rows:
        raise ControlContractError(f"Event registry '{source}' must have a non-empty 'event_types' mapping.")
    specs: dict[str, EventTypeSpec] = {}
    for name, raw in rows.items():
        event_type = str(name).strip()
        if not event_type or "." not in event_type:
            raise ControlContractError(
                f"Event registry '{source}': event_type {name!r} must be dotted (e.g. 'agent.before_run')."
            )
        raw = raw or {}
        if not isinstance(raw, dict):
            raise ControlContractError(f"Event registry '{source}': '{event_type}' must be a mapping.")
        visibility = str(raw.get("visibility", "ui_safe"))
        if visibility not in VISIBILITY_LEVELS:
            raise ControlContractError(
                f"Event registry '{source}': '{event_type}' visibility {visibility!r} "
                f"must be one of {sorted(VISIBILITY_LEVELS)}."
            )
        specs[event_type] = EventTypeSpec(
            event_type=event_type,
            visibility=visibility,
            durable=bool(raw.get("durable", True)),
            redact_for_ui=bool(raw.get("redact_for_ui", False)),
            checkpoint_candidate=bool(raw.get("checkpoint_candidate", False)),
        )
    return EventTypeRegistry(specs)


# ── Stand-in cho control/emitter.py: emitter gọi registry.get TRƯỚC khi publish ──
class EventEmitter:
    """Thu nhỏ EventEmitter (control/emitter.py:53-61): chứng minh REGISTRY là cổng gác,
    không phải emitter. Sink chỉ là list để xem cái gì đã publish."""

    def __init__(self, registry: EventTypeRegistry) -> None:
        self._registry = registry
        self.published: list[tuple[str, str]] = []  # (event_type, visibility)

    def emit(self, event_type: str) -> None:
        spec = self._registry.get(event_type)   # ControlContractError nếu lạ -> chặn trước publish
        self.published.append((event_type, spec.visibility))


# ============================================================================
# DEMO
# ============================================================================

def demo() -> None:
    print("=" * 72)
    print("SRP case 04 — Event-Type Catalog (control/event_registry.py)")
    print("Actor DUY NHẤT: đội control-plane. Tách ĐỊNH NGHĨA khỏi THỰC THI.")
    print("=" * 72)

    # "Cấu hình" in-memory thay cho config/runtime_event_types.yaml.
    config = {
        "event_types": {
            "agent.before_run": {"visibility": "ui_safe"},
            "agent.tool_call": {"visibility": "internal", "redact_for_ui": True},
            "agent.secret_loaded": {"visibility": "secret", "durable": False},
        }
    }

    registry = parse_event_registry(config, source="demo.yaml")
    print(f"\n(1) Parser dựng registry với {len(registry.types())} type: {registry.types()}")

    # (2) Mọi type khai báo phải có visibility hợp lệ (bất biến của Parser).
    for et in registry.types():
        vis = registry.visibility(et)
        assert vis in VISIBILITY_LEVELS, f"{et} visibility lạ: {vis}"
        print(f"    {et:<22} visibility={vis}")
    print("    -> mọi visibility nằm trong VISIBILITY_LEVELS. PASS")

    # (3) Emitter dùng registry làm gate: type LẠ -> registry ném, emitter KHÔNG publish.
    emitter = EventEmitter(registry)
    emitter.emit("agent.before_run")
    emitter.emit("agent.tool_call")
    print(f"\n(3) đã publish hợp lệ: {emitter.published}")
    try:
        emitter.emit("agent.totally_made_up")
        raise AssertionError("type lạ phải bị chặn")
    except ControlContractError as err:
        print(f"    type lạ bị chặn TẠI REGISTRY (không phải emitter): {err}")
    assert len(emitter.published) == 2, "type lạ không được lọt vào sink"
    print("    -> registry là cổng gác; sink chỉ nhận type đã khai báo. PASS")

    # (4) Thêm event type mới = sửa CẤU HÌNH, KHÔNG đụng code emitter.
    config["event_types"]["agent.after_run"] = {"visibility": "ui_safe"}
    registry2 = parse_event_registry(config, source="demo.yaml")
    emitter2 = EventEmitter(registry2)   # cùng class EventEmitter, KHÔNG sửa 1 dòng
    emitter2.emit("agent.after_run")
    assert ("agent.after_run", "ui_safe") in emitter2.published
    print("\n(4) thêm 'agent.after_run' chỉ bằng sửa config -> emitter dùng lại y nguyên. PASS")

    # (5) Parser bắt cấu hình sai: visibility ngoài tập hợp -> lỗi rõ ràng.
    #     'world_readable' KHÔNG nằm trong VISIBILITY_LEVELS thật -> bị từ chối.
    #     (Lưu ý: 'public' LÀ mức hợp lệ trong events.py:25, nên KHÔNG dùng làm ví dụ sai.)
    try:
        parse_event_registry({"event_types": {"x.bad": {"visibility": "world_readable"}}})
        raise AssertionError("visibility sai phải bị từ chối")
    except ControlContractError:
        print("(5) Parser từ chối visibility='world_readable' (không hợp lệ). PASS")

    # ---- ĐỐI CHỨNG: nếu mỗi emitter tự hard-code danh sách event type ----
    print("\n--- ĐỐI CHỨNG: nếu KHÔNG có registry, mỗi emitter tự liệt kê type cho phép ---")
    print("  * Hai emitter dễ lệch nhau; type gõ sai lọt qua silently rồi vỡ ở downstream.")
    print("  * Đổi visibility 1 type phải sửa mọi emitter -> Shotgun Surgery.")
    print("  Có registry: 1 nguồn sự thật, N type, đổi chỉ 1 chỗ, gate tự thực thi.")

    print("\nKẾT: registry trả lời 'type này hợp lệ không / ai được thấy', emitter chỉ")
    print("publish. Hai trách nhiệm tách bạch -> đổi catalog không lan ra code phát sự kiện.")


if __name__ == "__main__":
    demo()
