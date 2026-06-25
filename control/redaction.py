"""Redactor — the secret-safety boundary before any payload reaches UI/SSE. Epic E21 (S21.7).

Splits a raw ``payload`` into a redacted ``ui_payload`` + ``RedactionInfo``. Secret-keyed
fields are masked recursively (nested dicts AND lists), recording dotted/indexed paths.
The original payload is never mutated. The gateway streams only ``ui_payload``; if it is
absent the gateway must NOT fall back to raw (enforced in Phase C).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from control.events import RedactionInfo, RuntimeEvent

# Keys whose values are masked wherever they appear (case-insensitive, exact key match).
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


class Redactor:
    def __init__(self, secret_keys: frozenset[str] = SECRET_KEYS) -> None:
        self.secret_keys = frozenset(k.lower() for k in secret_keys)

    def _is_secret(self, key: str) -> bool:
        return key.lower() in self.secret_keys

    def redact(self, payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        """Return (redacted_copy, sorted_redacted_paths). Input is left unchanged."""
        fields: list[str] = []
        redacted = self._walk(payload, "", fields)
        return redacted, sorted(set(fields))

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

    def apply(self, event: RuntimeEvent, *, level: str | None = None) -> RuntimeEvent:
        """Return a copy of ``event`` with ``ui_payload`` + ``redaction`` filled from ``payload``."""
        ui_payload, fields = self.redact(event.payload)
        info = RedactionInfo(
            level=level or event.redaction.level,
            has_secret=bool(fields),
            redacted_fields=tuple(fields),
        )
        return replace(event, ui_payload=ui_payload, redaction=info)
