"""Rigor for orchestrator.loop + orchestrator.checkpoint: run/resume facade, projection, error branches."""
from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core.bootstrap import build_kernel
from core.schemas import TaskEnvelope
from core.session import SessionFactory, SessionIdentity
from discipline import Budget
from features.llm_chat import FEATURE as LLM_FEATURE
from features.llm_chat import LLMChatTool
from graph.state import encode_session_state
from orchestrator import resume, run
from orchestrator.checkpoint import (
    Checkpoint,
    checkpoint_db_path,
    checkpoint_path,
    load_checkpoint,
    open_checkpointer,
    save_checkpoint,
    save_graph_projection,
)
from orchestrator.loop import (
    _legacy_state,
    _outcome,
    _restore_persisted_session,
    _stream,
    _sync_budget,
)

FINAL_DONE = '{"action":"final","message":"done","finish_reason":"done"}'


# --------------------------------------------------------------------------- #
# Test agent helper (a kernel with a scripted llm.chat tool).                  #
# --------------------------------------------------------------------------- #
def _agent(scripted_client, *responses):
    """Build a kernel whose llm.chat replays `responses`. Reuses the audit scripted_client fixture."""
    kernel = build_kernel(
        {"features": {"example_echo": {"enabled": True, "module": "features.example_echo"}}}
    )
    client = scripted_client(list(responses))
    kernel.registry.register_feature(LLM_FEATURE)
    kernel.registry.register_tools(
        LLM_FEATURE.capabilities,
        LLMChatTool(client=client),
        feature_name=LLM_FEATURE.name,
        kind="model",
        idempotent=True,
    )
    return kernel, client


# =========================================================================== #
# run() — the public facade over the compiled LangGraph.                      #
# =========================================================================== #
@pytest.mark.audit
def test_run_completes_and_syncs_budget_back_into_caller_object(scripted_client):
    """run() returns the terminal outcome AND mutates the passed Budget (one step consumed)."""
    kernel, client = _agent(scripted_client, FINAL_DONE)
    budget = Budget(max_steps=5)

    outcome = run(kernel, "do the thing", budget=budget, run_id="r-sync", checkpoint=False)

    assert outcome["status"] == "completed"
    assert outcome["result"] == "done"
    assert budget.steps == 1  # _sync_budget wrote the persisted step count back
    assert len(client.calls) == 1


@pytest.mark.audit
def test_run_checkpoint_off_writes_no_durable_or_projection_artifacts(scripted_client):
    """checkpoint=False must leave neither the SQLite DB nor the JSON projection on disk."""
    kernel, _ = _agent(scripted_client, FINAL_DONE)
    run(kernel, "ephemeral", run_id="off-run", checkpoint=False)

    assert not checkpoint_db_path("off-run").exists()
    assert not checkpoint_path("off-run").exists()
    assert load_checkpoint("off-run") is None


@pytest.mark.audit
def test_run_checkpoint_on_writes_sqlite_and_langgraph_projection(scripted_client):
    """checkpoint=True persists the authoritative SQLite DB and a langgraph-backed JSON projection."""
    kernel, _ = _agent(scripted_client, FINAL_DONE)
    run(kernel, "durable", run_id="on-run", checkpoint=True)

    assert checkpoint_db_path("on-run").exists()
    cp = load_checkpoint("on-run")
    assert cp is not None
    assert cp.status == "completed"
    assert cp.backend == "langgraph"
    assert cp.step == 1


