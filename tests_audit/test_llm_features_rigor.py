"""Strict audit of the LLM adapter + feature plugins: lazy client, JSON-mode request shape, retry/backoff classification, and the loader/echo/llm_chat plugin contracts."""
from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

import llm.adapter as adapter
from core.bootstrap import build_kernel
from core.schemas import ToolRequest
from core.session import SessionFactory
from discipline import parse_action
from features.example_echo import FEATURE as ECHO_FEATURE
from features.example_echo import EchoTool
from features.example_echo import install as install_echo
from features.llm_chat import FEATURE as LLM_FEATURE
from features.llm_chat import LLMChatTool
from features.llm_chat import install as install_llm
from features.loader import install_configured_features

OK = '{"action":"final","message":"ok"}'


# --------------------------------------------------------------------------- #
# Helpers — offline fakes mirroring tests/test_llm_adapter.py + audit conftest #
# --------------------------------------------------------------------------- #
def _response(content):
    """Build a fake OpenAI ChatCompletion response carrying `content`."""
    message = type("Message", (), {"content": content})()
    choice = type("Choice", (), {"message": message})()
    return type("Response", (), {"choices": [choice]})()


class _ScriptClient:
    """A client whose .chat.completions.create plays a strict script of
    Exceptions (raised) / str (returned as content) and records every kwargs."""

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict] = []
        outer = self

        class _Comp:
            def create(self, **kwargs):
                outer.calls.append(dict(kwargs))
                item = outer.script.pop(0)
                if isinstance(item, Exception):
                    raise item
                return _response(item)

        self.chat = type("Chat", (), {"completions": _Comp()})()


class _StatusError(Exception):
    """Duck-typed HTTP error carrying a status_code, like openai's APIStatusError."""

    def __init__(self, status, msg="err"):
        super().__init__(msg)
        self.status_code = status


@pytest.fixture(autouse=True)
def _reset_adapter_singleton():
    """The module-level client cache + sleep are process global; reset around each
    test so lazy-construction assertions are never contaminated by a prior test."""
    adapter.reset_client()
    original_sleep = adapter._sleep
    yield
    adapter._sleep = original_sleep
    adapter.reset_client()


# --------------------------------------------------------------------------- #
# LAZY client construction — the explicit target of missing lines 27-32        #
# --------------------------------------------------------------------------- #
def test_no_client_constructed_on_import_or_with_injected_client():
    # WHY: importing/using the adapter must NOT build a client (no network at import).
    assert adapter._client is None
    fake = _ScriptClient([OK])
    adapter.call_llm([{"role": "user", "content": "hi"}], client=fake)
    # Injected client path must never populate the module cache.
    assert adapter._client is None


def test_first_real_call_lazily_constructs_openai_with_env_config(monkeypatch):
    """WHY: pins lines 27-32 — the lazy import + OpenAI(...) construction from env.
    No real network: we replace openai.OpenAI with a recorder that returns a
    scripted client, and assert base_url/api_key/timeout come from env defaults."""
    monkeypatch.setenv("LLM_BASE_URL", "http://example.test/v1")
    monkeypatch.setenv("LLM_API_KEY", "secret-key")
    monkeypatch.setenv("LLM_TIMEOUT", "7.5")
    captured: dict = {}
    constructions: list[int] = []

    def fake_openai(**kwargs):
        constructions.append(1)
        captured.update(kwargs)
        return _ScriptClient([OK])

    import openai

    monkeypatch.setattr(openai, "OpenAI", fake_openai)

    assert adapter._client is None  # not built yet
    out = adapter.call_llm([{"role": "user", "content": "hi"}])
    assert out == OK
    assert captured == {
        "base_url": "http://example.test/v1",
        "api_key": "secret-key",
        "timeout": 7.5,
    }
    # Cached: a second call reuses the same client (no re-construction).
    adapter.call_llm([{"role": "user", "content": "hi"}])
    assert constructions == [1]
    assert adapter._client is not None


