"""
Case 02 — Adapter: bọc client LLM kiểu-OpenAI, dịch lỗi thành envelope JSON
===========================================================================

Distill TRUNG THỰC từ hex_agent (Adapter / Structural):

  - llm/adapter.py:72-119
        call_llm(messages, *, json_mode=True, client=None) -> str
        Adapter cấp-module bọc client openai.OpenAI. Đảm bảo hành vi
        KHÔNG-NÉM-EXCEPTION: luôn trả về một chuỗi JSON. Khi lỗi (đã hết retry
        hoặc lỗi vĩnh viễn) trả envelope {"action":"final","finish_reason":
        "error","message": ...}. Có retry + exponential backoff, và downgrade
        json_object -> text khi server từ chối response_format.

  - llm/adapter.py:25-32     _get_client() — lazy tạo client, injectable.
  - llm/adapter.py:40-50     _is_transient() — phân loại lỗi đáng retry (429/5xx/timeout/connection).
  - llm/adapter.py:53-59     _is_connection_error() — endpoint không tới được (server chết).
  - llm/adapter.py:105-119   ráp thông điệp lỗi ACTIONABLE: nêu URL + gợi ý "is the server running?".

  - tests/test_llm_adapter.py:54-82
        _DeadClient + test_connection_failure_message_is_actionable — mô phỏng
        openai.APIConnectionError (không có HTTP status, tên class chứa
        "connection", bọc cause OSError "Connection refused").

File này CHỈ dùng thư viện chuẩn Python 3.14. KHÔNG import openai hay hex_agent.
Client thật (mạng) được thay bằng fake stdlib. Logic dịch lỗi + retry/backoff
được giữ nguyên vai trò.
"""
from __future__ import annotations

import json
from typing import Any


# ──────────────────────────────────────────────────────────────────────────
# Cấu hình mặc định (trùng tinh thần llm/adapter.py:13-22)
# ──────────────────────────────────────────────────────────────────────────
_BASE_URL = "http://localhost:1234/v1"
_MODEL = "local-model"
_MAX_RETRIES = 2
_RETRY_BASE = 0.5

# Hàm sleep ở cấp module để test/demo có thể thay (no-op) — như _sleep trong adapter thật.
_sleep = lambda _seconds: None  # noqa: E731  (demo: không thật sự ngủ)


# ──────────────────────────────────────────────────────────────────────────
# Helper phân loại lỗi — duck-typed để KHÔNG phải import lớp exception của openai
# (trùng llm/adapter.py:40-59)
# ──────────────────────────────────────────────────────────────────────────
def _is_transient(exc: Exception) -> bool:
    """Đáng retry: timeout, rớt kết nối, 429, 5xx. Vĩnh viễn: 4xx khác + không phân loại được."""
    status = getattr(exc, "status_code", None)
    if not isinstance(status, int):
        status = getattr(exc, "status", None)
    if isinstance(status, int):
        return status == 429 or status >= 500
    name = type(exc).__name__.lower()
    return "timeout" in name or "connection" in name


def _is_connection_error(exc: Exception) -> bool:
    """Request chưa từng chạm HTTP status -> endpoint không tới được (server chết / sai port)."""
    if isinstance(getattr(exc, "status_code", None), int) or isinstance(getattr(exc, "status", None), int):
        return False
    return "connection" in type(exc).__name__.lower()


def _is_response_format_error(exc: Exception) -> bool:
    """True khi server từ chối response_format={'type':'json_object'}."""
    return "response_format" in str(exc).lower()