@pytest.mark.audit
def test_run_projection_shape_is_the_documented_read_model(scripted_client):
    """Pin the JSON run-state projection: stable top-level keys + decoded TaskEnvelope in state."""
    kernel, _ = _agent(scripted_client, FINAL_DONE)
    run(kernel, "shape", run_id="shape-run", checkpoint=True)

    raw = json.loads(checkpoint_path("shape-run").read_text(encoding="utf-8"))
    assert set(raw) == {
        "run_id",
        "task",
        "messages",
        "budget",
        "state",
        "step",
        "status",
        "backend",
        "schema_version",
    }
    assert raw["run_id"] == "shape-run"
    assert raw["task"] == "shape"
    assert raw["backend"] == "langgraph"
    assert raw["status"] == "completed"
    # A completed run closes the task: current_task is null and last_result holds the outcome.
    assert raw["state"]["current_task"] is None
    assert raw["state"]["last_result"]["status"] == "completed"
    assert raw["state"]["last_result"]["result"] == "done"
    assert load_checkpoint("shape-run").state["current_task"] is None


@pytest.mark.audit
def test_running_projection_encodes_current_task_as_task_envelope_on_disk():
    """A mid-flight (running) projection stores current_task as a {"__task__": ...} envelope, decoded on load."""
    import os
    import tempfile

    tmp = tempfile.mkdtemp()
    prev = os.environ.get("AGENT_RUNS_DIR")
    os.environ["AGENT_RUNS_DIR"] = tmp
    try:
        task = TaskEnvelope(user_request="mid", task_id="MID")
        save_graph_projection(
            {
                "run_id": "running-proj",
                "task": "mid",
                "status": "running",
                "budget": {"steps": 1},
                "session_state": encode_session_state({"current_task": task}),
            }
        )
        raw = json.loads(checkpoint_path("running-proj").read_text(encoding="utf-8"))
        assert raw["status"] == "running"
        assert "__task__" in raw["state"]["current_task"]
        assert raw["state"]["current_task"]["__task__"]["task_id"] == "MID"
        decoded = load_checkpoint("running-proj").state["current_task"]
        assert isinstance(decoded, TaskEnvelope)
        assert decoded.task_id == "MID"
    finally:
        if prev is None:
            os.environ.pop("AGENT_RUNS_DIR", None)
        else:
            os.environ["AGENT_RUNS_DIR"] = prev


@pytest.mark.audit
def test_run_rejects_foreign_or_mismatched_session(scripted_client):
    """The run() preconditions guard kernel ownership, task ownership, and run_id agreement."""
    own, _ = _agent(scripted_client, FINAL_DONE)
    other, _ = _agent(scripted_client, FINAL_DONE)

    foreign = SessionFactory(kernel=other).create_root("task", run_id="rid")
    with pytest.raises(ValueError, match="different kernel"):
        run(own, "task", session=foreign, checkpoint=False)

    session = SessionFactory(kernel=own).create_root("owned", run_id="rid")
    with pytest.raises(ValueError, match="own the requested task"):
        run(own, "a-different-request", session=session, checkpoint=False)
    with pytest.raises(ValueError, match="run_id"):
        run(own, "owned", session=session, run_id="not-rid", checkpoint=False)


@pytest.mark.audit
def test_run_default_run_id_is_the_task_id_when_unspecified(scripted_client):
    """Without an explicit run_id the facade derives a stable run_id (== task_id) for the projection."""
    kernel, _ = _agent(scripted_client, FINAL_DONE)
    outcome = run(kernel, "auto-id", checkpoint=True)

    task_id = outcome["task_id"]
    assert task_id
    # The projection is keyed by the derived run_id, which equals the task_id for a root run.
    assert load_checkpoint(task_id) is not None


@pytest.mark.audit
def test_run_with_delegation_service_injects_targets_into_system_prompt(scripted_client):
    """A delegation service contributes its targets to the appended system prompt sent to the LLM."""

    class _Delegation:
        def available_targets(self):
            return ("agent:planner", "agent:coder")

    kernel, client = _agent(scripted_client, FINAL_DONE)
    outcome = run(
        kernel,
        "q",
        run_id="deleg-run",
        delegation_service=_Delegation(),
    )
    assert outcome["status"] == "completed"
    # The system message the model saw carries the delegation grammar with the listed targets.
    system_prompt = client.calls[0]["messages"][0]["content"]
    assert "Delegation targets: agent:planner, agent:coder" in system_prompt
    assert '"action":"delegate"' in system_prompt


