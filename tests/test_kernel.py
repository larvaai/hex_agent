from core.bootstrap import build_kernel, create_kernel

ECHO = {"features": {"example_echo": {"enabled": True, "module": "features.example_echo"}}}
DISABLED = {"features": {"example_echo": {"enabled": False, "module": "features.example_echo"}}}


def test_execute_registered_tool():
    k = build_kernel(ECHO)
    r = k.execute_tool("echo", {"msg": "hi"})
    assert r["ok"] is True
    assert r["capability"] == "echo"
    assert r["feature"] == "example_echo"
    assert r["data"]["echo"] == {"msg": "hi"}


def test_unknown_tool_null_fallback():
    k = build_kernel(ECHO)
    r = k.execute_tool("nope")
    assert r["ok"] is False
    assert r["data"].get("missing_capability") is True


def test_disabled_feature_not_registered():
    k = build_kernel(DISABLED)
    assert k.registry.has_tool("echo") is False
    r = k.execute_tool("echo")
    assert r["ok"] is False
    assert r["data"].get("missing_capability") is True


def test_events_emitted():
    k = build_kernel(ECHO)
    seen: list[str] = []
    k.events.subscribe(lambda topic, payload: seen.append(topic))
    k.execute_tool("echo", {"a": 1})
    assert "tool.requested" in seen
    assert "tool.completed" in seen


def test_describe_capabilities():
    k = build_kernel(ECHO)
    desc = k.describe_capabilities()
    assert "echo" in [t["name"] for t in desc["tools"]]
    assert any(f["name"] == "example_echo" for f in desc["features"])


def test_default_config_loads():
    k = create_kernel()
    assert k.registry.has_tool("echo")