# ──────────────────────────────────────────────────────────────────────────
# ADAPTER — call_llm() (trùng vai trò llm/adapter.py:72-119)
# Target interface: call_llm(...) -> str (JSON) và CAM KẾT không bao giờ raise.
# Adaptee: client.chat.completions.create(**kwargs) (interface kiểu-OpenAI).
# ──────────────────────────────────────────────────────────────────────────
def call_llm(messages, *, model=None, temperature=0.2, json_mode=True, client) -> str:
    """Gọi endpoint chat kiểu-OpenAI. Retry lỗi transient + backoff; nếu server
    từ chối json_object thì retry một lần ở text mode; lỗi vĩnh viễn (hoặc hết
    retry) trả về JSON `final`/error — KHÔNG BAO GIỜ raise."""
    kwargs: dict[str, Any] = {
        "model": model or _MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    attempts = max(1, _MAX_RETRIES + 1)
    last_exc: Exception | None = None
    attempt = 0
    downgraded = False
    while attempt < attempts:
        try:
            response = client.chat.completions.create(**kwargs)
            return response.choices[0].message.content or ""
        except Exception as exc:
            last_exc = exc
            # Server từ chối json_object -> hạ xuống text MỘT lần, không tốn lượt retry.
            if json_mode and not downgraded and _is_response_format_error(exc):
                kwargs["response_format"] = {"type": "text"}
                downgraded = True
                continue
            if attempt + 1 < attempts and _is_transient(exc):
                _sleep(_RETRY_BASE * (2 ** attempt))  # backoff: 0.5, 1.0, 2.0, ...
                attempt += 1
                continue
            break

    # Ráp thông điệp lỗi ACTIONABLE (trùng llm/adapter.py:105-119).
    detail = str(last_exc)
    cause = last_exc.__cause__ if last_exc is not None else None
    if cause and str(cause) and str(cause) not in detail:
        detail = f"{detail} ({cause})"
    if last_exc is not None and _is_connection_error(last_exc):
        detail = f"{detail} — cannot reach the LLM at {_BASE_URL}; is the server running?"
    return json.dumps(
        {"action": "final", "finish_reason": "error",
         "message": f"LLM request failed after {attempt + 1} attempt(s): {detail}"},
        ensure_ascii=False,
    )


# ──────────────────────────────────────────────────────────────────────────
# Fake ADAPTEE — các client kiểu-OpenAI (thay cho openai.OpenAI thật)
# Trùng cấu trúc test doubles tests/test_llm_adapter.py:5-24, 54-68.
# ──────────────────────────────────────────────────────────────────────────
class _FakeChoiceMsg:
    def __init__(self, content: str) -> None:
        self.message = type("M", (), {"content": content})()


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoiceMsg(content)]


class _OkClient:
    """Client trả về JSON hợp lệ ngay lần đầu."""

    def __init__(self, content: str = '{"action":"final","message":"ok"}') -> None:
        self.content = content
        self.kwargs: dict | None = None
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.kwargs = kwargs
                return _FakeResponse(outer.content)

        self.chat = type("C", (), {"completions": _Completions()})()


class _DeadClient:
    """Endpoint không tới được — mô phỏng openai.APIConnectionError:
    không có HTTP status, tên class chứa 'connection', bọc cause refused socket.
    (trùng tests/test_llm_adapter.py:54-68)."""

    def __init__(self) -> None:
        class APIConnectionError(Exception):
            pass

        class _Completions:
            def create(self, **kwargs):
                exc = APIConnectionError("Connection error.")
                exc.__cause__ = OSError("[Errno 61] Connection refused")
                raise exc

        self.chat = type("C", (), {"completions": _Completions()})()


class _FlakyThenOkClient:
    """Hỏng transient (status 503) `fail_times` lần rồi mới thành công.
    Dùng để chứng minh retry/backoff của adapter."""

    def __init__(self, fail_times: int, content: str = '{"action":"final","message":"recovered"}') -> None:
        self.fail_times = fail_times
        self.calls = 0
        self.content = content
        outer = self

        class _ServerError(Exception):
            def __init__(self) -> None:
                super().__init__("temporary upstream failure")
                self.status_code = 503

        class _Completions:
            def create(self, **kwargs):
                outer.calls += 1
                if outer.calls <= outer.fail_times:
                    raise _ServerError()
                return _FakeResponse(outer.content)

        self.chat = type("C", (), {"completions": _Completions()})()


class _RejectsJsonObjectClient:
    """Server chỉ chấp nhận text/json_schema, 400 khi gặp json_object.
    Adapter phải downgrade sang text rồi thành công (trùng llm/adapter.py:62-69, 95-98)."""

    def __init__(self, content: str = '{"action":"final","message":"text-mode ok"}') -> None:
        self.content = content
        self.formats_seen: list[Any] = []
        outer = self

        class _BadFormat(Exception):
            pass

        class _Completions:
            def create(self, **kwargs):
                fmt = kwargs.get("response_format")
                outer.formats_seen.append(fmt)
                if fmt == {"type": "json_object"}:
                    raise _BadFormat("'response_format.type' must be 'json_schema' or 'text'")
                return _FakeResponse(outer.content)

        self.chat = type("C", (), {"completions": _Completions()})()