@pytest.mark.audit
def test_run_without_delegation_service_appends_no_delegation_grammar(scripted_client):
    """With no delegation service the prompt stays the bare DEFAULT_SYSTEM (no delegate verb)."""
    kernel, client = _agent(scripted_client, FINAL_DONE)
    run(kernel, "q", run_id="no-deleg", checkpoint=False)
    system_prompt = client.calls[0]["messages"][0]["content"]
    assert "Delegation targets" not in system_prompt
    assert '"action":"delegate"' not in system_prompt


@pytest.mark.audit
def test_run_llm_transport_failure_surfaces_root_cause_in_failed_outcome(scripted_client):
    """A raised provider error must terminate as a failed outcome carrying the root cause string."""
    kernel, _ = _agent(scripted_client, RuntimeError("provider socket reset"))
    outcome = run(kernel, "task", budget=Budget(max_steps=3, max_parse_errors=1), checkpoint=False)

    assert outcome["status"] == "failed"
    assert "provider socket reset" in outcome["result"]["reason"]


# =========================================================================== #
# resume() — error branches (the assignment's headline cases).                #
# =========================================================================== #
@pytest.mark.audit
def test_resume_unknown_run_with_no_artifacts_raises_file_not_found(scripted_client):
    """resume() of a run_id that has neither a SQLite DB nor a legacy projection raises FileNotFoundError."""
    kernel, _ = _agent(scripted_client)
    assert not checkpoint_db_path("ghost").exists()
    with pytest.raises(FileNotFoundError, match="ghost"):
        resume(kernel, "ghost")


@pytest.mark.audit
def test_resume_empty_sqlite_db_raises_file_not_found(scripted_client):
    """An existing-but-empty SQLite DB (no thread written) hits the get_tuple-is-None guard."""
    run_id = "empty-db"
    with open_checkpointer(run_id):
        pass  # creates the DB + schema, writes no checkpoint tuple
    assert checkpoint_db_path(run_id).exists()

    kernel, _ = _agent(scripted_client)
    with pytest.raises(FileNotFoundError, match="empty-db"):
        resume(kernel, run_id)


@pytest.mark.audit
def test_resume_completed_run_replays_stored_outcome_without_touching_llm(scripted_client):
    """A finished run resumes to its stored outcome and must NOT issue any fresh LLM call."""
    first, first_client = _agent(scripted_client, '{"action":"final","message":"once","finish_reason":"done"}')
    assert run(first, "task", run_id="done")["result"] == "once"
    assert len(first_client.calls) == 1

    # Empty script: any LLM call would raise "scripted responses exhausted".
    second, second_client = _agent(scripted_client)
    outcome = resume(second, "done")

    assert outcome["status"] == "completed"
    assert outcome["result"] == "once"
    assert second_client.calls == []


@pytest.mark.audit
def test_resume_interrupted_run_continues_from_sqlite_to_completion(scripted_client):
    """Tool step succeeds, process crashes before the next LLM call; resume continues to FINISHED."""
    first, _ = _agent(scripted_client, '{"action":"tool","tool":"echo","args":{"k":1}}')
    original = first.execute_tool
    llm_calls = {"n": 0}

    def crash_before_second_llm(name, args=None, **kwargs):
        if name == "llm.chat":
            llm_calls["n"] += 1
            if llm_calls["n"] == 2:
                raise RuntimeError("crash after tool, before 2nd llm")
        return original(name, args, **kwargs)

    first.execute_tool = crash_before_second_llm
    with pytest.raises(RuntimeError, match="crash after tool"):
        run(first, "tool then continue", run_id="cont")

    mid = load_checkpoint("cont")
    assert mid.status == "running"  # the run is genuinely mid-flight, not terminal

    second, second_client = _agent(scripted_client, '{"action":"final","message":"continued","finish_reason":"done"}')
    outcome = resume(second, "cont")

    assert outcome["status"] == "completed"
    assert outcome["result"] == "continued"
    assert len(second_client.calls) == 1  # exactly one fresh call finalized the run


