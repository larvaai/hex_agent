"""Text renderers over the projection — glyphs, connectors, decorations, log folding.

Builds TaskNode objects directly (not via reduce) to pin render_tree's formatting,
and feeds Events through render_log/render to pin the fold-then-render path.
"""
from dragzero import (
    Event,
    EventType,
    TaskNode,
    TaskStatus,
    render,
    render_log,
    render_tree,
)


def _node(desc="root", status=TaskStatus.PENDING.value, parent_id=None, nid="t-root", **kw):
    return TaskNode(id=nid, description=desc, parent_id=parent_id, status=status, **kw)


def test_render_tree_none_is_empty():
    assert render_tree(None) == "(empty)"


def test_done_root_renders_glyph_status_and_description():
    root = _node(desc="build the thing", status=TaskStatus.DONE.value)
    out = render_tree(root)
    assert "●" in out  # ● done glyph
    assert "[done]" in out
    assert "build the thing" in out
    # root has no connector
    assert "├─" not in out and "└─" not in out


def test_child_renders_with_connector_and_is_indented():
    root = _node(desc="parent", status=TaskStatus.RUNNING.value)
    child = _node(desc="kid", status=TaskStatus.DONE.value, parent_id="t-root", nid="t-kid")
    root.children.append(child)
    out = render_tree(root)
    lines = out.splitlines()
    assert len(lines) == 2
    parent_line, child_line = lines
    # only child carries a connector; last child uses └─
    assert "└─ " in child_line  # └─
    assert "├─" not in parent_line and "└─" not in parent_line
    # child is indented past the start of the parent's content
    assert child_line.startswith("   ")
    assert "kid" in child_line


def test_two_children_use_branch_and_last_connectors():
    root = _node(desc="parent", status=TaskStatus.RUNNING.value)
    root.children.append(_node(desc="first", parent_id="t-root", nid="c1"))
    root.children.append(_node(desc="second", parent_id="t-root", nid="c2"))
    lines = render_tree(root).splitlines()
    assert "├─ " in lines[1]  # ├─ non-last child branches
    assert "└─ " in lines[2]  # └─ last child closes


def test_next_step_shown_for_running_node():
    root = _node(status=TaskStatus.RUNNING.value, next_step="call the API")
    out = render_tree(root)
    assert "→ next: call the API" in out  # → next:


def test_next_step_hidden_for_done_node():
    root = _node(status=TaskStatus.DONE.value, next_step="should not appear")
    out = render_tree(root)
    assert "→ next:" not in out
    assert "should not appear" not in out


def test_blocked_on_shown_only_when_waiting():
    waiting = _node(status=TaskStatus.WAITING.value, blocked_on="upstream-task")
    out = render_tree(waiting)
    assert "for: upstream-task" in out


def test_blocked_on_hidden_when_not_waiting():
    # blocked_on set but status running -> the "for:" decoration is suppressed
    running = _node(status=TaskStatus.RUNNING.value, blocked_on="upstream-task")
    out = render_tree(running)
    assert "for:" not in out


def test_tools_render_gear_and_check():
    root = _node(status=TaskStatus.DONE.value, tools=[{"tool": "read_file", "ok": True}])
    out = render_tree(root)
    assert "⚙" in out  # ⚙
    assert "read_file✓" in out  # read_file✓


def test_tools_render_cross_when_not_ok():
    root = _node(status=TaskStatus.RUNNING.value, tools=[{"tool": "write_file", "ok": False}])
    out = render_tree(root)
    assert "write_file✗" in out  # write_file✗


def test_render_log_one_line_per_event_with_type():
    events = [
        Event(type=EventType.ROOT_TASK_CREATED, seq=0, task_id="t1", payload={"description": "go"}),
        Event(type=EventType.TASK_STARTED, seq=1, task_id="t1", agent_id="a1"),
    ]
    out = render_log(events)
    lines = out.splitlines()
    assert len(lines) == 2
    assert EventType.ROOT_TASK_CREATED.value in lines[0]
    assert EventType.TASK_STARTED.value in lines[1]


def test_render_folds_events_then_renders_tree():
    events = [
        Event(type=EventType.ROOT_TASK_CREATED, seq=0, task_id="t1", payload={"description": "ship it"}),
        Event(type=EventType.TASK_COMPLETED, seq=1, task_id="t1"),
    ]
    out = render(events)
    # folded root is DONE -> glyph + status + description from the fold
    assert "●" in out  # ●
    assert "[done]" in out
    assert "ship it" in out


def test_render_empty_events_is_empty():
    assert render([]) == "(empty)"
