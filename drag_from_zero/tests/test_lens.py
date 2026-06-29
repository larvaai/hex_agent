"""Multi-lens advisory — lens core, consult tool, hệ-mandate, config/determinism.

The slice's contract, proven test-by-test (additive: every old suite stays byte-identical):
  Luật 1 — a lens ADVISES, code/agent DECIDES: a lens line carries NO verdict key.
  Luật 2 — permission is STRUCTURAL: run_lenses holds no ToolRegistry, so a lens can't
           dispatch a tool/consult; the capability gate is an opt-in PHỤ layer.
  Luật 3 — additive: no lens/hệ configured ⇒ stream byte-identical to before.

Phase 1 covers the lens-runner on FakeLLM: registry resolve, all-lines-returned (raw +
cascade), no-forge output, acyclic-at-build.
"""
import pytest

from dragzero import Agent, EventLog, EventType, FakeLLM, Orchestrator, Roster
from dragzero.capability import Capability
from dragzero.lens import ComboSpec, ComboStage, Lens, LensComboError, LensRegistry, load_lenses, run_lenses

FORBIDDEN = {"verdict", "route", "mode", "passed", "status", "score"}


def _consult(**args):
    return {"action": {"type": "tool", "tool": "consult_lenses", "args": args}}


def _solo():
    return {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}}


def _lens_llm(lines_by_id):
    """FakeLLM whose lens responder returns a scripted line per lens_id. It branches on
    request=='lens' BEFORE touching any other key — a lens ctx has no 'observations' (F4)."""
    def responder(ctx):
        assert ctx.get("request") == "lens"
        return {"lens": lines_by_id[ctx["lens_id"]]}
    return FakeLLM(responder)


def _reg(*lenses):
    reg = LensRegistry()
    for lz in lenses:
        reg.register_lens(lz)
    return reg


# ── Phase 1 — lens core ───────────────────────────────────────────────────────
def test_registry_resolve():
    reg = _reg(Lens("risk", "what breaks?"), Lens("evidence", "what proves it?"))
    reg.register_combo(ComboSpec("inspect_v1", (ComboStage("risk"), ComboStage("evidence"))))
    assert reg.get_combo("inspect_v1").stages[0].lens == "risk"
    assert reg.get_lens("risk").prompt == "what breaks?"
    assert reg.get_lens("nope") is None
    assert reg.get_combo("nope") is None


def test_run_lenses_independent():
    reg = _reg(Lens("risk", "?"), Lens("evidence", "?"))
    stages = (ComboStage("risk"), ComboStage("evidence"))
    log = EventLog()
    lines = run_lenses(reg, stages, {"task": "t"}, _lens_llm({"risk": "R", "evidence": "E"}),
                       log, agent_id="w", source="combo")
    assert lines == ["R", "E"]
    assert len(log.of_type(EventType.LENS_QUERIED)) == 2
    assert len(log.of_type(EventType.LENS_RETURNED)) == 2
    assert log.of_type(EventType.LENS_QUERIED)[0].payload["source"] == "combo"


def test_run_lenses_cascade():
    reg = _reg(Lens("a", "?"), Lens("b", "?"), Lens("c", "?"))
    stages = (ComboStage("a"), ComboStage("b"), ComboStage("c", reads=("a", "b")))
    seen_upstream: dict = {}

    def responder(ctx):
        assert ctx.get("request") == "lens"
        if ctx["lens_id"] == "c":
            seen_upstream.update(ctx["upstream"])
        return {"lens": ctx["lens_id"].upper()}

    log = EventLog()
    lines = run_lenses(reg, stages, {"task": "t"}, FakeLLM(responder), log, agent_id="w", source="combo")
    assert lines == ["A", "B", "C"]                 # ALL lines: raw A,B AND synth C
    assert seen_upstream == {"a": "A", "b": "B"}    # C's ctx carried upstream lines
    order = [e.payload["lens_id"] for e in log.of_type(EventType.LENS_RETURNED)]
    assert order == ["a", "b", "c"]                 # C ran AFTER its reads


def test_lens_output_no_verdict():  # Luật 1 — no-forge
    reg = _reg(Lens("risk", "?"))
    log = EventLog()
    run_lenses(reg, (ComboStage("risk"),), {"task": "t"}, _lens_llm({"risk": "x"}),
               log, agent_id="w", source="adhoc")
    ret = log.of_type(EventType.LENS_RETURNED)[0]
    assert set(ret.payload) == {"lens_id", "line"}
    assert not (set(ret.payload) & FORBIDDEN)


def test_cascade_acyclic():  # self / forward / unknown ref → LensComboError at register (build)
    reg = _reg(Lens("a", "?"), Lens("c", "?"))
    with pytest.raises(LensComboError):
        reg.register_combo(ComboSpec("self", (ComboStage("c", reads=("c",)),)))
    with pytest.raises(LensComboError):
        reg.register_combo(ComboSpec("fwd", (ComboStage("a", reads=("c",)), ComboStage("c"))))