@pytest.mark.audit
def test_resume_reproduces_task_identity_across_process_boundary(scripted_client):
    """The task_id persisted before a crash is the same task_id returned after resume."""
    first, _ = _agent(scripted_client)
    original = first.execute_tool

    def crash_first_llm(name, args=None, **kwargs):
        if name == "llm.chat":
            raise RuntimeError("crash on first llm")
        return original(name, args, **kwargs)

    first.execute_tool = crash_first_llm
    with pytest.raises(RuntimeError):
        run(first, "survive restart", run_id="reproduce")

    persisted_task_id = load_checkpoint("reproduce").state["current_task"].task_id
    second, _ = _agent(scripted_client, '{"action":"final","message":"recovered","finish_reason":"done"}')
    outcome = resume(second, "reproduce")

    assert outcome["status"] == "completed"
    assert outcome["task_id"] == persisted_task_id


# =========================================================================== #
# Legacy-JSON migration path (_legacy_state) — the pre-LangGraph compat road.  #
# =========================================================================== #
@pytest.mark.audit
def test_resume_legacy_completed_returns_stored_last_result(scripted_client):
    """A legacy-json checkpoint with status!=running short-circuits to its stored last_result."""
    save_checkpoint(
        Checkpoint(
            run_id="legacy-done",
            task="do it",
            status="completed",
            state={"last_result": {"task_id": "T1", "status": "completed", "result": "legacy-result"}},
            backend="legacy-json",
        )
    )
    assert not checkpoint_db_path("legacy-done").exists()

    kernel, _ = _agent(scripted_client)  # empty script: resume must not call the LLM
    outcome = resume(kernel, "legacy-done")
    assert outcome == {"task_id": "T1", "status": "completed", "result": "legacy-result"}


@pytest.mark.audit
def test_resume_legacy_terminal_without_last_result_synthesizes_outcome(scripted_client):
    """A legacy terminal checkpoint lacking last_result yields a synthesized {task_id:None,...} outcome."""
    save_checkpoint(
        Checkpoint(run_id="legacy-fail", task="x", status="failed", state={}, backend="legacy-json")
    )
    kernel, _ = _agent(scripted_client)
    outcome = resume(kernel, "legacy-fail")
    assert outcome == {"task_id": None, "status": "failed", "result": None}


@pytest.mark.audit
def test_resume_legacy_running_without_envelope_migrates_and_continues(scripted_client):
    """A running legacy checkpoint whose state has no TaskEnvelope is migrated from .task then run."""
    save_checkpoint(
        Checkpoint(
            run_id="legacy-run",
            task="resume me",
            status="running",
            messages=[
                {"role": "system", "content": "s"},
                {"role": "user", "content": "resume me"},
            ],
            budget={
                "max_steps": 30,
                "max_parse_errors": 3,
                "max_same_tool_calls": 3,
                "steps": 0,
                "parse_errors": 0,
                "_tool_calls": {},
            },
            state={},  # no current_task -> _legacy_state builds one from .task / run_id
            step=0,
            backend="legacy-json",
        )
    )
    kernel, _ = _agent(scripted_client, '{"action":"final","message":"legacy-resumed","finish_reason":"done"}')
    outcome = resume(kernel, "legacy-run")
    assert outcome["status"] == "completed"
    assert outcome["result"] == "legacy-resumed"
    assert outcome["task_id"] == "legacy-run"  # synthesized envelope took run_id as task_id


@pytest.mark.audit
def test_legacy_state_missing_projection_raises(scripted_client):
    """_legacy_state with no projection on disk raises FileNotFoundError."""
    kernel, _ = _agent(scripted_client)
    with pytest.raises(FileNotFoundError, match="ghost"):
        _legacy_state(kernel, "ghost")