def test_reset_client_forces_reconstruction(monkeypatch):
    # WHY: reset_client() must drop the cache so the next call rebuilds.
    constructions: list[int] = []

    def fake_openai(**kwargs):
        constructions.append(1)
        return _ScriptClient([OK, OK])

    import openai

    monkeypatch.setattr(openai, "OpenAI", fake_openai)
    adapter.call_llm([{"role": "user", "content": "hi"}])
    adapter.reset_client()
    assert adapter._client is None
    adapter.call_llm([{"role": "user", "content": "hi"}])
    assert constructions == [1, 1]  # two distinct constructions


# --------------------------------------------------------------------------- #
# JSON-mode request shape                                                       #
# --------------------------------------------------------------------------- #
def test_json_mode_request_shape_full():
    # WHY: pin every field the adapter sends in JSON mode.
    fake = _ScriptClient([OK])
    msgs = [{"role": "user", "content": "hi"}]
    adapter.call_llm(msgs, model="m-x", temperature=0.7, client=fake)
    kw = fake.calls[0]
    assert kw["model"] == "m-x"
    assert kw["messages"] == msgs
    assert kw["temperature"] == 0.7
    assert kw["response_format"] == {"type": "json_object"}
    assert "max_tokens" in kw and isinstance(kw["max_tokens"], int)


def test_json_mode_off_omits_response_format():
    fake = _ScriptClient([OK])
    adapter.call_llm([{"role": "user", "content": "hi"}], json_mode=False, client=fake)
    assert "response_format" not in fake.calls[0]


def test_model_none_falls_back_to_config_default(monkeypatch):
    # WHY: model=None must resolve to LLM_MODEL env default, not literal None.
    monkeypatch.setenv("LLM_MODEL", "configured-default")
    fake = _ScriptClient([OK])
    adapter.call_llm([{"role": "user", "content": "hi"}], model=None, client=fake)
    assert fake.calls[0]["model"] == "configured-default"


def test_max_tokens_honors_env(monkeypatch):
    monkeypatch.setenv("LLM_MAX_TOKENS", "321")
    fake = _ScriptClient([OK])
    adapter.call_llm([{"role": "user", "content": "hi"}], client=fake)
    assert fake.calls[0]["max_tokens"] == 321


@pytest.mark.parametrize("content,expected", [(None, ""), ("", ""), ("payload", "payload")])
def test_none_or_empty_content_normalized_to_empty_string(content, expected):
    # WHY: `response.choices[0].message.content or ""` — None/"" must surface as "".
    fake = _ScriptClient([content])
    assert adapter.call_llm([{"role": "user", "content": "x"}], client=fake) == expected


def test_default_temperature_is_low():
    # WHY: deterministic default temperature (0.2) so JSON output is stable.
    fake = _ScriptClient([OK])
    adapter.call_llm([{"role": "user", "content": "x"}], client=fake)
    assert fake.calls[0]["temperature"] == 0.2


# --------------------------------------------------------------------------- #
# Retry / backoff classification                                               #
# --------------------------------------------------------------------------- #
def test_transient_then_success_uses_exponential_backoff(monkeypatch):
    """WHY: two transient 503s then success → 3 calls, and the recorded backoff
    sleeps are retry_base * 2**attempt (here base=0.5 → 0.5, 1.0)."""
    monkeypatch.setenv("LLM_MAX_RETRIES", "2")
    monkeypatch.setenv("LLM_RETRY_BASE", "0.5")
    slept: list[float] = []
    adapter._sleep = lambda d: slept.append(d)
    fake = _ScriptClient([_StatusError(503), _StatusError(503), OK])
    out = adapter.call_llm([{"role": "user", "content": "hi"}], client=fake)
    assert out == OK
    assert len(fake.calls) == 3
    assert slept == [0.5, 1.0]  # exp backoff schedule


