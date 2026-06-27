"""Slice 2 — the real-LLM adapter behind the port.

These exercise ONLY the new adapter (parsing, repair, substitutability). The core
and the Slice 1 invariants are untouched; `test_invariants.py` still proves them.
Determinism comes from stub transports and RecordedLLM — no weights, no network.
"""
import pytest

from dragzero import Agent, EventType, FakeLLM, Orchestrator, Roster, reduce, render_tree
from dragzero.adapters.llm_local import (
    LLMFormatError,
    OpenAICompatLLM,
    RecordedLLM,
    build_messages,
    coerce_response,
    coerce_triage,
    extract_json,
)

_DELEGATE = '{"plan":{"steps":[{"id":"s1","description":"scope"}],"next":"delegate"},"decision":{"mode":"delegate","target":"researcher","subtask":"find sources"}}'
_SOLO = '{"plan":{"steps":[],"next":null},"decision":{"mode":"solo"}}'


def _role_stub(mapping):
    """Transport that answers based on the role embedded in the user message."""
    def transport(messages):
        user = messages[-1]["content"]
        for role, raw in mapping.items():
            if f"Your role: {role}." in user:
                return raw
        raise AssertionError(f"no stub for messages: {user!r}")
    return transport


# --- prompting -------------------------------------------------------------- #
def test_build_messages_carries_contract_roles_and_task():
    msgs = build_messages({"role": "planner", "task": "fix parse_config", "depth": 0}, roles=["researcher", "writer"])
    assert msgs[0]["role"] == "system" and "JSON" in msgs[0]["content"].upper()
    assert "fix parse_config" in msgs[1]["content"]
    assert "researcher" in msgs[1]["content"] and "Your role: planner." in msgs[1]["content"]


# --- extraction / coercion -------------------------------------------------- #
def test_extract_json_from_fences_and_prose():
    fenced = 'Sure!\n```json\n{"plan":{"steps":[],"next":null},"decision":{"mode":"solo"}}\n```\nDone.'
    assert extract_json(fenced)["decision"]["mode"] == "solo"
    prose = 'Thinking... {"decision":{"mode":"delegate","target":"researcher"},"plan":{"steps":["x"],"next":"go"}} ok'
    assert extract_json(prose)["decision"]["target"] == "researcher"


def test_coerce_normalizes_and_validates():
    out = coerce_response('{"decision":{"mode":"delegate","target":"researcher","subtask":"x"},"plan":{"steps":["a","b"],"next":"go"}}')
    assert out["decision"]["mode"] == "delegate"
    assert out["plan"]["steps"][0] == {"id": "s1", "description": "a", "status": "pending"}
    with pytest.raises(LLMFormatError):
        coerce_response("there is no json here")
    with pytest.raises(LLMFormatError):
        coerce_response('{"decision":{"mode":"delegate"}}')  # delegate without target


# --- the adapter drives the UNCHANGED core ---------------------------------- #
def test_openai_adapter_output_drives_core():
    llm = OpenAICompatLLM(roles=["researcher"], transport=_role_stub({"planner": _DELEGATE, "researcher": _SOLO}))
    orch = Orchestrator(Roster([Agent("a1", "planner", llm), Agent("a2", "researcher", llm)]))
    log = orch.run("fix parser")

    assert EventType.SUBTASK_SPAWNED in log.types()
    root, _ = reduce(log.events())
    assert root.children[0].description == "find sources"
    assert root.children[0].agent_id == "a2"


# --- repair + graceful fallback --------------------------------------------- #
def test_malformed_then_repair_succeeds():
    calls = {"n": 0}

    def transport(messages):
        calls["n"] += 1
        return "I cannot comply." if calls["n"] == 1 else _SOLO

    llm = OpenAICompatLLM(transport=transport)
    out = llm.complete({"role": "planner", "task": "t", "depth": 0})
    assert out["decision"]["mode"] == "solo"
    assert calls["n"] == 2 and llm.last_meta["repaired"] is True and llm.last_meta["fallback"] is False