@pytest.mark.audit
def test_legacy_state_rejects_non_legacy_backend(scripted_client):
    """_legacy_state refuses a langgraph-backed projection (resume must go through SQLite instead)."""
    save_checkpoint(Checkpoint(run_id="lg", task="x", status="running", backend="langgraph"))
    kernel, _ = _agent(scripted_client)
    with pytest.raises(FileNotFoundError, match="lg"):
        _legacy_state(kernel, "lg")


# =========================================================================== #
# _restore_persisted_session — identity/scope reconstruction fallbacks.        #
# =========================================================================== #
@pytest.mark.audit
def test_restore_session_synthesizes_identity_and_full_scope_when_absent(scripted_client):
    """No session_identity + allowed_capabilities=None -> identity built from task_id, full tool scope."""
    kernel, _ = _agent(scripted_client)
    task = TaskEnvelope(user_request="restore-me", task_id="TID-9")
    persisted = {
        "session_state": encode_session_state({"current_task": task}),
        "task_id": "TID-9",
        # deliberately no "session_identity" and no "allowed_capabilities"
    }
    session = _restore_persisted_session(kernel, "run-x", persisted)

    assert session.identity.run_id == "run-x"
    assert session.identity.task_id == "TID-9"
    assert session.identity.agent_id == "agent:root"
    # allowed=None falls back to the kernel's full registered tool set.
    registered = {item["name"] for item in kernel.registry.list_tools()}
    assert session.allowed_capabilities == frozenset(registered)
    assert "llm.chat" in session.allowed_capabilities


@pytest.mark.audit
def test_restore_session_identity_falls_back_to_run_id_when_no_task(scripted_client):
    """With neither identity, task_id, nor a TaskEnvelope, identity.task_id defaults to run_id."""
    kernel, _ = _agent(scripted_client)
    session = _restore_persisted_session(kernel, "run-y", {"session_state": {}})
    assert session.identity.task_id == "run-y"
    assert session.identity.run_id == "run-y"


@pytest.mark.audit
def test_restore_session_honors_explicit_identity_and_scope(scripted_client):
    """A persisted dict identity + explicit allowed_capabilities are used verbatim (subset of runtime)."""
    kernel, _ = _agent(scripted_client)
    identity = SessionIdentity(
        session_id="S", run_id="run-z", task_id="task-z", agent_id="agent:custom"
    )
    persisted = {
        "session_identity": identity.as_dict(),
        "allowed_capabilities": ["echo"],
        "session_state": encode_session_state({"current_task": TaskEnvelope(user_request="u")}),
    }
    session = _restore_persisted_session(kernel, "run-z", persisted)
    assert session.identity.agent_id == "agent:custom"
    assert session.identity.task_id == "task-z"
    assert session.allowed_capabilities == frozenset({"echo"})


@pytest.mark.audit
@pytest.mark.security
def test_restore_session_rejects_capabilities_not_in_runtime(scripted_client):
    """Restoring a scope wider than the runtime's tools is a privilege-escalation guard -> ValueError."""
    kernel, _ = _agent(scripted_client)
    persisted = {
        "allowed_capabilities": ["echo", "tool.that.does.not.exist"],
        "session_state": encode_session_state({"current_task": TaskEnvelope(user_request="u")}),
        "task_id": "t",
    }
    with pytest.raises(ValueError, match="unavailable in this runtime"):
        _restore_persisted_session(kernel, "run-esc", persisted)


# =========================================================================== #
# _outcome — projection of terminal state into the public result shape.        #
# =========================================================================== #
@pytest.mark.audit
def test_outcome_prefers_explicit_outcome_dict():
    """When state carries a dict 'outcome', it is returned verbatim."""
    assert _outcome({"outcome": {"task_id": "A", "status": "completed", "result": "R"}}) == {
        "task_id": "A",
        "status": "completed",
        "result": "R",
    }


