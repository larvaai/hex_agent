"""Empty-by-default gates + Budget counter math.

Pins registries.py: empty registries are pure pass-through, phase filtering and
first-wins semantics for hooks/rules, ToolRegistry CRUD, and Budget's
charge-when-it-fits-else-refuse counter (refusal must not increment ``used``).
"""
from dragzero import Budget, HookRegistry, RuleRegistry, ToolRegistry
from dragzero.agent import Task


# ---- HookRegistry -----------------------------------------------------------

def test_empty_hookregistry_passes_through():
    h = HookRegistry()
    assert h.check("pre_plan", {}) is None
    assert h.check("anything", {"k": "v"}) is None


def test_registered_hook_returns_its_reason():
    h = HookRegistry()
    h.register("pre_plan", lambda ctx: "blocked: nope")
    assert h.check("pre_plan", {}) == "blocked: nope"


def test_hook_phase_filter_does_not_fire_other_phase():
    h = HookRegistry()
    h.register("pre_plan", lambda ctx: "from pre_plan")
    # A hook registered on pre_plan must not fire for pre_delegate.
    assert h.check("pre_delegate", {}) is None
    # But it still fires for its own phase.
    assert h.check("pre_plan", {}) == "from pre_plan"


def test_first_blocking_hook_wins():
    h = HookRegistry()
    h.register("p", lambda ctx: None)        # passes
    h.register("p", lambda ctx: "first")     # first blocker
    h.register("p", lambda ctx: "second")    # never reached
    assert h.check("p", {}) == "first"


# ---- RuleRegistry -----------------------------------------------------------

def test_empty_ruleregistry_routes_none():
    r = RuleRegistry()
    task = Task(id="t1", description="do a thing")
    assert r.route(task) is None


def test_rule_returning_id_wins():
    r = RuleRegistry()
    r.add(lambda t: "worker-a")
    task = Task(id="t1", description="do a thing")
    assert r.route(task) == "worker-a"


def test_first_non_none_rule_wins():
    r = RuleRegistry()
    r.add(lambda t: None)         # abstains
    r.add(lambda t: "second")     # first to claim
    r.add(lambda t: "third")      # never reached
    task = Task(id="t1", description="x")
    assert r.route(task) == "second"


def test_rule_reads_task_via_fn_only():
    # A dummy with just the attribute the rule fn touches is enough.
    class Dummy:
        description = "urgent"

    r = RuleRegistry()
    r.add(lambda t: "fast" if "urgent" in t.description else None)
    assert r.route(Dummy()) == "fast"


# ---- ToolRegistry -----------------------------------------------------------

class _Tool:
    def __init__(self, name):
        self.name = name


def test_toolregistry_register_get_names_len():
    reg = ToolRegistry()
    assert len(reg) == 0
    assert reg.names() == []

    t = _Tool("grep")
    returned = reg.register(t)
    assert returned is t                  # register returns the tool
    assert reg.get("grep") is t
    assert reg.names() == ["grep"]
    assert len(reg) == 1


def test_toolregistry_get_unknown_is_none():
    reg = ToolRegistry()
    assert reg.get("nope") is None


# ---- Budget -----------------------------------------------------------------

def test_budget_none_is_disabled_and_always_charges():
    b = Budget(None)
    assert b.enabled is False
    assert b.charge() is True
    assert b.used == 1
    assert b.charge() is True
    assert b.used == 2


def test_budget_two_charges_then_refuses_without_increment():
    b = Budget(2)
    assert b.enabled is True
    assert b.charge() is True            # used 1
    assert b.used == 1
    assert b.charge() is True            # used 2
    assert b.used == 2
    assert b.charge() is False           # would exceed limit
    assert b.used == 2                   # refusal does NOT increment


def test_budget_one_boundary():
    b = Budget(1)
    assert b.charge() is True            # used 1
    assert b.used == 1
    assert b.charge() is False           # second refused
    assert b.used == 1


def test_budget_multi_charge_overflow_refused():
    b = Budget(3)
    assert b.charge() is True            # used 1
    assert b.charge() is True            # used 2
    assert b.used == 2
    # 2 + 2 > 3 -> refuse, used unchanged
    assert b.charge(n=2) is False
    assert b.used == 2
    # but a charge that fits still goes through
    assert b.charge(n=1) is True
    assert b.used == 3
