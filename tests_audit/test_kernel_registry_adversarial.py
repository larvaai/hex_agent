"""Adversarial kernel, registry, feature-loader and event-bus contract tests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from core.bootstrap import build_kernel, load_config
from core.events import EventBus
from core.registry import CapabilityRegistry
from core.schemas import FeatureDescriptor
from core.session import SessionFactory
from features.loader import install_configured_features

pytestmark = pytest.mark.audit

ENVELOPE_KEYS = {"ok", "capability", "feature", "data", "error", "metadata"}


class RaisingTool:
    name = "raising"

    def execute(self, request):
        raise RuntimeError("secret internal failure")


class NonDictTool:
    name = "nondict"

    def execute(self, request):
        return ["not", "a", "dict"]


class MutatingTool:
    name = "mutator"

    def execute(self, request):
        request.args["nested"]["value"] = "mutated"
        return {"ok": True}


def empty_kernel():
    return build_kernel({"features": {}})


def test_tool_exception_is_normalized_and_events_remain_balanced():
    kernel = empty_kernel()
    kernel.registry.register_tool("raising", RaisingTool(), feature_name="audit")
    events = []
    kernel.events.subscribe(lambda topic, payload: events.append((topic, payload)))
    result = kernel.execute_tool("raising", {"x": 1})
    assert set(result) == ENVELOPE_KEYS
    assert result["ok"] is False
    assert result["data"]["kernel_error"] is True
    assert result["error"] == "secret internal failure"
    assert [topic for topic, _ in events] == ["tool.requested", "tool.failed"]
    assert events[0][1]["request_id"] == events[1][1]["request_id"]


def test_non_dict_executor_result_is_rejected_without_shape_leak():
    kernel = empty_kernel()
    kernel.registry.register_tool("nondict", NonDictTool())
    result = kernel.execute_tool("nondict")
    assert set(result) == ENVELOPE_KEYS
    assert result["ok"] is False
    assert result["data"]["kernel_error"] is True
    assert "expected dict" in result["error"]


def test_middleware_non_dict_result_is_normalized():
    kernel = empty_kernel()
    kernel.use(lambda request, nxt: "bad middleware result")
    result = kernel.execute_tool("anything")
    assert set(result) == ENVELOPE_KEYS
    assert result["ok"] is False
    assert "Middleware returned str" in result["error"]
    assert result["metadata"]["request_id"]


def test_middleware_exception_must_not_escape_the_kernel_boundary():
    kernel = empty_kernel()

    def explode(request, nxt):
        raise RuntimeError("middleware exploded")

    kernel.use(explode)
    result = kernel.execute_tool("anything")
    assert result["ok"] is False
    assert result["metadata"].get("kernel_error") is True
    assert "middleware exploded" in result["error"]


def test_tool_cannot_mutate_callers_argument_object():
    kernel = empty_kernel()
    kernel.registry.register_tool("mutator", MutatingTool())
    args = {"nested": {"value": "original"}}
    assert kernel.execute_tool("mutator", args)["ok"] is True
    assert args == {"nested": {"value": "original"}}


def test_observer_failure_isolated_and_later_observers_receive_pristine_payload():
    bus = EventBus()
    seen = []

    def bad_observer(topic, payload):
        payload["nested"]["x"] = 999
        raise RuntimeError("observer failure")

    bus.subscribe(bad_observer)
    bus.subscribe(lambda topic, payload: seen.append(payload))
    source = {"nested": {"x": 1}}
    bus.publish("topic", source)
    assert source == {"nested": {"x": 1}}
    assert seen == [{"nested": {"x": 1}}]


def test_registry_resolution_precedence_exact_then_fallback_then_null():
    registry = CapabilityRegistry()
    exact = object()
    fallback = object()
    registry.set_fallback_tool_executor(fallback, feature_name="fallback-feature")
    registry.register_tool("exact", exact, feature_name="exact-feature", kind="read", idempotent=True)

    exact_resolution = registry.resolve_tool("exact")
    assert exact_resolution.executor is exact
    assert exact_resolution.feature == "exact-feature"
    assert exact_resolution.descriptor.kind == "read"

    fallback_resolution = registry.resolve_tool("missing")
    assert fallback_resolution.executor is fallback
    assert fallback_resolution.feature == "fallback-feature"

    registry.set_fallback_tool_executor(None)
    null_resolution = registry.resolve_tool("missing")
    assert null_resolution.executor.name == "null_tool"
    assert null_resolution.feature is None


def test_every_registry_mutator_is_blocked_after_freeze():
    registry = CapabilityRegistry()
    registry.freeze()
    operations = [
        lambda: registry.register_feature(FeatureDescriptor("x")),
        lambda: registry.register_tool("x", object()),
        lambda: registry.register_tools(["x", "y"], object()),
        lambda: registry.set_fallback_tool_executor(object()),
    ]
    for operation in operations:
        with pytest.raises(RuntimeError, match="frozen"):
            operation()


def test_session_scope_block_happens_before_fallback_executor():
    kernel = empty_kernel()

    class ForbiddenFallback:
        name = "fallback"

        def execute(self, request):
            raise AssertionError("scope-blocked fallback must never execute")

    kernel.registry.set_fallback_tool_executor(ForbiddenFallback())
    session = SessionFactory(kernel=kernel).create_root("x", allowed_capabilities=frozenset())
    result = session.execute_tool("missing")
    assert result["ok"] is False
    assert result["metadata"]["scope_block"] is True


@pytest.mark.concurrency
def test_concurrent_tool_calls_have_unique_request_ids_and_correct_session_lineage():
    kernel = build_kernel(
        {"features": {"example_echo": {"enabled": True, "module": "features.example_echo"}}}
    )
    factory = SessionFactory(kernel=kernel)
    sessions = [factory.create_root(f"task-{index}", run_id="shared-run") for index in range(20)]

    def call(index):
        session = sessions[index % len(sessions)]
        result = session.execute_tool("echo", {"index": index})
        return result["metadata"]

    with ThreadPoolExecutor(max_workers=20) as pool:
        metadata = list(pool.map(call, range(1000)))

    request_ids = [item["request_id"] for item in metadata]
    assert len(request_ids) == len(set(request_ids)) == 1000
    known_sessions = {session.identity.session_id: session.identity.task_id for session in sessions}
    for item in metadata:
        assert known_sessions[item["session_id"]] == item["task_id"]
        assert item["run_id"] == "shared-run"


def test_load_config_missing_empty_and_non_mapping_inputs(tmp_path):
    assert load_config(tmp_path / "missing.yaml") == {"features": {}}
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    assert load_config(empty) == {"features": {}}
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a mapping"):
        load_config(invalid)


@pytest.mark.parametrize(
    "config, error",
    [
        ({"features": {"x": {"enabled": True}}}, "has no 'module'"),
        (
            {"features": {"x": {"enabled": True, "module": "tests_audit.fake_without_install"}}},
            "has no install",
        ),
    ],
)
def test_feature_loader_rejects_incomplete_plugins(config, error, monkeypatch):
    if "module" in config["features"]["x"]:
        fake_module = type("FakeModule", (), {})()
        monkeypatch.setattr("features.loader.importlib.import_module", lambda path: fake_module)
    with pytest.raises(ValueError, match=error):
        install_configured_features(empty_kernel(), config)


def test_feature_loader_does_not_import_disabled_plugin(monkeypatch):
    imported = []
    monkeypatch.setattr("features.loader.importlib.import_module", lambda path: imported.append(path))
    install_configured_features(
        empty_kernel(),
        {"features": {"disabled": {"enabled": False, "module": "must.not.import"}}},
    )
    assert imported == []


def test_kernel_config_is_deeply_frozen_but_original_input_remains_mutable():
    config = {"features": {}, "nested": {"items": [{"x": 1}]}}
    kernel = build_kernel(config)
    SessionFactory(kernel=kernel).create_root("freeze")
    config["nested"]["items"][0]["x"] = 2
    assert kernel.config["nested"]["items"][0]["x"] == 1
    with pytest.raises(TypeError):
        kernel.config["nested"]["items"][0]["x"] = 3