@pytest.mark.audit
def test_outcome_synthesizes_from_fields_when_outcome_missing_or_not_a_dict():
    """No/invalid 'outcome' -> derive from task_id/status/final, defaulting status to 'incomplete'."""
    assert _outcome({"task_id": "A", "status": "running", "final": "F"}) == {
        "task_id": "A",
        "status": "running",
        "result": "F",
    }
    # Missing keys default sensibly; a non-dict outcome value is ignored.
    assert _outcome({"outcome": "not-a-dict"}) == {
        "task_id": None,
        "status": "incomplete",
        "result": None,
    }
    assert _outcome({}) == {"task_id": None, "status": "incomplete", "result": None}


# =========================================================================== #
# _stream — final-state fallback + projection-on-error.                         #
# =========================================================================== #
@pytest.mark.audit
def test_stream_falls_back_to_graph_snapshot_when_stream_yields_nothing():
    """If graph.stream yields no values and input is None, the live snapshot supplies final_state."""

    class _Snap:
        def __init__(self, values):
            self.values = values
            self.next = ()

    class _Graph:
        def __init__(self, values):
            self._values = values

        def stream(self, graph_input, config, stream_mode="values"):
            return iter(())  # yields nothing

        def get_state(self, config):
            return _Snap(self._values)

    final = _stream(
        _Graph({"status": "completed", "via": "snapshot"}),
        None,
        config={"configurable": {"thread_id": "t"}},
        projection=False,
    )
    assert final == {"status": "completed", "via": "snapshot"}


@pytest.mark.audit
def test_stream_persists_projection_then_reraises_on_error(tmp_path, monkeypatch):
    """On a mid-stream exception with projection on, the last good snapshot is flushed, then re-raised."""
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path / "runs"))

    class _Snap:
        def __init__(self, values):
            self.values = values
            self.next = ()

    class _Graph:
        def stream(self, graph_input, config, stream_mode="values"):
            yield {"run_id": "boom", "task": "t", "status": "running", "budget": {"steps": 0}}
            raise RuntimeError("mid-stream blowup")

        def get_state(self, config):
            return _Snap(
                {"run_id": "boom", "task": "t", "status": "running", "budget": {"steps": 1}}
            )

    with pytest.raises(RuntimeError, match="mid-stream blowup"):
        _stream(
            _Graph(),
            {"run_id": "boom"},
            config={"configurable": {"thread_id": "boom"}},
            projection=True,
        )

    # The error handler flushed the snapshot projection to disk before re-raising.
    cp = load_checkpoint("boom")
    assert cp is not None
    assert cp.status == "running"
    assert cp.step == 1  # snapshot's budget.steps, not the earlier streamed value


@pytest.mark.audit
def test_stream_error_with_empty_snapshot_does_not_write_projection(tmp_path, monkeypatch):
    """An error whose recovery snapshot has empty values must not emit a misleading projection."""
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path / "runs"))

    class _Snap:
        values = {}
        next = ()

    class _Graph:
        def stream(self, graph_input, config, stream_mode="values"):
            raise RuntimeError("blow up before any value")
            yield  # pragma: no cover

        def get_state(self, config):
            return _Snap()

    with pytest.raises(RuntimeError, match="blow up"):
        _stream(_Graph(), None, config={"configurable": {"thread_id": "x"}}, projection=True)
    assert load_checkpoint("x") is None


# =========================================================================== #
# _sync_budget — persisted counters flow back into the caller's Budget.        #
# =========================================================================== #
@pytest.mark.audit
def test_sync_budget_copies_steps_parse_errors_and_tool_calls():
    """_sync_budget mirrors the persisted counters and copies (does not alias) the tool-call map."""
    target = Budget()
    persisted_map = {"echo:{}": 2}
    state = {
        "budget": {
            "max_steps": 30,
            "max_parse_errors": 3,
            "max_same_tool_calls": 3,
            "steps": 7,
            "parse_errors": 2,
            "_tool_calls": persisted_map,
        }
    }
    _sync_budget(target, state)
    assert target.steps == 7
    assert target.parse_errors == 2
    assert target._tool_calls == {"echo:{}": 2}
    # Mutating the source map afterwards must not bleed into the synced budget (defensive copy).
    persisted_map["echo:{}"] = 99
    assert target._tool_calls == {"echo:{}": 2}


