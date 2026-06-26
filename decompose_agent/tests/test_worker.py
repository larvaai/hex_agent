"""Worker boundary: 4-cell context (no graph leak), ScriptedWorker spine, LocalLLMWorker
text-mode (F6), and F7 — the action runner forces writes into the ACTIVE node's dir only."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from decompose_agent import worker as W
from decompose_agent.gates import UnsafeArtifactPath
from decompose_agent.json_repair import JsonGateError
from decompose_agent.tree import load_tree
from decompose_agent.workspace import node_dir, write_artifact


def _tree(tmp_path):
    p = tmp_path / "t.yaml"
    p.write_text(
        "- {id: P, parent: null, kind: work, status: decomposed, done_when: [{check: all_children_done}]}\n"
        "- {id: P.a, parent: P, kind: work, status: pending, depends_on: [],\n"
        "   done_when: [{check: file_exists, artifact: a.txt}, {check: row_count_gte, params: {n: 2}, artifact: a.txt}]}\n"
        "- {id: P.b, parent: P, kind: work, status: pending, depends_on: [P.a],\n"
        "   done_when: [{check: file_exists, artifact: b.txt}]}\n"
    )
    return load_tree(p)


# ── assemble_4cell: exactly 4 cells, breadcrumb root→node, NO graph leak ───────

def test_assemble_4cell_shape_and_no_graph_leak(tmp_path):
    tree = _tree(tmp_path)
    ctx = W.assemble_4cell(tree.nodes["P.a"], tree)
    cells = ctx.cells()
    assert len(cells) == 4 and all(isinstance(c, str) and c for c in cells)
    assert ctx.node_id == "P.a"
    assert "P" in ctx.breadcrumb and "P.a" in ctx.breadcrumb  # root→node path
    assert "file_exists" in ctx.node and "a.txt" in ctx.node and "row_count_gte" in ctx.node
    # the sibling P.b must NOT appear anywhere — the worker never sees the graph
    assert "P.b" not in ctx.render()


def test_assemble_4cell_journal_tail_is_this_node_only(tmp_path):
    from decompose_agent.journal import Journal
    tree = _tree(tmp_path)
    j = Journal(tmp_path, "P")
    j.append("P.a", {"event": "attempt", "verdict": "FAIL", "marker": "MINE"})
    j.append("P.b", {"event": "attempt", "verdict": "FAIL", "marker": "OTHER"})
    ctx = W.assemble_4cell(tree.nodes["P.a"], tree, journal=j)
    assert "MINE" in ctx.journal_tail
    assert "OTHER" not in ctx.journal_tail


# ── ScriptedWorker spine + repair ladder on propose ───────────────────────────

def test_scripted_worker_returns_scripted_action(tmp_path):
    tree = _tree(tmp_path)
    act = W.write_action({"a.txt": "x"})
    sw = W.ScriptedWorker({"P.a": [act]})
    ctx = W.assemble_4cell(tree.nodes["P.a"], tree)
    assert sw.propose(ctx) == act


def test_scripted_worker_parses_raw_via_repair_ladder(tmp_path):
    tree = _tree(tmp_path)
    sw = W.ScriptedWorker({"P.a": ['```json\n{"action":"tool","tool":"write_artifacts","args":{"files":{}}}\n```']})
    ctx = W.assemble_4cell(tree.nodes["P.a"], tree)
    assert sw.propose(ctx)["tool"] == "write_artifacts"


def test_scripted_worker_raw_garbage_raises_gate_error(tmp_path):
    tree = _tree(tmp_path)
    sw = W.ScriptedWorker({"P.a": ["{not json at all"]})
    ctx = W.assemble_4cell(tree.nodes["P.a"], tree)
    with pytest.raises(JsonGateError):
        sw.propose(ctx)


def test_scripted_worker_decompose_not_implemented_this_phase(tmp_path):
    tree = _tree(tmp_path)
    with pytest.raises(NotImplementedError):
        W.ScriptedWorker({}).decompose(tree.nodes["P.a"], failure_evidence=[])


# ── LocalLLMWorker: text-mode, NO response_format (F6 / DEC-D3) ────────────────

class _FakeClient:
    """Records the create() kwargs; returns a canned canonical action — no network."""

    def __init__(self, content):
        self.captured = None
        inner = self

        class _Completions:
            def create(self, **kwargs):
                inner.captured = kwargs
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

        self.chat = SimpleNamespace(completions=_Completions())


def test_local_llm_worker_uses_text_mode_no_response_format(tmp_path):
    tree = _tree(tmp_path)
    fake = _FakeClient('{"action":"tool","tool":"write_artifacts","args":{"files":{"a.txt":"x"}}}')
    w = W.LocalLLMWorker(client=fake, model="local-model")
    action = w.propose(W.assemble_4cell(tree.nodes["P.a"], tree))
    assert "response_format" not in fake.captured  # F6: LM Studio rejects json_object
    assert action == {"action": "tool", "tool": "write_artifacts", "args": {"files": {"a.txt": "x"}}}


def test_local_llm_worker_repairs_dirty_output(tmp_path):
    tree = _tree(tmp_path)
    fake = _FakeClient('Sure:\n```json\n{"action":"fs_write","path":"a.txt","content":"x"}\n```')
    w = W.LocalLLMWorker(client=fake)
    action = w.propose(W.assemble_4cell(tree.nodes["P.a"], tree))
    assert action["action"] == "tool" and action["tool"] == "fs_write"
    assert action["args"] == {"path": "a.txt", "content": "x"}


# ── F7: writes are forced into the ACTIVE node's dir; escapes rejected ─────────

def test_write_artifact_jailed_to_active_node_dir(tmp_path):
    tree = _tree(tmp_path)
    a = tree.nodes["P.a"]
    p = write_artifact(tmp_path, "P", a, "a.txt", "hello")
    assert p == (node_dir(tmp_path, "P", "P.a") / "a.txt").resolve()
    assert p.read_text() == "hello"


def test_write_artifact_rejects_escape_into_sibling_dir(tmp_path):
    tree = _tree(tmp_path)
    a = tree.nodes["P.a"]
    # worker tries to pre-satisfy P.b's gate by writing into P.b's dir → rejected, nothing written
    with pytest.raises(UnsafeArtifactPath):
        write_artifact(tmp_path, "P", a, "../P.b/b.txt", "forged")
    assert not (node_dir(tmp_path, "P", "P.b") / "b.txt").exists()


# ── LocalLLMWorker resilience: timeout + retry/backoff + actionable error (#2) ──

class _ApiConnectionError(Exception):
    """name contains 'connection' → treated as an unreachable-endpoint error."""


class _Transient(Exception):
    def __init__(self, msg="busy", status=503):
        super().__init__(msg)
        self.status_code = status


class _FlakyClient:
    def __init__(self, content="{}", fail=0, exc=None):
        self.calls = 0
        self.last_kwargs = None
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.calls += 1
                outer.last_kwargs = kwargs
                if outer.calls <= fail:
                    raise exc or _Transient()
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

        self.chat = SimpleNamespace(completions=_Completions())


def test_local_llm_passes_a_timeout_to_create(tmp_path):
    tree = _tree(tmp_path)
    fake = _FlakyClient('{"action":"tool","tool":"x","args":{}}')
    W.LocalLLMWorker(client=fake, timeout=12.5).propose(W.assemble_4cell(tree.nodes["P.a"], tree))
    assert fake.last_kwargs["timeout"] == 12.5  # a hung socket can no longer block forever


def test_local_llm_retries_transient_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "_sleep", lambda *_: None)
    tree = _tree(tmp_path)
    fake = _FlakyClient('{"action":"tool","tool":"write_artifacts","args":{"files":{}}}', fail=2)
    action = W.LocalLLMWorker(client=fake, retries=2).propose(W.assemble_4cell(tree.nodes["P.a"], tree))
    assert action["tool"] == "write_artifacts"
    assert fake.calls == 3  # 2 transient failures + 1 success


def test_local_llm_unreachable_raises_actionable_worker_error(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "_sleep", lambda *_: None)
    tree = _tree(tmp_path)
    fake = _FlakyClient(fail=99, exc=_ApiConnectionError("refused"))
    w = W.LocalLLMWorker(client=fake, base_url="http://localhost:9999/v1", retries=1)
    with pytest.raises(W.WorkerError) as e:
        w.propose(W.assemble_4cell(tree.nodes["P.a"], tree))
    msg = str(e.value).lower()
    assert "localhost:9999" in msg and "running" in msg
    assert fake.calls == 2  # 1 try + 1 retry, then give up (no infinite hang)