# Đối chứng: gọi adaptee TRỰC TIẾP, không qua adapter -> caller phải tự bắt exception.
def raw_call_no_adapter(client, messages) -> str:
    """Không có adapter: client.create() có thể NÉM exception mờ mịt; caller
    buộc phải tự try/except ở mọi nơi gọi, và lỗi 'Connection error.' không nói
    được là đã thử URL nào."""
    response = client.chat.completions.create(model=_MODEL, messages=messages)
    return response.choices[0].message.content or ""


# ──────────────────────────────────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────────────────────────────────
def demo() -> None:
    print("=" * 70)
    print("CASE 02 — Adapter LLM: dịch mọi mode lỗi thành envelope JSON, không raise")
    print("=" * 70)
    msgs = [{"role": "user", "content": "hi"}]

    # [1] đường thành công
    print("\n[1] Client OK -> trả thẳng nội dung JSON")
    ok = _OkClient()
    out = call_llm(msgs, model="m1", client=ok)
    print("    call_llm ->", out)
    assert json.loads(out)["message"] == "ok"
    assert ok.kwargs["response_format"] == {"type": "json_object"}
    print("[assert] json_mode bật mặc định + nội dung đi qua nguyên vẹn. OK")

    # [2] server CHẾT -> envelope lỗi ACTIONABLE, không exception
    print("\n[2] Server CHẾT (APIConnectionError) -> envelope lỗi, KHÔNG raise")
    out = call_llm(msgs, client=_DeadClient())
    action = json.loads(out)
    print("    call_llm ->", out)
    assert action["finish_reason"] == "error"
    assert _BASE_URL in action["message"]                # nêu rõ endpoint đã thử
    assert "is the server running" in action["message"].lower()  # gợi ý hành động
    assert "refused" in action["message"].lower()        # lộ cause gốc
    print("[assert] Thông điệp lỗi nêu URL + gợi ý + cause. OK")

    # [3] retry/backoff: hỏng 503 hai lần rồi phục hồi
    print("\n[3] Lỗi transient 503 x2 -> adapter retry rồi thành công")
    flaky = _FlakyThenOkClient(fail_times=2)
    out = call_llm(msgs, client=flaky)
    print(f"    số lần gọi adaptee = {flaky.calls}; call_llm -> {out}")
    assert json.loads(out)["message"] == "recovered"
    assert flaky.calls == 3  # 2 lần hỏng + 1 lần được (max_retries=2 -> tối đa 3 lượt)
    print("[assert] Retry nuốt lỗi tạm thời, caller không thấy gì ngoài kết quả. OK")

    # [3b] hỏng nhiều hơn số retry -> envelope lỗi, vẫn không raise
    print("\n[3b] Lỗi transient nhiều hơn số retry -> envelope lỗi (vẫn không raise)")
    too_flaky = _FlakyThenOkClient(fail_times=5)
    out = call_llm(msgs, client=too_flaky)
    print(f"    số lần gọi adaptee = {too_flaky.calls}; call_llm -> {out}")
    assert json.loads(out)["finish_reason"] == "error"
    assert too_flaky.calls == 3  # cố hết 3 lượt rồi bỏ
    print("[assert] Hết retry vẫn trả envelope, không ném exception. OK")

    # [4] downgrade json_object -> text
    print("\n[4] Server từ chối json_object -> adapter hạ xuống text rồi thành công")
    picky = _RejectsJsonObjectClient()
    out = call_llm(msgs, client=picky)
    print("    formats đã thử:", picky.formats_seen)
    print("    call_llm ->", out)
    assert picky.formats_seen == [{"type": "json_object"}, {"type": "text"}]
    assert json.loads(out)["message"] == "text-mode ok"
    print("[assert] Adapter tự dịch sang text mode, không cần đổi cấu hình. OK")

    # [5] đối chứng: gọi adaptee trực tiếp -> caller lãnh exception
    print("\n[5] Đối chứng raw_call_no_adapter: gọi thẳng adaptee -> exception mờ mịt")
    raised = False
    try:
        raw_call_no_adapter(_DeadClient(), msgs)
    except Exception as exc:  # noqa: BLE001
        raised = True
        print(f"    raw -> RAISE {type(exc).__name__}: {exc}  (không biết đã thử URL nào)")
    assert raised, "không có adapter thì caller phải tự lãnh exception"
    print("[assert] Không adapter = mọi call site phải tự try/except + tự đoán nguyên nhân. OK")

    print("\nKẾT LUẬN: Adapter biến API hay-ném-exception, hay-đổi-status của LLM")
    print("thành một hợp đồng ổn định: luôn trả JSON, lỗi cũng là dữ liệu actionable.")


if __name__ == "__main__":
    demo()