# ── Phase 2 — consult_lenses dispatch + capability permission ──────────────────
def _agent_lens_llm(lens_lines, agent_steps):
    """One FakeLLM driving BOTH agent.step and run_lenses. It branches on request=='lens'
    FIRST (a lens ctx has no 'observations'); the agent path pops scripted steps in order."""
    steps = list(agent_steps)

    def responder(ctx):
        if ctx.get("request") == "lens":
            return {"lens": lens_lines[ctx["lens_id"]]}
        return steps.pop(0)

    return FakeLLM(responder)


def test_agent_consult_observation():  # agent calls consult mid-loop → lens lines become an observation
    reg = _reg(Lens("risk", "?"), Lens("evidence", "?"))
    llm = _agent_lens_llm({"risk": "risk-says", "evidence": "evidence-says"},
                          [_consult(lenses=["risk", "evidence"]), _solo()])
    log = Orchestrator(Roster([Agent("a", "worker", llm)]), lenses=reg).run("inspect")

    called = [e.payload["tool"] for e in log.of_type(EventType.TOOL_CALLED)]
    assert called == ["consult_lenses"]
    tr = [e for e in log.of_type(EventType.TOOL_RESULT) if e.payload["tool"] == "consult_lenses"][0]
    assert tr.payload["ok"] is True
    assert "risk-says" in tr.payload["output"] and "evidence-says" in tr.payload["output"]
    assert len(log.of_type(EventType.LENS_QUERIED)) == 2
    assert len(log.of_type(EventType.LENS_RETURNED)) == 2
    assert all(e.payload["source"] == "adhoc" for e in log.of_type(EventType.LENS_QUERIED))
    # exactly one terminal decision — the agent's SOLO; no lens forged one
    assert len(log.of_type(EventType.DELEGATION_DECIDED)) == 1


def test_consult_gated_when_capability_set():  # Luật 2 — opt-in capability layer denies consult
    reg = _reg(Lens("risk", "?"))
    llm = _agent_lens_llm({"risk": "x"}, [_consult(lenses=["risk"]), _solo()])
    log = Orchestrator(Roster([Agent("a", "worker", llm)]),
                       lenses=reg, capability=Capability(tools=frozenset())).run("t")
    assert EventType.TOOL_DENIED in log.types()
    assert EventType.LENS_QUERIED not in log.types()  # denied before _run_tool → no lens ran


def test_lens_cannot_dispatch_tool():  # Luật 2 structural (F5) — a tool-shaped lens reply never dispatches
    reg = _reg(Lens("risk", "?"))

    def responder(ctx):
        if ctx.get("request") == "lens":
            return {"action": {"type": "tool", "tool": "read_file", "args": {}}}  # tool-shaped
        return _consult(lenses=["risk"]) if not ctx["observations"] else _solo()

    log = Orchestrator(Roster([Agent("a", "worker", FakeLLM(responder))]), lenses=reg).run("t")
    called = [e.payload["tool"] for e in log.of_type(EventType.TOOL_CALLED)]
    assert called == ["consult_lenses"]   # the lens's tool-shaped reply never reached dispatch
    assert "read_file" not in called
    assert len(log.of_type(EventType.LENS_RETURNED)) == 1


def test_consult_empty_by_default():  # Luật 3 — lenses=None ⇒ not configured, no LENS event, tools untouched
    def responder(ctx):
        return _consult(lenses=["risk"]) if not ctx["observations"] else _solo()

    orch = Orchestrator(Roster([Agent("a", "worker", FakeLLM(responder))]))  # lenses=None
    log = orch.run("t")
    tr = [e for e in log.of_type(EventType.TOOL_RESULT) if e.payload["tool"] == "consult_lenses"][0]
    assert tr.payload["ok"] is False and "not configured" in tr.payload["error"]
    assert EventType.LENS_QUERIED not in log.types()
    assert orch.tools.names() == []


# ── Phase 3 — hệ mandate + Agent.he + wiring ──────────────────────────────────
def _he_reg(*lenses, combo_stages, he="thanh_tra", combo="inspect_v1", enabled=True):
    reg = _reg(*lenses)
    reg.register_combo(ComboSpec(combo, combo_stages))
    reg.register_he(he, combo, enabled=enabled)
    return reg


def test_he_mandate_autoruns():  # agent in hệ X → CODE forces the combo; agent never emits consult
    reg = _he_reg(Lens("risk", "?"), Lens("evidence", "?"),
                  combo_stages=(ComboStage("risk"), ComboStage("evidence")))
    llm = _agent_lens_llm({"risk": "risk!", "evidence": "evidence!"}, [_solo()])
    agent = Agent("w", "worker", llm, he="thanh_tra")
    log = Orchestrator(Roster([agent]), lenses=reg).run("audit")

    q = log.of_type(EventType.LENS_QUERIED)
    assert len(q) == 2 and all(e.payload["source"] == "combo" for e in q)
    assert EventType.TOOL_CALLED not in log.types()      # agent did NOT consult; code mandated it
    # the lines were seeded into the agent's step-0 observations (combo runs BEFORE the first step)
    step_ctx = next(c for c in llm.calls if c.get("request") != "lens")
    outs = " ".join(str(o.get("output")) for o in step_ctx["observations"])
    assert "risk!" in outs and "evidence!" in outs


