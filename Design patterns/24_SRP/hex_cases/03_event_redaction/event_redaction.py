"""
SRP case 03 — Secret Masking Before UI (chỉ phục vụ UI/Observability team).

Distill TRUNG THỰC từ codebase hex_agent:
  - control/redaction.py:1-74   (toàn bộ Redactor + SECRET_KEYS)
      * SECRET_KEYS frozenset    -> redaction.py:16-33
      * REDACTED const           -> redaction.py:34
      * Redactor.__init__        -> redaction.py:38-39
      * _is_secret (SecretIdentifier) -> redaction.py:41-42
      * redact (entry)           -> redaction.py:44-48
      * _walk (Masker đệ quy + MetadataRecorder) -> redaction.py:50-63
      * apply (EventPatcher)     -> redaction.py:65-73

Ý NGHĨA SRP:
  Redactor là class guardrail nằm đúng ranh giới bảo mật: tách payload thô thành
  (ui_payload an toàn) + (danh sách đường dẫn field đã che) cho audit. Nó có MỘT actor:
  đội UI/Observability — "đừng bao giờ để secret rò ra SSE/HTTP". Nó KHÔNG validate event,
  KHÔNG route, KHÔNG lưu. Thuần biến đổi, không side effect, KHÔNG mutate input gốc.

Vai trò pattern:
  - SecretIdentifier : _is_secret (so khớp tên key, không phân biệt hoa thường).
  - Masker          : _walk đệ quy xuống dict + list, thay terminal secret bằng [REDACTED].
  - MetadataRecorder: _walk ghi lại path dạng "a.b" / "a[0].b".
  - EventPatcher    : apply -> trả bản copy event với ui_payload đã làm sạch + RedactionInfo.

Bản distill:
  - Giữ NGUYÊN thuật toán đệ quy + cách đánh path.
  - THAY RuntimeEvent/RedactionInfo nặng (control/events.py) bằng dataclass tối thiểu
    cùng tên vai trò, để chạy độc lập. Logic redact KHÔNG đổi.
  - Chỉ dùng stdlib (dataclasses, copy).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from typing import Any

# Key nào thì che giá trị ở MỌI nơi xuất hiện (so khớp tên chính xác, bỏ hoa/thường).
SECRET_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "password",
        "passwd",
        "secret",
        "secret_key",
        "client_secret",
        "token",
        "access_token",
        "refresh_token",
        "private_key",
        "set-cookie",
        "cookie",
    }
)
REDACTED = "[REDACTED]"


# ── Stand-in tối thiểu cho control/events.py (LƯỢC BỎ các field không liên quan redact) ──
@dataclass(frozen=True)
class RedactionInfo:
    level: str = "ui_safe"
    has_secret: bool = False
    redacted_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeEvent:
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    ui_payload: dict[str, Any] | None = None
    redaction: RedactionInfo = field(default_factory=RedactionInfo)


class Redactor:
    def __init__(self, secret_keys: frozenset[str] = SECRET_KEYS) -> None:
        self.secret_keys = frozenset(k.lower() for k in secret_keys)

    # ── SecretIdentifier ──
    def _is_secret(self, key: str) -> bool:
        return key.lower() in self.secret_keys

    # ── entry ──
    def redact(self, payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        """Trả (bản_copy_đã_che, danh_sách_path_đã_che_sắp_xếp). Input GIỮ NGUYÊN."""
        fields: list[str] = []
        redacted = self._walk(payload, "", fields)
        return redacted, sorted(set(fields))

    # ── Masker (đệ quy) + MetadataRecorder ──
    def _walk(self, value: Any, path: str, fields: list[str]) -> Any:
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for key, item in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if self._is_secret(str(key)):
                    out[key] = REDACTED
                    fields.append(child_path)
                else:
                    out[key] = self._walk(item, child_path, fields)
            return out
        if isinstance(value, list):
            return [self._walk(item, f"{path}[{index}]", fields) for index, item in enumerate(value)]
        return value

    # ── EventPatcher ──
    def apply(self, event: RuntimeEvent, *, level: str | None = None) -> RuntimeEvent:
        """Trả bản copy của event với ui_payload + redaction được điền từ payload."""
        ui_payload, fields = self.redact(event.payload)
        info = RedactionInfo(
            level=level or event.redaction.level,
            has_secret=bool(fields),
            redacted_fields=tuple(fields),
        )
        return replace(event, ui_payload=ui_payload, redaction=info)


# ============================================================================
# DEMO
# ============================================================================

def demo() -> None:
    print("=" * 72)
    print("SRP case 03 — Secret Masking Before UI (control/redaction.py)")
    print("Actor DUY NHẤT: đội UI/Observability. Một việc: tách payload an toàn vs secret.")
    print("=" * 72)

    redactor = Redactor()

    # (1) secret ở top-level VÀ trong dict lồng -> cả hai bị che; path được ghi lại.
    payload = {
        "api_key": "sk-top-level-123",
        "user": "alice",
        "auth": {"token": "abc.def.ghi", "scope": "read"},
        "items": [{"password": "p@ss"}, {"name": "ok"}],
    }
    original_snapshot = copy.deepcopy(payload)

    redacted, fields = redactor.redact(payload)
    print("\n(1) redact payload lồng nhau:")
    print(f"    fields đã che = {fields}")
    assert redacted["api_key"] == REDACTED
    assert redacted["auth"]["token"] == REDACTED
    assert redacted["items"][0]["password"] == REDACTED
    # Cấu trúc không-phải-secret được copy nguyên vẹn (graceful degradation):
    assert redacted["user"] == "alice"
    assert redacted["auth"]["scope"] == "read"
    assert redacted["items"][1] == {"name": "ok"}
    print("    -> mọi secret terminal thành [REDACTED]; phần khác giữ nguyên. PASS")

    # (2) MetadataRecorder: path dạng "a.b" và "a[i].b".
    assert "api_key" in fields
    assert "auth.token" in fields
    assert "items[0].password" in fields
    print("    -> path ghi đúng: 'auth.token', 'items[0].password'. PASS")

    # (3) Bất biến quan trọng: input gốc KHÔNG bị mutate (no side effect).
    assert payload == original_snapshot, "redact KHÔNG được sửa input gốc"
    assert payload["api_key"] == "sk-top-level-123"
    print("\n(3) [BẤT BIẾN] payload gốc giữ nguyên (audit trail thật vẫn còn). PASS")

    # (4) EventPatcher: apply điền ui_payload + redaction lên event.
    event = RuntimeEvent(event_type="agent.tool_call", payload=payload)
    patched = redactor.apply(event, level="ui_safe")
    assert patched.ui_payload is not None and patched.ui_payload["api_key"] == REDACTED
    assert patched.redaction.has_secret is True
    assert "auth.token" in patched.redaction.redacted_fields
    assert event.ui_payload is None, "event gốc không bị đụng (replace tạo bản mới)"
    print("(4) apply -> event mới có ui_payload sạch + RedactionInfo. event gốc nguyên. PASS")

    # (5) Case-insensitive: API_KEY viết hoa vẫn bị bắt.
    redacted2, fields2 = redactor.redact({"API_KEY": "X", "Cookie": "Y"})
    assert redacted2["API_KEY"] == REDACTED and redacted2["Cookie"] == REDACTED
    print("(5) so khớp không phân biệt hoa/thường: API_KEY, Cookie đều bị che. PASS")

    # ---- ĐỐI CHỨNG: nếu redaction bị trộn vào emitter (God Emitter) ----
    print("\n--- ĐỐI CHỨNG: nếu KHÔNG tách Redactor mà nhét vào EventEmitter ---")
    print("  * Mỗi đường publish (SSE, JSONL, Kafka...) phải tự nhớ che secret -> dễ sót.")
    print("  * Thêm key bí mật mới phải sửa nhiều nơi; quên 1 nơi = rò token ra UI.")
    print("  Tách ra: thêm key bí mật chỉ sửa SECRET_KEYS, mọi sink dùng chung 1 cổng che.")

    print("\nKẾT: 1 class guardrail, 1 actor, thuần hàm, không side effect. Đổi luật che")
    print("secret chỉ đụng file này; không lan tới authz, dispatch event hay kernel.")


if __name__ == "__main__":
    demo()
