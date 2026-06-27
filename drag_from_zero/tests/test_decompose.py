"""Gap 2 — decompose-until-trivial: worker PROPOSES, code ACCEPTS.

Two layers. The pure Gate-2 (accept_decomposition): a split is accepted only if every child is
STRICTLY smaller (μ=done_when_count), the parent's criteria are all covered by implication, and no
child smuggles a verdict-shaped key. Then end-to-end through the orchestrator: a dwc>1 task that
fails its K leaf attempts decomposes into done_when-gated children, each verified by code, and the
parent closes by compose. Leaf-ness is discovered by exhausting K — never asked of the model.
"""
from dragzero import Agent, FakeLLM, Orchestrator, Roster
from dragzero.accept import accept_decomposition
from dragzero.adapters.tools_fs import FsSandbox, build_fs_tools
from dragzero.capability import Capability
from dragzero.events import EventType
from dragzero.read_model import reduce
from dragzero.server import build_graph
from dragzero.verifier import build_done_when

FE = lambda art: {"check": "file_exists", "artifact": art}  # noqa: E731


# ── Gate-2 is a pure structural gate (run BEFORE any tree mutation) ────────────
def test_accept_smaller_covering_split():
    parent = build_done_when([FE("a.txt"), FE("b.txt")])
    children = [{"id": "la", "done_when": [FE("a.txt")]}, {"id": "lb", "done_when": [FE("b.txt")]}]
    assert accept_decomposition(parent, children, parent_id="t1").ok


def test_reject_singleton():
    parent = build_done_when([FE("a"), FE("b")])
    v = accept_decomposition(parent, [{"id": "x", "done_when": [FE("a")]}], parent_id="t1")
    assert not v.ok and "SINGLETON" in v.reason


def test_reject_not_smaller():  # a child no smaller than the parent breaks the termination proof
    parent = build_done_when([FE("a"), FE("b")])
    children = [{"id": "x", "done_when": [FE("a"), FE("c")]}, {"id": "y", "done_when": [FE("b")]}]
    v = accept_decomposition(parent, children, parent_id="t1")
    assert not v.ok and "NOT_SMALLER" in v.reason


def test_reject_child_forging_a_verdict():  # the worker can never grade itself
    parent = build_done_when([FE("a"), FE("b")])
    children = [{"id": "x", "done_when": [{"check": "file_exists", "artifact": "a", "passed": True}]},
                {"id": "y", "done_when": [FE("b")]}]
    v = accept_decomposition(parent, children, parent_id="t1")
    assert not v.ok and "verdict" in v.reason.lower()


def test_reject_undercover():  # a parent criterion no child implies = silent scope loss
    parent = build_done_when([{"check": "grep_matches", "artifact": "r.md", "params": {"pattern": "coverage"}}, FE("a")])
    children = [{"id": "x", "done_when": [FE("a")]}, {"id": "y", "done_when": [FE("b")]}]
    v = accept_decomposition(parent, children, parent_id="t1")
    assert not v.ok and "UNDERCOVER" in v.reason


# ── end-to-end: leaf attempts → decompose → compose ───────────────────────────
def _write(path, content="x"):
    return {"action": {"type": "tool", "tool": "write_file", "args": {"path": path, "content": content}}}


_SOLO = {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}}


def _two_part_responder(ctx):
    """Root keeps producing only a.txt (never b.txt) so it FAILS its dwc=2 gate; when asked to
    decompose it splits into two single-criterion leaves; each child produces its own file."""
    if ctx.get("request") == "decompose":  # the ask-path ctx has no observations
        return {"decompose": {"children": [
            {"id": "la", "goal": "produce a.txt only", "done_when": [FE("a.txt")]},
            {"id": "lb", "goal": "produce b.txt only", "done_when": [FE("b.txt")]},
        ]}}
    task, obs = ctx["task"], ctx["observations"]
    if "b.txt only" in task:
        return _write("b.txt") if not obs else _SOLO
    if "a.txt only" in task:
        return _write("a.txt") if not obs else _SOLO
    return _write("a.txt") if not obs else _SOLO  # root: incomplete on purpose