# =========================================================================== #
# checkpoint.py — Checkpoint codec, projection, atomicity, malformed input.    #
# =========================================================================== #
@pytest.mark.audit
def test_checkpoint_path_and_db_path_are_distinct_per_run():
    """The UI projection JSON and the authoritative SQLite DB live at different, run-scoped paths."""
    p = checkpoint_path("abc")
    db = checkpoint_db_path("abc")
    assert p != db
    assert p.name == "checkpoint.json"
    assert db.name == "langgraph.sqlite"
    assert p.parent == db.parent  # both under runs/<run_id>/


@pytest.mark.audit
def test_checkpoint_from_json_requires_nonempty_string_run_id():
    """from_json is the trust boundary for external JSON: run_id must be a non-empty string."""
    with pytest.raises(ValueError, match="run_id"):
        Checkpoint.from_json({})
    with pytest.raises(ValueError, match="run_id"):
        Checkpoint.from_json({"run_id": ""})
    with pytest.raises((TypeError, ValueError), match="run_id"):
        Checkpoint.from_json({"run_id": ["not", "a", "string"]})
    with pytest.raises((TypeError, ValueError), match="run_id"):
        Checkpoint.from_json({"run_id": 12345})


@pytest.mark.audit
def test_checkpoint_from_json_defaults_legacy_schema_version_to_one():
    """A v1 (pre-schema_version) JSON blob defaults schema_version=1 and backend=legacy-json."""
    cp = Checkpoint.from_json({"run_id": "r"})
    assert cp.schema_version == 1
    assert cp.backend == "legacy-json"
    assert cp.status == "running"
    assert cp.messages == []
    assert cp.budget == {}


@pytest.mark.audit
def test_checkpoint_from_graph_state_reads_migration_kernel_state_key():
    """from_graph_state honors the v1 'kernel_state' migration alias and derives step from budget.steps."""
    cp = Checkpoint.from_graph_state(
        {
            "run_id": "g",
            "task": "t",
            "status": "running",
            "budget": {"steps": 5},
            "kernel_state": {
                "current_task": {
                    "__task__": {
                        "task_id": "X",
                        "user_request": "u",
                        "context": {},
                        "metadata": {},
                    }
                }
            },
        }
    )
    assert cp.step == 5
    assert cp.backend == "langgraph"
    assert isinstance(cp.state["current_task"], TaskEnvelope)
    assert cp.state["current_task"].task_id == "X"


@pytest.mark.audit
def test_checkpoint_from_graph_state_defaults_status_to_running():
    """A graph state with no status string projects to 'running' rather than empty/None."""
    cp = Checkpoint.from_graph_state({"run_id": "g", "task": "t"})
    assert cp.status == "running"
    assert cp.step == 0


@pytest.mark.audit
def test_save_disabled_writes_nothing(tmp_path, monkeypatch):
    """save_checkpoint(enabled=False) and save_graph_projection(enabled=False) are pure no-ops."""
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path / "runs"))
    save_checkpoint(Checkpoint(run_id="off", task="x"), enabled=False)
    save_graph_projection({"run_id": "off2", "task": "x"}, enabled=False)
    assert load_checkpoint("off") is None
    assert load_checkpoint("off2") is None
    assert not checkpoint_path("off").exists()


