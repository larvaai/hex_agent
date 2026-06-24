"""KernelSession owns run state and capability scope; AgentKernel owns shared services."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.bootstrap import build_kernel
from core.session import SessionFactory

ECHO = {"features": {"example_echo": {"enabled": True, "module": "features.example_echo"}}}


def test_root_sessions_have_distinct_state_and_identity():
    kernel = build_kernel(ECHO)
    factory = SessionFactory(kernel=kernel)
    first = factory.create_root("one", run_id="run")
    second = factory.create_root("two", run_id="run")
    assert first.identity.session_id != second.identity.session_id
    assert first.identity.task_id != second.identity.task_id
    assert id(first.state) != id(second.state)
    first.state.set("private", {"items": [1]})
    assert second.state.get("private") is None


def test_child_scope_is_narrower_and_state_isolated():
    kernel = build_kernel(ECHO)
    factory = SessionFactory(kernel=kernel)
    parent = factory.create_root("parent", allowed_capabilities=frozenset({"echo"}))
    child = factory.create_child(
        parent,
        delegation_id="d1",
        target="agent:child",
        user_request="child",
        requested_scope=frozenset({"echo"}),
    )
    assert child.allowed_capabilities <= parent.allowed_capabilities
    assert child.identity.parent_session_id == parent.identity.session_id
    assert child.identity.delegation_id == "d1"
    child.state.set("private", "child")
    assert parent.state.get("private") is None


def test_child_cannot_expand_parent_scope():
    kernel = build_kernel(ECHO)
    parent = SessionFactory(kernel=kernel).create_root(
        "parent", allowed_capabilities=frozenset({"echo"})
    )
    with pytest.raises(PermissionError):
        SessionFactory(kernel=kernel).create_child(
            parent,
            delegation_id="d1",
            target="agent:child",
            user_request="child",
            requested_scope=frozenset({"echo", "terminal_run"}),
        )


def test_kernel_shared_configuration_freezes_on_first_session():
    kernel = build_kernel(ECHO)
    SessionFactory(kernel=kernel).create_root("x")
    with pytest.raises(RuntimeError, match="registry is frozen"):
        kernel.registry.register_tool("late", object())
    with pytest.raises(RuntimeError, match="pipeline is frozen"):
        kernel.use(lambda request, nxt: nxt(request))
    with pytest.raises(TypeError):
        kernel.config["features"]["late"] = {"enabled": True}


def test_session_scope_is_enforced_at_kernel_chokepoint():
    kernel = build_kernel(ECHO)
    session = SessionFactory(kernel=kernel).create_root("x", allowed_capabilities=frozenset())
    result = session.execute_tool("echo", {"x": 1})
    assert result["ok"] is False
    assert result["metadata"]["scope_block"] is True


def test_ten_sessions_do_not_cross_contaminate_state():
    kernel = build_kernel(ECHO)
    factory = SessionFactory(kernel=kernel)
    sessions = [factory.create_root(f"child-{index}") for index in range(10)]

    def write(index):
        session = sessions[index]
        session.state.set("owner", index)
        session.state.set("values", [index] * 50)

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(write, range(10)))

    assert len({id(session.state) for session in sessions}) == 10
    for index, session in enumerate(sessions):
        assert session.state.get("owner") == index
        assert session.state.get("values") == [index] * 50