def test_unrecoverable_output_falls_back_to_solo_without_crashing():
    llm = OpenAICompatLLM(transport=lambda messages: "no json, ever, sorry")
    out = llm.complete({"role": "planner", "task": "t", "depth": 0})
    assert out["decision"]["mode"] == "solo" and out["_meta"]["fallback"] is True

    orch = Orchestrator(Roster([Agent("a1", "planner", llm)]))
    log = orch.run("t")
    root, _ = reduce(log.events())
    assert root.status == "done"
    assert EventType.SUBTASK_SPAWNED not in log.types()


# --- deterministic full-loop replay ----------------------------------------- #
def test_recorded_llm_drives_full_loop_deterministically():
    planner = 'Here:\n```json\n{"plan":{"steps":[{"id":"s1","description":"scope the report"}],"next":"delegate research"},"decision":{"mode":"delegate","target":"researcher","subtask":"gather 3 sources"}}\n```'
    researcher = '{"plan":{"steps":[{"id":"s1","description":"search"}],"next":"summarise"},"decision":{"mode":"solo"}}'

    def build():
        llm = RecordedLLM([planner, researcher])
        orch = Orchestrator(Roster([Agent("a1", "planner", llm), Agent("a2", "researcher", llm)]))
        return orch.run("Write a short report")

    t1 = render_tree(reduce(build().events())[0])
    t2 = render_tree(reduce(build().events())[0])
    assert t1 == t2  # deterministic
    assert "gather 3 sources" in t1


# --- the port is substitutable (Liskov for adapters) ------------------------ #
def test_real_adapter_is_substitutable_with_fakellm():
    def shape(llm):
        orch = Orchestrator(Roster([Agent("a1", "planner", llm), Agent("a2", "researcher", llm)]))
        root, _ = reduce(orch.run("task").events())
        return render_tree(root)

    fake = FakeLLM(lambda ctx: coerce_response(_DELEGATE) if ctx["role"] == "planner" else coerce_response(_SOLO))
    recorded = RecordedLLM([_DELEGATE, _SOLO])
    assert shape(fake) == shape(recorded)  # same tree regardless of which adapter


# --- Slice D1: the triage branch (request:"triage") through the same parse path - #
def _triage_ctx(text):
    return {"agent_id": "w", "role": "worker", "input": text, "request": "triage"}


def test_recorded_triage_answer():
    llm = RecordedLLM(['{"kind":"answer","text":"Paris is the capital."}'])
    out = llm.complete(_triage_ctx("capital of France?"))
    assert out["triage"]["kind"] == "answer" and "Paris" in out["triage"]["text"]


def test_recorded_triage_task_parse():  # fenced JSON, done_when as typed triples → passed through
    reply = ('```json\n{"kind":"task","goal":"add tests","done_when":['
             '{"check":"file_exists","artifact":"test_x.py"},'
             '{"check":"grep_matches","artifact":"test_x.py","params":{"pattern":"def test_"}}]}\n```')
    out = RecordedLLM([reply]).complete(_triage_ctx("write tests for x"))
    assert out["triage"]["kind"] == "task" and out["triage"]["goal"] == "add tests"
    dw = out["triage"]["done_when"]
    assert dw[0] == {"check": "file_exists", "artifact": "test_x.py"}
    assert dw[1]["check"] == "grep_matches" and dw[1]["params"] == {"pattern": "def test_"}


def test_triage_parse_repair():  # broken→good recovers via repair; ever-broken falls back to answer, never raises
    calls = {"n": 0}

    def transport(messages):
        calls["n"] += 1
        return "Let me think about it." if calls["n"] == 1 else \
            '{"kind":"task","goal":"g","done_when":[{"check":"file_exists","artifact":"a.txt"}]}'

    llm = OpenAICompatLLM(transport=transport)
    out = llm.complete(_triage_ctx("do x"))
    assert out["triage"]["kind"] == "task" and calls["n"] == 2
    assert llm.last_meta["repaired"] is True and llm.last_meta["fallback"] is False

    llm2 = OpenAICompatLLM(transport=lambda m: "no json here, ever, sorry")
    out2 = llm2.complete(_triage_ctx("x"))
    assert out2["triage"]["kind"] == "answer" and llm2.last_meta["fallback"] is True


# coerce_triage is pure + total: it never raises, falling back to an answer ----- #
def test_coerce_triage_pure_fallback():
    assert coerce_triage("utter garbage")["triage"]["kind"] == "answer"
    assert coerce_triage('{"kind":"task","goal":"g"}')["triage"]["goal"] == "g"