def _run(sandbox, done_when):
    orch = Orchestrator(Roster([Agent("w", "worker", FakeLLM(_two_part_responder))]),
                        tools=build_fs_tools(), sandbox=sandbox)
    root = orch.start("produce a.txt and b.txt", agent=orch.roster.by_role_or_id("worker"), done_when=done_when)
    orch.run_until_idle()
    return orch, root


def test_failed_leaf_decomposes_and_children_verify(tmp_path):
    sandbox = FsSandbox(str(tmp_path))
    orch, root = _run(sandbox, [FE("a.txt"), FE("b.txt")])
    types = orch.log.types()

    assert EventType.DECOMPOSITION_ACCEPTED in types
    spawned = [e for e in orch.log.of_type(EventType.SUBTASK_SPAWNED) if e.payload.get("done_when")]
    assert len(spawned) == 2  # two single-criterion leaves, each carrying its done_when
    passes = [e for e in orch.log.of_type(EventType.LEAF_VERIFIED) if e.payload["verdict"] == "PASS"]
    assert {e.task_id for e in passes} == {"la", "lb"}        # both children verified by CODE
    assert (tmp_path / "a.txt").exists() and (tmp_path / "b.txt").exists()

    # the parent closed by compose; the projection re-derives PASS over the sandbox
    g = build_graph(orch.log, sandbox, spec={}, activated_at=None)
    rootn = next(n for n in g["nodes"] if n["id"] == root)
    assert rootn["verdict"] == "PASS" and len(rootn["children"]) == 2
    assert rootn["mu"] > next(n for n in g["nodes"] if n["id"] == "la")["mu"]  # μ shrank at the split


def test_atomic_leaf_that_never_passes_is_unsolvable(tmp_path):
    # dwc==1 and the worker never writes the artifact → K_LEAF attempts then UNSOLVABLE_LEAF
    def never(ctx):
        return _SOLO
    orch = Orchestrator(Roster([Agent("w", "worker", FakeLLM(never))]), tools=build_fs_tools(), sandbox=FsSandbox(str(tmp_path)))
    orch.start("do it", agent=orch.roster.by_role_or_id("worker"), done_when=[FE("missing.txt")])
    orch.run_until_idle()
    fails = orch.log.of_type(EventType.TASK_FAILED)
    assert any(e.payload.get("error") == "UNSOLVABLE_LEAF" for e in fails)
    assert len([e for e in orch.log.of_type(EventType.LEAF_VERIFIED) if e.payload["verdict"] == "FAIL"]) == 5  # K_LEAF


def test_rejected_decomposition_blocks_not_degrades(tmp_path):
    # the worker proposes a NON-shrinking split (child as big as parent) → Gate-2 rejects → BLOCKED,
    # never a silent unverified pass.
    def bad_split(ctx):
        if ctx.get("request") == "decompose":
            return {"decompose": {"children": [
                {"id": "x", "done_when": [FE("a.txt"), FE("b.txt")]},  # dwc 2 == parent → NOT_SMALLER
                {"id": "y", "done_when": [FE("b.txt")]},
            ]}}
        return _SOLO  # never satisfies the dwc=2 gate
    orch = Orchestrator(Roster([Agent("w", "worker", FakeLLM(bad_split))]), tools=build_fs_tools(), sandbox=FsSandbox(str(tmp_path)))
    orch.start("two", agent=orch.roster.by_role_or_id("worker"), done_when=[FE("a.txt"), FE("b.txt")])
    orch.run_until_idle()
    assert orch.log.of_type(EventType.DECOMPOSITION_REJECTED)
    assert any(e.payload.get("error") == "DECOMPOSE_REJECTED" for e in orch.log.of_type(EventType.TASK_FAILED))
    assert not orch.log.of_type(EventType.DECOMPOSITION_ACCEPTED)


