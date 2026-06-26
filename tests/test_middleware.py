"""Seam 2 — middleware chain around execute_tool (order, short-circuit, condense, budget, retry). Epic E06."""
from core.bootstrap import build_kernel
from discipline import Budget
from middleware import BudgetGuard, CondenseResult, PolicyGate, Retry

ECHO = {"features": {"example_echo": {"enabled": True, "module": "features.example_echo"}}}


def test_no_middleware_is_unchanged():
    k = build_kernel(ECHO)
    r = k.execute_tool("echo", {"a": 1})
    assert r["ok"] and r["data"]["echo"] == {"a": 1}


def test_policy_blocks_before_core():
    k = build_kernel(ECHO)
    blocked = []
    k.use(PolicyGate(deny={"echo"}, on_block=lambda req: blocked.append(req.name)))
    r = k.execute_tool("echo", {"a": 1})
    assert r["ok"] is False
    assert r["metadata"]["policy_block"] is True
    assert "task_id" in r["metadata"]  # kernel stamps trace ids even on short-circuit
    assert blocked == ["echo"]


def test_policy_emits_tool_failed():
    k = build_kernel(ECHO)
    k.use(PolicyGate(deny={"echo"}))
    seen = []
    k.events.subscribe(lambda t, p: seen.append(t))
    k.execute_tool("echo", {})
    assert "tool.failed" in seen


def test_ordering_outer_to_inner():
    k = build_kernel(ECHO)
    trace = []

    def mk(label):
        def mw(req, nxt):
            trace.append(label + ":in")
            r = nxt(req)
            trace.append(label + ":out")
            return r
        return mw

    k.use(mk("A"))
    k.use(mk("B"))
    k.execute_tool("echo", {})
    assert trace == ["A:in", "B:in", "B:out", "A:out"]


def test_condense_shrinks_tool_but_skips_llm():
    from features.llm_chat import FEATURE, LLMChatTool

    class _Fake:
        def __init__(self):
            class C:
                def create(self, **kw):
                    return type("R", (), {"choices": [type("Ch", (), {"message": type("M", (), {"content": "y" * 500})()})()]})()
            self.chat = type("X", (), {"completions": C()})()

    k = build_kernel(ECHO)
    k.use(CondenseResult(max_chars=50))
    r = k.execute_tool("echo", {"blob": "x" * 500})
    assert len(r["data"]["echo"]["blob"]) < 120          # tool result condensed

    k.registry.register_feature(FEATURE)
    k.registry.register_tools(FEATURE.capabilities, LLMChatTool(client=_Fake()), feature_name=FEATURE.name)
    rl = k.execute_tool("llm.chat", {"messages": []})
    assert len(rl["data"]["content"]) == 500             # llm.* NOT condensed


def test_budget_guard_blocks_repeated_tool():
    k = build_kernel(ECHO)
    k.use(BudgetGuard(Budget(max_same_tool_calls=2)))
    assert k.execute_tool("echo", {"x": 1})["ok"]
    assert k.execute_tool("echo", {"x": 1})["ok"]
    c = k.execute_tool("echo", {"x": 1})
    assert c["ok"] is False and c["metadata"]["budget_block"] is True


def test_retry_recovers_flaky_tool():
    k = build_kernel({"features": {}})

    class Flaky:
        name = "flaky"

        def __init__(self):
            self.n = 0

        def execute(self, req):
            self.n += 1
            return {"ok": self.n >= 2, "n": self.n}

    k.registry.register_tool("flaky", Flaky(), feature_name="t")
    k.use(Retry(attempts=3))
    r = k.execute_tool("flaky", {})
    assert r["ok"] is True and r["data"]["n"] == 2


# ── failure posture: fail-open advisory / fail-closed blocking (Phase 02) ────


def _advisory(fn):
    """Mark a middleware callable as fail-open (advisory: telemetry/condense)."""
    fn.fail_open = True
    return fn


def test_advisory_middleware_failure_is_fail_open():
    k = build_kernel(ECHO)
    skipped = []
    k.events.subscribe(lambda t, p: skipped.append(t) if t == "middleware.skipped" else None)

    @_advisory
    def boom(req, nxt):
        nxt(req)  # downstream runs
        raise RuntimeError("advisory exploded in post-processing")

    k.use(boom)
    r = k.execute_tool("echo", {"a": 1})
    assert r["ok"] is True                    # advisory failure did NOT block the call
    assert r["data"]["echo"] == {"a": 1}      # real tool result survives
    assert skipped == ["middleware.skipped"]  # swallow is observable, not silent


def test_blocking_middleware_failure_is_fail_closed():
    k = build_kernel(ECHO)

    def boom(req, nxt):  # no fail_open marker → blocking (default posture)
        raise RuntimeError("blocking exploded")

    k.use(boom)
    r = k.execute_tool("echo", {"a": 1})
    assert r["ok"] is False
    assert r["metadata"]["kernel_error"] is True


def test_chain_skips_only_the_failing_advisory():
    k = build_kernel(ECHO)
    trace = []

    @_advisory
    def adv(req, nxt):
        trace.append("adv")
        raise RuntimeError("nope")  # raises BEFORE calling nxt

    def passthru(req, nxt):
        trace.append("passthru")
        return nxt(req)

    k.use(adv)       # outer
    k.use(passthru)  # inner
    r = k.execute_tool("echo", {"a": 1})
    assert r["ok"] is True
    assert trace == ["adv", "passthru"]  # adv ran+skipped, passthru + core still ran


def test_advisory_failure_after_nxt_does_not_double_execute():
    # FM-HIGH: advisory calls nxt (executor runs) then raises in post-processing. The fallback
    # must NOT re-run the executor — latched nxt replays the first result.
    k = build_kernel({"features": {}})

    class Counter:
        name = "counter"

        def __init__(self):
            self.n = 0

        def execute(self, req):
            self.n += 1
            return {"ok": True, "n": self.n}

    counter = Counter()
    k.registry.register_tool("counter", counter, feature_name="t")

    @_advisory
    def post_raise(req, nxt):
        nxt(req)  # executor runs once here (n -> 1)
        raise RuntimeError("post-processing blew up")

    k.use(post_raise)
    r = k.execute_tool("counter", {})
    assert counter.n == 1          # executor ran EXACTLY once
    assert r["ok"] is True
    assert r["data"]["n"] == 1     # returns the one and only result