def test_give_up_after_max_retries_returns_structured_error(monkeypatch):
    # WHY: transient that never resolves → exactly max_retries+1 calls, structured final.
    monkeypatch.setenv("LLM_MAX_RETRIES", "2")
    monkeypatch.setenv("LLM_RETRY_BASE", "0")
    fake = _ScriptClient([_StatusError(503), _StatusError(503), _StatusError(503), OK])
    action = parse_action(
        adapter.call_llm([{"role": "user", "content": "hi"}], client=fake)
    )
    assert action["action"] == "final"
    assert action["finish_reason"] == "error"
    assert len(fake.calls) == 3  # max_retries + 1; OK is never reached
    assert "3 attempt(s)" in action["message"]


def test_non_retryable_4xx_surfaces_immediately(monkeypatch):
    # WHY: a 400 is permanent — exactly one call, no retry, structured error.
    monkeypatch.setenv("LLM_MAX_RETRIES", "5")
    monkeypatch.setenv("LLM_RETRY_BASE", "0")
    slept: list[float] = []
    adapter._sleep = lambda d: slept.append(d)
    fake = _ScriptClient([_StatusError(400), OK])
    action = parse_action(
        adapter.call_llm([{"role": "user", "content": "hi"}], client=fake)
    )
    assert action["finish_reason"] == "error"
    assert len(fake.calls) == 1
    assert slept == []  # never slept — not transient


def test_max_retries_zero_means_single_attempt(monkeypatch):
    # WHY: boundary — max_retries=0 must still make one attempt (max(1, 0+1)).
    monkeypatch.setenv("LLM_MAX_RETRIES", "0")
    fake = _ScriptClient([_StatusError(503), OK])
    action = parse_action(
        adapter.call_llm([{"role": "user", "content": "hi"}], client=fake)
    )
    assert action["finish_reason"] == "error"
    assert len(fake.calls) == 1  # transient, but no retries budgeted


def test_unclassifiable_exception_is_permanent(monkeypatch):
    # WHY: a bare RuntimeError has no status + non-transient name → not retried.
    monkeypatch.setenv("LLM_MAX_RETRIES", "3")
    fake = _ScriptClient([RuntimeError("boom"), OK])
    action = parse_action(
        adapter.call_llm([{"role": "user", "content": "hi"}], client=fake)
    )
    assert action["finish_reason"] == "error"
    assert len(fake.calls) == 1


@pytest.mark.parametrize(
    "status,transient",
    [
        (429, True),   # rate limit
        (500, True),   # server error boundary
        (503, True),
        (599, True),
        (499, False),  # just below 5xx, not 429
        (400, False),
        (404, False),
        (428, False),  # just below 429
        (430, False),  # just above 429
    ],
)
def test_is_transient_status_boundaries(status, transient):
    # WHY: off-by-one around the 429 and 500 cutoffs.
    assert adapter._is_transient(_StatusError(status)) is transient


def test_is_transient_reads_status_attr_when_no_status_code():
    # WHY: classifier falls back to `.status` when `.status_code` is absent.
    exc = Exception("x")
    exc.status = 503  # type: ignore[attr-defined]
    assert adapter._is_transient(exc) is True
    exc2 = Exception("y")
    exc2.status = 400  # type: ignore[attr-defined]
    assert adapter._is_transient(exc2) is False


@pytest.mark.parametrize(
    "name,transient",
    [
        ("APITimeoutError", True),
        ("ConnectionResetError", True),
        ("ConnectionError", True),
        ("ValueError", False),
        ("KeyError", False),
    ],
)
def test_is_transient_classifies_by_exception_name(name, transient):
    # WHY: nameless (no status) exceptions are retried only if name says timeout/connection.
    exc = type(name, (Exception,), {})("msg")
    assert adapter._is_transient(exc) is transient


def test_non_int_status_falls_through_to_name_check():
    # WHY: a non-int status_code must not be treated as a status; name decides.
    class _Weird(Exception):
        status_code = "503"  # string, not int

    assert adapter._is_transient(_Weird()) is False  # name 'weird' → permanent

    class _WeirdTimeout(Exception):
        status_code = None

    assert adapter._is_transient(_WeirdTimeout()) is True  # name has 'timeout'


