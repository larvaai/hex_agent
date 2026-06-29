"""
Lesson 23 - Visitor Pattern
Neuroscience analogy: Microglia scan - cung scanner, hanh vi khac per neuron type (double dispatch)

Cau truc file:
  1. Element hierarchy + Visitor interface
  2. Demo 1 - Microglia scan: 4 element type x 3 visitor (Surveillance / Homeostasis / Inflammatory)
  3. Demo 2 - 4 anti-patterns (isinstance, mutate, cyclic dep, forgotten visit)
  4. Demo 3 - Visitor over AST: PrettyPrint + Eval + Optimize + ToSQL (revisit Lesson 15)
  5. Demo 4 - match-case alternative (Pythonic)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Optional


# =============================================================================
# 1. NEURAL TISSUE - Element hierarchy
# =============================================================================
class NeuralElement(ABC):
    @abstractmethod
    def accept(self, v: "MicroglialVisitor") -> None: ...


@dataclass
class HealthyNeuron(NeuralElement):
    id: int

    def accept(self, v: "MicroglialVisitor") -> None:
        v.visit_healthy(self)


@dataclass
class StressedNeuron(NeuralElement):
    id: int
    stress_level: float = 0.7

    def accept(self, v: "MicroglialVisitor") -> None:
        v.visit_stressed(self)


@dataclass
class ApoptoticNeuron(NeuralElement):
    id: int

    def accept(self, v: "MicroglialVisitor") -> None:
        v.visit_apoptotic(self)


@dataclass
class DamagedSynapse(NeuralElement):
    id: int
    activity: float = 0.1   # low activity = candidate for pruning

    def accept(self, v: "MicroglialVisitor") -> None:
        v.visit_damaged_synapse(self)


# =============================================================================
# 2. MicroglialVisitor + 3 ConcreteVisitors
# =============================================================================
class MicroglialVisitor(ABC):
    @abstractmethod
    def visit_healthy(self, n: HealthyNeuron) -> None: ...
    @abstractmethod
    def visit_stressed(self, n: StressedNeuron) -> None: ...
    @abstractmethod
    def visit_apoptotic(self, n: ApoptoticNeuron) -> None: ...
    @abstractmethod
    def visit_damaged_synapse(self, s: DamagedSynapse) -> None: ...


class SurveillanceVisitor(MicroglialVisitor):
    """Just monitor. Log contacts, no action."""
    def __init__(self):
        self.log: List[str] = []
    def visit_healthy(self, n):
        self.log.append(f"contact[{n.id}] healthy: brief, retract")
    def visit_stressed(self, n):
        self.log.append(f"contact[{n.id}] stressed: lasting, monitor (sl={n.stress_level:.1f})")
    def visit_apoptotic(self, n):
        self.log.append(f"contact[{n.id}] apoptotic: flag for clearance")
    def visit_damaged_synapse(self, s):
        self.log.append(f"contact[{s.id}] synapse: flag for pruning (act={s.activity:.2f})")


class HomeostasisVisitor(MicroglialVisitor):
    """Healthy mode: trophic + phagocytose + pruning."""
    def __init__(self):
        self.bdnf_released = 0
        self.phagocytosed = 0
        self.pruned = 0
    def visit_healthy(self, n):
        pass  # no action needed
    def visit_stressed(self, n):
        self.bdnf_released += 1
        print(f"    [Homeostasis] release BDNF rescue stressed neuron #{n.id}")
    def visit_apoptotic(self, n):
        self.phagocytosed += 1
        print(f"    [Homeostasis] phagocytose apoptotic neuron #{n.id}")
    def visit_damaged_synapse(self, s):
        self.pruned += 1
        print(f"    [Homeostasis] prune damaged synapse #{s.id}")


class InflammatoryVisitor(MicroglialVisitor):
    """Chronic activation (M1, neuroinflammation analog Alzheimer).
    Bystander damage even healthy neurons."""
    def __init__(self):
        self.tnf_released = 0
        self.bystander_hits = 0
    def visit_healthy(self, n):
        # CHRONIC neuroinflammation: even healthy neurons get hit
        self.bystander_hits += 1
        self.tnf_released += 1
        print(f"    [Inflammatory] TNF-a hit BYSTANDER healthy neuron #{n.id} (collateral damage)")
    def visit_stressed(self, n):
        self.tnf_released += 1
        print(f"    [Inflammatory] TNF-a + IL-6 amplify stress on #{n.id}")
    def visit_apoptotic(self, n):
        self.tnf_released += 1
        print(f"    [Inflammatory] IL-1b release at apoptotic #{n.id}")
    def visit_damaged_synapse(self, s):
        print(f"    [Inflammatory] aggressive cleanup synapse #{s.id}")


def section(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


# =============================================================================
# 3. Demo 1 - same tissue, 3 visitor
# =============================================================================
def make_tissue() -> List[NeuralElement]:
    return [
        HealthyNeuron(1),
        HealthyNeuron(2),
        StressedNeuron(3, stress_level=0.8),
        ApoptoticNeuron(4),
        DamagedSynapse(5, activity=0.05),
        HealthyNeuron(6),
        StressedNeuron(7, stress_level=0.5),
        DamagedSynapse(8, activity=0.02),
    ]


def scan_tissue(visitor: MicroglialVisitor, tissue: List[NeuralElement]) -> None:
    for elem in tissue:
        elem.accept(visitor)


def demo_microglia_scan() -> None:
    section("Demo 1 - Microglial scan: 4 element type x 3 visitor")

    print("\n[Surveillance mode]")
    sv = SurveillanceVisitor()
    scan_tissue(sv, make_tissue())
    for line in sv.log:
        print("    " + line)

    print("\n[Homeostasis mode] (healthy microglia)")
    hv = HomeostasisVisitor()
    scan_tissue(hv, make_tissue())
    print(f"    Summary: BDNF={hv.bdnf_released}, phagocytosed={hv.phagocytosed}, pruned={hv.pruned}")

    print("\n[Inflammatory mode] (chronic activation, Alzheimer-like)")
    iv = InflammatoryVisitor()
    scan_tissue(iv, make_tissue())
    print(f"    Summary: TNF={iv.tnf_released}, BYSTANDER damage on healthy={iv.bystander_hits}")


# =============================================================================
# 4. Demo 2 - 4 Anti-patterns
# =============================================================================
def demo_isinstance_antipattern() -> None:
    section("Demo 2a - Anti-pattern: isinstance() inside visitor")
    print()
    print("  WRONG:")
    print("    def visit(self, e):")
    print("        if isinstance(e, HealthyNeuron): ...")
    print("        elif isinstance(e, StressedNeuron): ...")
    print()
    print("  -> Bypasses double dispatch.")
    print("  -> Adding new element type requires touching every visitor's visit().")
    print("  Fix: trust accept(visitor) -> visitor.visit_X(self).")


def demo_mutate_antipattern() -> None:
    section("Demo 2b - Anti-pattern: visitor mutates element")
    print()

    @dataclass
    class TaggableNeuron:
        id: int
        tagged: bool = False
        def accept(self, v): v(self)

    n = TaggableNeuron(id=1)
    def bad_visit(neuron):
        neuron.tagged = True   # SIDE EFFECT
    n.accept(bad_visit)
    print(f"    After 1st visit: tagged = {n.tagged}")
    n.accept(bad_visit)
    print(f"    After 2nd visit: tagged = {n.tagged} (idempotent here, but in general:")
    print()
    print("  Problem: traverse N times -> different state each time.")
    print("  Fix: visitor stateless (or state in visitor); element immutable.")
    print("       Need transform? Return NEW element from visit (transformer visitor).")


def demo_cyclic_import() -> None:
    section("Demo 2c - Cyclic import: Visitor <-> Element")
    print()
    print("  Problem:")
    print("    elements.py: from visitors import MicroglialVisitor")
    print("    visitors.py: from elements import HealthyNeuron, StressedNeuron, ...")
    print()
    print("  Fix options:")
    print("    1. from __future__ import annotations + 'forward-ref' strings.")
    print("    2. typing.TYPE_CHECKING guard (only import for type-checker).")
    print("    3. Define Visitor as Protocol (typing.Protocol) — no concrete dep.")
    print("    4. Common base in 3rd module to break cycle.")


def demo_forgotten_visit() -> None:
    section("Demo 2d - Forgotten visit_X when adding new element type")
    print()
    print("  If we add ` PlaqueAggregate(NeuralElement)` but Visitor base has no abstract")
    print("  visit_plaque, an old visitor + new element silently calls fall-through method.")
    print()
    print("  Demo: try to instantiate visitor missing visit_plaque (with abstract guard):")

    # Create extended visitor base requiring visit_plaque
    class ExtendedVisitor(MicroglialVisitor):
        @abstractmethod
        def visit_plaque(self, p) -> None: ...

    class IncompleteVisitor(ExtendedVisitor):
        # Inherits all 4 abstracts from MicroglialVisitor + visit_plaque, only impls 4.
        def visit_healthy(self, n): pass
        def visit_stressed(self, n): pass
        def visit_apoptotic(self, n): pass
        def visit_damaged_synapse(self, s): pass
        # NOTE: forgot visit_plaque

    try:
        IncompleteVisitor()
    except TypeError as e:
        print(f"  OK ABC blocks instantiation: {e}")
    print("  Fix: every visit_X is @abstractmethod -> subclass must implement or fail at init.")


def demo_failure_modes() -> None:
    demo_isinstance_antipattern()
    demo_mutate_antipattern()
    demo_cyclic_import()
    demo_forgotten_visit()


# =============================================================================
# 5. Demo 3 - Visitor over AST (revisit Lesson 15)
# =============================================================================
class Expr(ABC):
    @abstractmethod
    def accept(self, v: "ExprVisitor"): ...


@dataclass(frozen=True)
class NumLit(Expr):
    value: float
    def accept(self, v): return v.visit_num(self)


@dataclass(frozen=True)
class BoolLit(Expr):
    value: bool
    def accept(self, v): return v.visit_bool(self)


@dataclass(frozen=True)
class Var(Expr):
    name: str
    def accept(self, v): return v.visit_var(self)


@dataclass(frozen=True)
class And(Expr):
    left: Expr
    right: Expr
    def accept(self, v): return v.visit_and(self)


@dataclass(frozen=True)
class Or(Expr):
    left: Expr
    right: Expr
    def accept(self, v): return v.visit_or(self)


@dataclass(frozen=True)
class Less(Expr):
    left: Expr
    right: Expr
    def accept(self, v): return v.visit_less(self)


class ExprVisitor(ABC):
    @abstractmethod
    def visit_num(self, n: NumLit): ...
    @abstractmethod
    def visit_bool(self, b: BoolLit): ...
    @abstractmethod
    def visit_var(self, v: Var): ...
    @abstractmethod
    def visit_and(self, a: And): ...
    @abstractmethod
    def visit_or(self, o: Or): ...
    @abstractmethod
    def visit_less(self, l: Less): ...


class PrettyPrintVisitor(ExprVisitor):
    def __init__(self): self.depth = 0
    def _indent(self): return "  " * self.depth
    def visit_num(self, n): return f"{self._indent()}NumLit({n.value})"
    def visit_bool(self, b): return f"{self._indent()}BoolLit({b.value})"
    def visit_var(self, v): return f"{self._indent()}Var({v.name})"
    def _bin(self, name, l, r):
        head = f"{self._indent()}{name}"
        self.depth += 1
        ls = l.accept(self); rs = r.accept(self)
        self.depth -= 1
        return f"{head}\n{ls}\n{rs}"
    def visit_and(self, a): return self._bin("And", a.left, a.right)
    def visit_or(self, o): return self._bin("Or", o.left, o.right)
    def visit_less(self, l): return self._bin("Less", l.left, l.right)


class EvalVisitor(ExprVisitor):
    def __init__(self, ctx: Dict[str, Any]):
        self.ctx = ctx
    def visit_num(self, n): return n.value
    def visit_bool(self, b): return b.value
    def visit_var(self, v):
        if v.name not in self.ctx: raise NameError(f"undefined {v.name!r}")
        return self.ctx[v.name]
    def visit_and(self, a): return bool(a.left.accept(self)) and bool(a.right.accept(self))
    def visit_or(self, o): return bool(o.left.accept(self)) or bool(o.right.accept(self))
    def visit_less(self, l): return l.left.accept(self) < l.right.accept(self)


class OptimizeVisitor(ExprVisitor):
    """Constant folding. Returns NEW AST (transformer visitor)."""
    def visit_num(self, n): return n
    def visit_bool(self, b): return b
    def visit_var(self, v): return v
    def visit_and(self, a):
        l = a.left.accept(self); r = a.right.accept(self)
        if isinstance(l, BoolLit) and l.value is False: return BoolLit(False)
        if isinstance(r, BoolLit) and r.value is False: return BoolLit(False)
        if isinstance(l, BoolLit) and l.value is True:  return r
        if isinstance(r, BoolLit) and r.value is True:  return l
        return And(l, r)
    def visit_or(self, o):
        l = o.left.accept(self); r = o.right.accept(self)
        if isinstance(l, BoolLit) and l.value is True:  return BoolLit(True)
        if isinstance(r, BoolLit) and r.value is True:  return BoolLit(True)
        if isinstance(l, BoolLit) and l.value is False: return r
        if isinstance(r, BoolLit) and r.value is False: return l
        return Or(l, r)
    def visit_less(self, l):
        ll = l.left.accept(self); rr = l.right.accept(self)
        if isinstance(ll, NumLit) and isinstance(rr, NumLit):
            return BoolLit(ll.value < rr.value)
        return Less(ll, rr)


class ToSQLVisitor(ExprVisitor):
    def visit_num(self, n): return str(n.value)
    def visit_bool(self, b): return "TRUE" if b.value else "FALSE"
    def visit_var(self, v): return v.name
    def visit_and(self, a): return f"({a.left.accept(self)} AND {a.right.accept(self)})"
    def visit_or(self, o):  return f"({o.left.accept(self)} OR {o.right.accept(self)})"
    def visit_less(self, l): return f"({l.left.accept(self)} < {l.right.accept(self)})"


def demo_visitor_over_ast() -> None:
    section("Demo 3 - Visitor over AST: 4 visitor on same tree")

    # AST: (x AND TRUE) OR (3 < 5)
    ast = Or(
        And(Var("x"), BoolLit(True)),
        Less(NumLit(3), NumLit(5)),
    )

    print("\n  AST:")
    print(ast.accept(PrettyPrintVisitor()))

    print("\n  EvalVisitor with ctx={x: True}:")
    print("    result =", ast.accept(EvalVisitor({"x": True})))

    print("\n  OptimizeVisitor (constant folding):")
    optimized = ast.accept(OptimizeVisitor())
    print(optimized.accept(PrettyPrintVisitor()))
    print("    -> 'x AND TRUE' folded to 'x'; '3 < 5' folded to BoolLit(True);")
    print("    -> 'x OR True' folded to BoolLit(True).")

    print("\n  ToSQLVisitor on optimized:")
    print("    SQL:", optimized.accept(ToSQLVisitor()))


# =============================================================================
# 6. Demo 4 - match-case alternative
# =============================================================================
def evaluate_match(expr, ctx: Dict[str, Any]):
    match expr:
        case NumLit(value=v):       return v
        case BoolLit(value=v):      return v
        case Var(name=n):
            if n not in ctx: raise NameError(f"undefined {n!r}")
            return ctx[n]
        case And(left=l, right=r):  return bool(evaluate_match(l, ctx)) and bool(evaluate_match(r, ctx))
        case Or(left=l, right=r):   return bool(evaluate_match(l, ctx)) or bool(evaluate_match(r, ctx))
        case Less(left=l, right=r): return evaluate_match(l, ctx) < evaluate_match(r, ctx)
        case _: raise TypeError(f"unknown expr: {type(expr)}")


def demo_match_case() -> None:
    section("Demo 4 - match-case (Python 3.10+) - lightweight alternative")
    ast = Or(
        And(Var("x"), BoolLit(True)),
        Less(NumLit(3), NumLit(5)),
    )
    result = evaluate_match(ast, {"x": True})
    print(f"\n  Same eval via match-case: result = {result}")
    print()
    print("  match-case wins for one-shot ops (no class boilerplate, no accept method).")
    print("  Visitor class wins for: stateful traversal, plugin system, lifecycle management,")
    print("                          shared traversal logic across many ops.")


# =============================================================================
# RUNNER
# =============================================================================
def main() -> None:
    demo_microglia_scan()
    demo_failure_modes()
    demo_visitor_over_ast()
    demo_match_case()
    print("\n" + "=" * 70)
    print("  Het demo Lesson 23 - Visitor (Microglia).")
    print("  *** This is the LAST of 23 GoF design patterns. ***")
    print("=" * 70)


if __name__ == "__main__":
    main()