def test_compose_fail_when_a_child_fails_is_not_a_silent_done(tmp_path):
    # The adversary's critical finding: a decomposed parent whose child FAILS used to roll up to
    # DONE in the orchestrator + ledger (only the projection caught it). The fence must make the
    # run's OWN truth (reduce over the event log = disk) report failure.
    def r(ctx):
        if ctx.get("request") == "decompose":
            return {"decompose": {"children": [
                {"id": "la", "goal": "produce a.txt only", "done_when": [FE("a.txt")]},
                {"id": "lb", "goal": "produce b.txt only", "done_when": [FE("b.txt")]},
            ]}}
        task, obs = ctx["task"], ctx["observations"]
        if "a.txt only" in task:
            return _write("a.txt") if not obs else _SOLO
        return _SOLO  # lb and the root never write b.txt → lb is UNSOLVABLE_LEAF
    sandbox = FsSandbox(str(tmp_path))
    orch = Orchestrator(Roster([Agent("w", "worker", FakeLLM(r))]), tools=build_fs_tools(), sandbox=sandbox)
    root = orch.start("two", agent=orch.roster.by_role_or_id("worker"), done_when=[FE("a.txt"), FE("b.txt")])
    orch.run_until_idle()

    _, nodes = reduce(orch.log.events())  # this fold IS the disk truth
    assert nodes[root].status == "failed"  # NOT "done" — the orchestrator no longer lies
    assert any(e.payload.get("error") == "COMPOSE_FAIL" for e in orch.log.of_type(EventType.TASK_FAILED))


def test_decompose_path_obeys_the_capability_depth_budget(tmp_path):
    # The adversary's medium finding: the decompose spawn path ignored the capability budget. A
    # tight depth must hard-stop the decompose chain, surfaced as CAPABILITY_EXHAUSTED.
    def r(ctx):
        if ctx.get("request") == "decompose":
            dw = ctx.get("done_when") or []
            return {"decompose": {"children": [
                {"id": f"leaf-{len(dw)}", "goal": "leaf", "done_when": [dw[0]]},
                {"id": f"tail-{len(dw)}", "goal": "tail", "done_when": dw[1:]},
            ]}}
        return _SOLO  # never satisfies → always wants to decompose deeper
    cap = Capability(tools=frozenset(), can_delegate=True, depth=1, spawn_quota=8)  # one level of split
    orch = Orchestrator(Roster([Agent("w", "worker", FakeLLM(r))]), tools=build_fs_tools(),
                        sandbox=FsSandbox(str(tmp_path)), capability=cap)
    orch.start("root", agent=orch.roster.by_role_or_id("worker"), done_when=[FE(f"f{i}.txt") for i in range(4)])
    orch.run_until_idle()
    assert orch.log.of_type(EventType.CAPABILITY_EXHAUSTED)  # depth budget fired ON the decompose path
    assert min(rc.capability.depth for rc in orch._recs.values()) >= -1  # children stayed a subset, didn't run away


def test_delegation_only_runs_are_unchanged(tmp_path):
    # a task with NO done_when never enters the gated path — byte-identical to before
    def deleg(ctx):
        if ctx["role"] == "planner":
            return {"plan": {"steps": [], "next": None}, "decision": {"mode": "delegate", "target": "coder", "subtask": "x"}}
        return _SOLO
    orch = Orchestrator(Roster([Agent("planner", "planner", FakeLLM(deleg)), Agent("coder", "coder", FakeLLM(deleg))]))
    orch.run("go", agent=orch.roster.by_role_or_id("planner"))
    assert not orch.log.of_type(EventType.LEAF_VERIFIED)  # gated path never engaged
    assert orch.log.of_type(EventType.SUBTASK_SPAWNED)     # delegation still works