def test_429_then_timeout_then_success_both_retried(monkeypatch):
    # WHY: mixed transient kinds (status + named) both retry before final success.
    monkeypatch.setenv("LLM_MAX_RETRIES", "3")
    monkeypatch.setenv("LLM_RETRY_BASE", "0")
    Timeout = type("APITimeoutError", (Exception,), {})
    fake = _ScriptClient([_StatusError(429), Timeout("slow"), OK])
    out = adapter.call_llm([{"role": "user", "content": "hi"}], client=fake)
    assert out == OK and len(fake.calls) == 3


def test_call_llm_never_raises_returns_valid_action_json(monkeypatch):
    # WHY: invariant — the adapter must NEVER raise; the error path is always
    # a parseable action object the discipline gate can consume.
    monkeypatch.setenv("LLM_MAX_RETRIES", "0")
    fake = _ScriptClient([_StatusError(418, "teapot")])
    raw = adapter.call_llm([{"role": "user", "content": "x"}], client=fake)
    action = parse_action(raw)  # must not raise
    assert action["action"] == "final" and action["finish_reason"] == "error"


@given(
    base=st.floats(min_value=0, max_value=2, allow_nan=False, allow_infinity=False),
    retries=st.integers(min_value=1, max_value=4),
)
def test_backoff_schedule_property(monkeypatch, base, retries):
    """PROPERTY: when every attempt is transient, the adapter makes exactly
    retries+1 calls and sleeps retries times with schedule base*2**i."""
    monkeypatch.setenv("LLM_MAX_RETRIES", str(retries))
    monkeypatch.setenv("LLM_RETRY_BASE", str(base))
    slept: list[float] = []
    adapter._sleep = lambda d: slept.append(d)
    fake = _ScriptClient([_StatusError(503) for _ in range(retries + 1)])
    out = adapter.call_llm([{"role": "user", "content": "x"}], client=fake)
    assert parse_action(out)["finish_reason"] == "error"
    assert len(fake.calls) == retries + 1
    assert slept == [base * (2 ** i) for i in range(retries)]


# --------------------------------------------------------------------------- #
# features/loader.py — install only enabled, adversarial config                #
# --------------------------------------------------------------------------- #
def _empty_kernel():
    return build_kernel({"features": {}})


def test_loader_installs_only_enabled_features():
    # WHY: enabled echo installs its capability; disabled llm does not.
    kernel = build_kernel(
        {
            "features": {
                "example_echo": {"enabled": True, "module": "features.example_echo"},
                "llm": {"enabled": False, "module": "features.llm_chat"},
            }
        }
    )
    assert kernel.registry.has_tool("echo") is True
    assert kernel.registry.has_tool("llm.chat") is False


@pytest.mark.parametrize(
    "features",
    [
        {},                                        # no features at all
        {"a": {"enabled": False, "module": "x"}},  # disabled-only
        {"a": None},                               # spec None → treated as {} → disabled
        {"a": {}},                                 # spec without 'enabled' → defaults False
        {"a": {"enabled": 0, "module": "x"}},      # falsy enabled
    ],
)
def test_loader_noop_for_absent_or_disabled_specs(features, monkeypatch):
    # WHY: none of these should import anything; import_module must never be called.
    imported: list[str] = []
    monkeypatch.setattr(
        "features.loader.importlib.import_module",
        lambda path: imported.append(path),
    )
    install_configured_features(_empty_kernel(), {"features": features})
    assert imported == []


def test_loader_treats_missing_features_key_as_empty():
    # WHY: config without a 'features' key must be a harmless no-op (config.get default).
    kernel = _empty_kernel()
    install_configured_features(kernel, {})  # no 'features' key
    assert kernel.registry.has_tool("echo") is False


def test_loader_treats_features_none_as_empty():
    # WHY: features: null in YAML → `or {}` guard must absorb None.
    install_configured_features(_empty_kernel(), {"features": None})