@pytest.mark.audit
def test_save_overwrite_is_atomic_no_temp_files_linger(tmp_path, monkeypatch):
    """Repeated saves overwrite in place via os.replace and leave no .tmp residue behind."""
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path / "runs"))
    for step in range(5):
        save_checkpoint(Checkpoint(run_id="ow", task=f"t{step}", step=step, status="running"))
    loaded = load_checkpoint("ow")
    assert loaded.step == 4
    assert loaded.task == "t4"
    leftovers = list(checkpoint_path("ow").parent.glob("*.tmp"))
    assert leftovers == []


@pytest.mark.audit
def test_save_graph_projection_decodes_session_task_envelope(tmp_path, monkeypatch):
    """save_graph_projection -> load_checkpoint round-trips a TaskEnvelope embedded in session_state."""
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path / "runs"))
    task = TaskEnvelope(user_request="round", task_id="RT")
    state = {
        "run_id": "proj",
        "task": "round",
        "status": "running",
        "budget": {"steps": 3},
        "session_state": encode_session_state({"current_task": task, "code_changed": True}),
    }
    save_graph_projection(state)
    loaded = load_checkpoint("proj")
    assert loaded.step == 3
    assert loaded.state["code_changed"] is True
    assert isinstance(loaded.state["current_task"], TaskEnvelope)
    assert loaded.state["current_task"].task_id == "RT"


@pytest.mark.audit
@pytest.mark.concurrency
def test_concurrent_same_run_projection_writes_are_atomic_and_loadable(tmp_path, monkeypatch):
    """Many threads writing the same run's projection never tear the JSON; a coherent record loads."""
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path / "runs"))
    checkpoints = [
        Checkpoint(run_id="shared", task=f"task-{i}", step=i, status="running") for i in range(80)
    ]
    with ThreadPoolExecutor(max_workers=16) as pool:
        errors = [f.exception() for f in [pool.submit(save_checkpoint, c) for c in checkpoints]]
    assert errors == [None] * len(checkpoints)

    loaded = load_checkpoint("shared")
    assert loaded is not None
    # The winner is internally consistent: its step and task came from the same write.
    assert loaded.step in range(80)
    assert loaded.task == f"task-{loaded.step}"


# =========================================================================== #
# Property: budget + run_id survive the projection round-trip intact.          #
# =========================================================================== #
@pytest.mark.audit
@pytest.mark.property
@given(
    steps=st.integers(min_value=0, max_value=10_000),
    parse_errors=st.integers(min_value=0, max_value=1_000),
    status=st.sampled_from(["running", "completed", "failed", "incomplete"]),
)
def test_projection_round_trip_preserves_counters_and_status(tmp_path_factory, steps, parse_errors, status):
    """For arbitrary counters, save->load preserves budget.steps/parse_errors, status, and step."""
    runs = tmp_path_factory.mktemp("runs")
    import os

    prev = os.environ.get("AGENT_RUNS_DIR")
    os.environ["AGENT_RUNS_DIR"] = str(runs)
    try:
        run_id = "p-" + uuid.uuid4().hex
        cp = Checkpoint(
            run_id=run_id,
            task="t",
            budget={
                "max_steps": 30,
                "max_parse_errors": 3,
                "max_same_tool_calls": 3,
                "steps": steps,
                "parse_errors": parse_errors,
                "_tool_calls": {},
            },
            step=steps,
            status=status,
        )
        save_checkpoint(cp)
        loaded = load_checkpoint(run_id)
        assert loaded.budget["steps"] == steps
        assert loaded.budget["parse_errors"] == parse_errors
        assert loaded.status == status
        assert loaded.step == steps
        # Budget reconstructed from the loaded projection yields the same live counters.
        rebuilt = Budget(**{k: v for k, v in loaded.budget.items() if k != "_tool_calls"})
        assert rebuilt.steps == steps
        assert rebuilt.parse_errors == parse_errors
    finally:
        if prev is None:
            os.environ.pop("AGENT_RUNS_DIR", None)
        else:
            os.environ["AGENT_RUNS_DIR"] = prev
