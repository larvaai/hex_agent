"""Slice 6b — the code-owned acceptance gate.

The load-bearing claim: a node's verdict is CODE's, re-derived over the sandbox, never the
model's claim. These pin the anti-gaming walls (closed vocab, forgery rejection, no-artifact
=FAIL, freshness, path-jail) and prove through build_graph that a task the model marks
COMPLETED still reads FAIL when its artifact isn't on disk.
"""
import time

import pytest

from dragzero.adapters.tools_fs import FsSandbox
from dragzero.events import Event, EventLog, EventType
from dragzero.server import build_graph
from dragzero.verifier import DoneWhen, build_done_when, mu, run_checks


def _dw(check, artifact=None, **params):
    return DoneWhen(check=check, artifact=artifact, params=params)


# ── the gate is the sole verdict authority ────────────────────────────────────
def test_unknown_check_fails_closed(tmp_path):
    (tmp_path / "a.txt").write_text("x\n")
    v = run_checks([_dw("totally_made_up", "a.txt")], tmp_path)
    assert not v.ok and "unknown check" in v.results[0].reason


def test_empty_done_when_is_fail(tmp_path):
    # "nothing to check" is never a pass — no partial credit, no vacuous pass.
    assert run_checks([], tmp_path).node_verdict == "FAIL"


def test_missing_artifact_is_fail(tmp_path):
    assert not run_checks([_dw("file_exists", "nope.txt")], tmp_path).ok


def test_empty_artifact_is_fail(tmp_path):
    (tmp_path / "e.txt").write_text("")
    v = run_checks([_dw("file_exists", "e.txt")], tmp_path)
    assert not v.ok and "empty" in v.results[0].reason


def test_real_pass_over_disk(tmp_path):
    (tmp_path / "report.md").write_text("2 passed\ncoverage: 86%\n")
    v = run_checks([_dw("grep_matches", "report.md", pattern=r"\d+ passed")], tmp_path)
    assert v.ok and v.node_verdict == "PASS"


def test_stale_artifact_fails_against_activated_at(tmp_path):
    (tmp_path / "a.txt").write_text("fresh\n")
    future = time.time() + 1000  # pretend the node activated AFTER the file was written
    v = run_checks([_dw("file_exists", "a.txt")], tmp_path, activated_at=future)
    assert not v.ok and "stale" in v.results[0].reason


def test_all_children_done_blocks_the_empty_case(tmp_path):
    assert not run_checks([_dw("all_children_done")], tmp_path, child_statuses=[]).ok
    assert not run_checks([_dw("all_children_done")], tmp_path, child_statuses=["done", "running"]).ok
    assert run_checks([_dw("all_children_done")], tmp_path, child_statuses=["done", "done"]).ok


# ── the worker can never write a verdict ──────────────────────────────────────
@pytest.mark.parametrize("forged", ["verdict", "passed", "status", "score", "done"])
def test_verdict_field_is_rejected_at_construction(forged):
    with pytest.raises(ValueError, match="verdict"):
        DoneWhen.from_dict({"check": "file_exists", "artifact": "a.txt", forged: True})


def test_path_jail_rejects_escape():
    with pytest.raises(ValueError, match="escape"):
        DoneWhen.from_dict({"check": "file_exists", "artifact": "../../etc/passwd"})


def test_mu_is_done_when_count():
    assert mu([]) == 1  # an unsplittable node floors at 1
    assert mu(build_done_when([{"check": "all_children_done"}, {"check": "file_exists", "artifact": "a"}])) == 2


# ── through the projection: model CLAIM ≠ verdict ─────────────────────────────
def _log(*events):
    log = EventLog()
    for e in events:
        log.append(e)
    return log


def test_completed_task_with_missing_artifact_reads_FAIL(tmp_path):
    sandbox = FsSandbox(str(tmp_path))
    log = _log(
        Event(EventType.ROOT_TASK_CREATED, task_id="root", payload={"description": "build auth"}),
        Event(EventType.SUBTASK_SPAWNED, task_id="c1", agent_id="coder",
              payload={"parent": "root", "subtask": "write the suite"}),
        Event(EventType.TASK_COMPLETED, task_id="c1"),  # the model CLAIMS done
    )
    spec = {"coder": [{"check": "file_exists", "artifact": "tests/auth.test.ts"}]}

    c1 = next(n for n in build_graph(log, sandbox, spec)["nodes"] if n["id"] == "c1")
    assert c1["verdict"] == "FAIL"                  # code looked at disk: nothing there
    assert c1["runtime"]["status"] == "blocked"     # the FAIL overrides the "done" claim

    sandbox.write("tests/auth.test.ts", "// import { signToken }\n")  # now the agent really wrote it
    c1b = next(n for n in build_graph(log, sandbox, spec)["nodes"] if n["id"] == "c1")
    assert c1b["verdict"] == "PASS" and c1b["runtime"]["status"] == "done"


def test_node_without_spec_is_unverified_not_passed(tmp_path):
    sandbox = FsSandbox(str(tmp_path))
    log = _log(
        Event(EventType.ROOT_TASK_CREATED, task_id="root", payload={"description": "x"}),
        Event(EventType.TASK_COMPLETED, task_id="root"),
    )
    root = build_graph(log, sandbox, spec={})["nodes"][0]
    assert root["verdict"] == "unverified"  # no criteria authored → honest, never a faked pass
    assert root["done_when"] == []