def test_he_disabled_no_run():  # enabled=False ⇒ configured-but-off; runs as if no hệ
    reg = _he_reg(Lens("risk", "?"), combo_stages=(ComboStage("risk"),), enabled=False)
    llm = _agent_lens_llm({"risk": "x"}, [_solo()])
    log = Orchestrator(Roster([Agent("w", "worker", llm, he="thanh_tra")]), lenses=reg).run("audit")
    assert EventType.LENS_QUERIED not in log.types()


def test_he_plus_adhoc():  # mandate combo AND an agent-initiated consult both fire
    reg = _he_reg(Lens("risk", "?"), Lens("evidence", "?"), combo_stages=(ComboStage("risk"),))
    llm = _agent_lens_llm({"risk": "r", "evidence": "e"}, [_consult(lenses=["evidence"]), _solo()])
    log = Orchestrator(Roster([Agent("w", "worker", llm, he="thanh_tra")]), lenses=reg).run("audit")
    sources = [e.payload["source"] for e in log.of_type(EventType.LENS_QUERIED)]
    assert sources == ["combo", "adhoc"]   # mandate seeds first, then the ad-hoc consult


def test_no_he_byte_identical():  # Luật 3 — registry present but agent has no hệ ⇒ stream unchanged
    reg = _he_reg(Lens("risk", "?"), combo_stages=(ComboStage("risk"),))
    r = lambda ctx: _solo()
    base = Orchestrator(Roster([Agent("w", "worker", FakeLLM(r))]), lenses=reg).run("t")   # he=None
    plain = Orchestrator(Roster([Agent("w", "worker", FakeLLM(r))])).run("t")              # no lenses
    assert EventType.LENS_QUERIED not in base.types()
    assert base.types() == plain.types()


def test_wiring_passes_he():
    from dragzero import Topology, build_runtime
    reg = _he_reg(Lens("risk", "?"), combo_stages=(ComboStage("risk"),))
    topo = Topology.from_dict({"version": 1, "nodes": [
        {"id": "a", "type": "agent", "role": "worker", "he": "thanh_tra", "entry": True}]})
    rt = build_runtime(topo, FakeLLM(lambda ctx: _solo()), lenses=reg)
    assert rt.orchestrator.roster.get("a").he == "thanh_tra"
    assert rt.orchestrator.lenses is reg


# ── Phase 4 — config loader + determinism ─────────────────────────────────────
_SAMPLE = {
    "catalog": {"risk": {"prompt": "what breaks?"}, "evidence": {"prompt": "what proves it?"},
                "synth": {"prompt": "combine the notes"}},
    "combos": {"inspect_v1": {"stages": [
        {"lens": "risk"}, {"lens": "evidence"}, {"lens": "synth", "reads": ["risk", "evidence"]}]}},
    "he": {"thanh_tra": {"combo": "inspect_v1", "enabled": True}},
}


def test_load_lenses_ok():
    reg = load_lenses(_SAMPLE)
    assert reg.get_lens("risk").prompt == "what breaks?"
    combo, enabled = reg.combo_for_he("thanh_tra")
    assert combo.id == "inspect_v1" and enabled is True
    assert combo.stages[2].reads == ("risk", "evidence")


def test_load_lenses_invalid():
    with pytest.raises(LensComboError):  # hệ → unknown combo
        load_lenses({"catalog": {"a": {"prompt": "p"}}, "he": {"x": {"combo": "nope"}}})
    with pytest.raises(LensComboError):  # combo references a lens missing from the catalog
        load_lenses({"catalog": {"a": {"prompt": "p"}}, "combos": {"c": {"stages": [{"lens": "ghost"}]}}})
    with pytest.raises(LensComboError):  # cascade cycle (forward ref)
        load_lenses({"catalog": {"a": {"prompt": "p"}, "b": {"prompt": "p"}},
                     "combos": {"c": {"stages": [{"lens": "a", "reads": ["b"]}, {"lens": "b"}]}}})


def test_recorded_lens_by_id():  # key-by-lens-id ⇒ deterministic replay, order-independent
    from dragzero.adapters.llm_local import RecordedLLM
    reg = _reg(Lens("risk", "?"), Lens("evidence", "?"))
    stages = (ComboStage("risk"), ComboStage("evidence"))

    def build():
        llm = RecordedLLM(by_lens={"risk": "R", "evidence": "E"})
        return run_lenses(reg, stages, {"task": "t"}, llm, EventLog(), agent_id="w", source="combo")

    assert build() == ["R", "E"]
    assert build() == ["R", "E"]   # same lines on replay — keyed by id, not call order