def test_loader_enabled_without_module_raises_clear_error():
    # WHY: enabled feature missing 'module' → actionable ValueError naming the feature.
    with pytest.raises(ValueError, match="Feature 'broken' is enabled but has no 'module'"):
        install_configured_features(
            _empty_kernel(), {"features": {"broken": {"enabled": True}}}
        )


def test_loader_unknown_module_raises_import_error():
    # WHY: a real-but-wrong module path surfaces ModuleNotFoundError (clear failure).
    with pytest.raises(ModuleNotFoundError):
        install_configured_features(
            _empty_kernel(),
            {"features": {"ghost": {"enabled": True, "module": "no.such.module.xyz"}}},
        )


def test_loader_module_without_install_raises_clear_error(monkeypatch):
    # WHY: a module lacking install(kernel) → ValueError naming the module path.
    monkeypatch.setattr(
        "features.loader.importlib.import_module",
        lambda path: type("M", (), {})(),  # module object with no install
    )
    with pytest.raises(ValueError, match="has no install"):
        install_configured_features(
            _empty_kernel(),
            {"features": {"x": {"enabled": True, "module": "fake.mod"}}},
        )


def test_loader_install_order_follows_config_iteration(monkeypatch):
    # WHY: multiple enabled features install in declared order (dict iteration).
    order: list[str] = []

    def fake_import(path):
        return type("M", (), {"install": staticmethod(lambda k: order.append(path))})()

    monkeypatch.setattr("features.loader.importlib.import_module", fake_import)
    install_configured_features(
        _empty_kernel(),
        {
            "features": {
                "first": {"enabled": True, "module": "mod.first"},
                "second": {"enabled": True, "module": "mod.second"},
            }
        },
    )
    assert order == ["mod.first", "mod.second"]


# --------------------------------------------------------------------------- #
# features/example_echo.py — the plugin pattern                                #
# --------------------------------------------------------------------------- #
def test_echo_tool_returns_copy_of_args_not_alias():
    # WHY: tool must not leak/alias the caller's dict — defensive copy.
    tool = EchoTool()
    args = {"k": "v", "nested": [1, 2]}
    out = tool.execute(ToolRequest(name="echo", args=args))
    assert out == {"ok": True, "echo": {"k": "v", "nested": [1, 2]}}
    assert out["echo"] is not args  # dict(request.args) makes a shallow copy


def test_echo_install_registers_feature_and_capability():
    kernel = _empty_kernel()
    install_echo(kernel)
    assert kernel.registry.has_tool("echo") is True
    features = {f["name"] for f in kernel.registry.list_features()}
    assert ECHO_FEATURE.name in features


def test_echo_through_kernel_yields_envelope():
    # WHY: echo flows through the chokepoint and comes back as a CapabilityResult.
    kernel = _empty_kernel()
    install_echo(kernel)
    env = kernel.execute_tool("echo", {"hello": "world"})
    assert env["ok"] is True
    assert env["capability"] == "echo"
    assert env["feature"] == ECHO_FEATURE.name
    assert env["data"]["echo"] == {"hello": "world"}


def test_echo_kernel_copy_isolation():
    # WHY: kernel deep-copies args; mutating the source after the call is invisible.
    kernel = _empty_kernel()
    install_echo(kernel)
    src = {"x": 1}
    env = kernel.execute_tool("echo", src)
    src["x"] = 999
    assert env["data"]["echo"] == {"x": 1}


# --------------------------------------------------------------------------- #
# features/llm_chat.py — LLM as a capability through execute_tool              #
# --------------------------------------------------------------------------- #
def _kernel_with_llm(client):
    kernel = _empty_kernel()
    install_llm(kernel, client=client)
    return kernel


def test_llm_chat_install_registers_capability_and_feature():
    kernel = _kernel_with_llm(_ScriptClient([OK]))
    assert kernel.registry.has_tool("llm.chat") is True
    features = {f["name"] for f in kernel.registry.list_features()}
    assert LLM_FEATURE.name in features


def test_llm_chat_envelope_carries_content_and_model():
    # WHY: the tool result becomes a CapabilityResult envelope with content + model.
    fake = _ScriptClient([OK])
    kernel = _kernel_with_llm(fake)
    env = kernel.execute_tool(
        "llm.chat",
        {"messages": [{"role": "user", "content": "hi"}], "model": "m-2", "json_mode": True},
    )
    assert env["ok"] is True
    assert env["capability"] == "llm.chat"
    assert env["feature"] == LLM_FEATURE.name
    assert env["data"]["content"] == OK
    assert env["data"]["model"] == "m-2"
    assert fake.calls[0]["model"] == "m-2"
    assert fake.calls[0]["response_format"] == {"type": "json_object"}


def test_llm_chat_arg_defaults_when_args_omitted():
    # WHY: missing args default — empty messages, temperature 0.2, json_mode True, model None.
    fake = _ScriptClient([OK])
    kernel = _kernel_with_llm(fake)
    env = kernel.execute_tool("llm.chat", {})
    assert env["ok"] is True
    kw = fake.calls[0]
    assert kw["messages"] == []
    assert kw["temperature"] == 0.2
    assert kw["response_format"] == {"type": "json_object"}
    assert env["data"]["model"] is None


def test_llm_chat_json_mode_false_passes_through():
    fake = _ScriptClient([OK])
    kernel = _kernel_with_llm(fake)
    kernel.execute_tool("llm.chat", {"messages": [], "json_mode": False})
    assert "response_format" not in fake.calls[0]


def test_llm_chat_tool_error_still_yields_ok_envelope_with_error_content():
    """WHY: the adapter swallows LLM failures into a structured action string, so
    the tool itself returns ok=True; the FAILURE is encoded inside data.content."""
    fake = _ScriptClient([_StatusError(500)])
    kernel = _kernel_with_llm(fake)
    env = kernel.execute_tool("llm.chat", {"messages": []})
    assert env["ok"] is True  # tool didn't raise; error is in the payload
    action = parse_action(env["data"]["content"])
    assert action["finish_reason"] == "error"


def test_llm_chat_emits_tool_events_with_task_lineage():
    # WHY: llm.chat is observed like any tool — requested+completed events carry task_id.
    fake = _ScriptClient([OK])
    kernel = _kernel_with_llm(fake)
    seen: list[tuple[str, dict]] = []
    kernel.events.subscribe(lambda t, p: seen.append((t, p)))
    session = SessionFactory(kernel=kernel).create_root("llm trace")
    task = session.state.get("current_task")
    session.execute_tool("llm.chat", {"messages": []})
    topics = [t for t, _ in seen]
    assert "tool.requested" in topics
    assert "tool.completed" in topics
    for t, p in seen:
        if t.startswith("tool."):
            assert p["task_id"] == task.task_id


def test_llm_chat_default_client_is_none_uses_adapter_lazy_path(monkeypatch):
    # WHY: install without a client → tool calls adapter.call_llm with client=None,
    # which would lazily construct OpenAI. We stub OpenAI to prove the wiring (no net).
    import openai

    monkeypatch.setattr(openai, "OpenAI", lambda **kw: _ScriptClient([OK]))
    kernel = _empty_kernel()
    install_llm(kernel)  # no client injected
    env = kernel.execute_tool("llm.chat", {"messages": []})
    assert env["ok"] is True
    assert env["data"]["content"] == OK
    assert adapter._client is not None  # lazily built via the default path


def test_llm_chat_tool_direct_execute_contract():
    # WHY: pin the raw dict the tool returns before the kernel wraps it.
    fake = _ScriptClient([OK])
    tool = LLMChatTool(client=fake)
    out = tool.execute(ToolRequest(name="llm.chat", args={"messages": [], "model": "z"}))
    assert out == {"ok": True, "content": OK, "model": "z"}
