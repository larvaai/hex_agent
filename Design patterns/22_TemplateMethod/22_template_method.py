"""
Lesson 22 - Template Method Pattern
Neuroscience analogy: LTP protocol (NMDA -> Ca2+ -> kinase -> AMPA) — skeleton fixed, hooks per synapse.

Cau truc file:
  1. SynapticPlasticityProtocol (skeleton) + 3 subclass
  2. Demo 1 - 3 synapse subclass cung skeleton
  3. Demo 2 - failure modes (override skeleton, fragile base, hook coupling)
  4. Demo 3 - Ellumm LessonProcessor template (3 lesson type)
  5. Demo 4 - Functional alternative (callbacks)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, Final, List, Optional


# =============================================================================
# 1. Skeleton (template method) + base class
# =============================================================================
@dataclass(frozen=True)
class GlutamateRelease:
    intensity: float


@dataclass(frozen=True)
class CalciumLevel:
    nM: float


@dataclass(frozen=True)
class KinaseState:
    camkii: float
    pka: float
    pkc: float
    dominant: str


@dataclass
class SynapseChange:
    delta: float    # positive = LTP, negative = LTD
    consolidated: bool = False
    subclass: str = ""


class SynapticPlasticityProtocol(ABC):
    """Base class. Skeleton 'induce' la TEMPLATE METHOD - subclass khong override.

    Hook luc cuoi:
      - _activate_nmda      [abstract]
      - _activate_kinases   [abstract]
      - _should_consolidate [optional, default threshold 0.3]
    """

    # Enforce skeleton via __init_subclass__
    _SKELETON_METHOD = "induce"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls._SKELETON_METHOD in cls.__dict__:
            raise TypeError(
                f"{cls.__name__} cannot override template method '{cls._SKELETON_METHOD}'"
            )

    # ---- TEMPLATE METHOD (do NOT override) ----
    def induce(self, stim_intensity: float, post_depolarization: float) -> SynapseChange:
        log = []
        log.append(f"  [{type(self).__name__}] induce_ltp(stim={stim_intensity:.2f}, depol={post_depolarization:.2f})")

        glu = self._release_glutamate(stim_intensity)
        log.append(f"    1. release_glutamate -> {glu}")

        if not self._coincidence_detected(glu, post_depolarization):
            log.append(f"    2. coincidence FAIL -> no plasticity")
            for line in log:
                print(line)
            return SynapseChange(delta=0.0, subclass=type(self).__name__)
        log.append(f"    2. coincidence OK")

        ca = self._activate_nmda(glu, post_depolarization)
        log.append(f"    3. activate_nmda [HOOK] -> Ca²⁺={ca.nM:.0f}nM")

        kin = self._activate_kinases(ca)
        log.append(f"    4. activate_kinases [HOOK] -> dominant={kin.dominant}")

        ampa = self._modify_ampa(kin)
        log.append(f"    5. modify_ampa -> {ampa:+.2f}")

        delta = self._strengthen_synapse(ampa, kin)
        log.append(f"    6. strengthen_synapse -> delta={delta:+.2f}")

        consolidated = self._should_consolidate(delta)
        if consolidated:
            self._late_phase_protein_synthesis()
            log.append(f"    7. consolidate (late-phase) [HOOK said yes]")
        else:
            log.append(f"    7. no consolidation (delta below threshold)")

        for line in log:
            print(line)
        return SynapseChange(delta=delta, consolidated=consolidated, subclass=type(self).__name__)

    # ---- SHARED operations ----
    def _release_glutamate(self, stim: float) -> GlutamateRelease:
        return GlutamateRelease(intensity=min(1.0, stim))

    def _coincidence_detected(self, glu: GlutamateRelease, depol: float) -> bool:
        return glu.intensity > 0.2 and depol > 0.3

    def _modify_ampa(self, kin: KinaseState) -> float:
        # Phosphorylation level proxy
        return 0.5 * (kin.camkii + kin.pka) - 0.3 * kin.pkc

    def _strengthen_synapse(self, ampa: float, kin: KinaseState) -> float:
        return ampa  # signed: + LTP, - LTD

    def _late_phase_protein_synthesis(self) -> None:
        pass  # placeholder; in real life: gene transcription -> protein

    # ---- HOOKS (subclass implements) ----
    @abstractmethod
    def _activate_nmda(self, glu: GlutamateRelease, depol: float) -> CalciumLevel: ...

    @abstractmethod
    def _activate_kinases(self, ca: CalciumLevel) -> KinaseState: ...

    def _should_consolidate(self, delta: float) -> bool:
        """Optional hook with default."""
        return abs(delta) > 0.3


# =============================================================================
# 2. Concrete subclasses (3 synapse types, same skeleton, different hooks)
# =============================================================================
class HippocampalCA1(SynapticPlasticityProtocol):
    """NR2B-dominant NMDA, CaMKII heavy. Fast strong LTP. Memory."""

    def _activate_nmda(self, glu: GlutamateRelease, depol: float) -> CalciumLevel:
        # NR2B has slow off-kinetics -> more Ca²⁺
        return CalciumLevel(nM=glu.intensity * depol * 1500)

    def _activate_kinases(self, ca: CalciumLevel) -> KinaseState:
        return KinaseState(
            camkii=min(1.0, ca.nM / 1000),
            pka=min(1.0, ca.nM / 2000),
            pkc=0.1,
            dominant="CaMKII",
        )


class CerebellarPurkinje(SynapticPlasticityProtocol):
    """mGluR + voltage-gated Ca²⁺, PKC heavy. LTD instead of LTP."""

    def _activate_nmda(self, glu: GlutamateRelease, depol: float) -> CalciumLevel:
        # mGluR pathway gives lower Ca²⁺ but PKC dominant
        return CalciumLevel(nM=glu.intensity * depol * 700)

    def _activate_kinases(self, ca: CalciumLevel) -> KinaseState:
        return KinaseState(
            camkii=0.2,
            pka=0.1,
            pkc=min(1.0, ca.nM / 600),     # PKC heavy
            dominant="PKC",
        )

    def _should_consolidate(self, delta: float) -> bool:
        # Purkinje does LTD; consolidate when delta is negative enough
        return delta < -0.2


class CorticalLayer5(SynapticPlasticityProtocol):
    """NR2A-dominant NMDA. Higher threshold. Mixed kinases."""

    def _activate_nmda(self, glu: GlutamateRelease, depol: float) -> CalciumLevel:
        # NR2A faster off-kinetics -> less total Ca²⁺
        return CalciumLevel(nM=glu.intensity * depol * 1000)

    def _activate_kinases(self, ca: CalciumLevel) -> KinaseState:
        return KinaseState(
            camkii=min(1.0, ca.nM / 1500),
            pka=min(1.0, ca.nM / 1500),
            pkc=0.3,
            dominant="CaMKII+PKA",
        )

    def _should_consolidate(self, delta: float) -> bool:
        # Cortex needs stronger signal to consolidate
        return delta > 0.5


def section(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


# =============================================================================
# 3. Demo 1 - same skeleton, 3 subclass
# =============================================================================
def demo_three_synapses() -> None:
    section("Demo 1 - SynapticPlasticity: same skeleton, 3 subclass hooks")

    cases = [
        ("Strong activation (stim=0.9, depol=0.8)", 0.9, 0.8),
        ("Subthreshold      (stim=0.4, depol=0.2)", 0.4, 0.2),
        ("Moderate          (stim=0.6, depol=0.5)", 0.6, 0.5),
    ]

    for label, stim, depol in cases:
        print(f"\n  CASE: {label}")
        for synapse in (HippocampalCA1(), CerebellarPurkinje(), CorticalLayer5()):
            change = synapse.induce(stim, depol)
            tag = "LTP" if change.delta > 0 else "LTD" if change.delta < 0 else "no-change"
            print(f"    -> {change.subclass}: delta={change.delta:+.2f} ({tag}), "
                  f"consolidated={change.consolidated}")


# =============================================================================
# 4. Demo 2 - Failure modes
# =============================================================================
def demo_skeleton_override_blocked() -> None:
    section("Demo 2a - Subclass cannot override template method (skeleton)")
    print()
    try:
        class BadSynapse(SynapticPlasticityProtocol):
            def induce(self, stim_intensity, post_depolarization):  # WRONG
                return SynapseChange(delta=99.9, subclass="cheater")
            def _activate_nmda(self, glu, depol):
                return CalciumLevel(0)
            def _activate_kinases(self, ca):
                return KinaseState(0, 0, 0, "none")
    except TypeError as e:
        print(f"  OK guard caught: {e}")
        print(f"  -> Skeleton protected via __init_subclass__.")


def demo_fragile_base_class() -> None:
    section("Demo 2b - Fragile base class problem")
    print()
    print("  If we add a new step (e.g. _activate_metabotropic) into induce()'s skeleton,")
    print("  every existing subclass would need a hook for it OR base must provide a default.")
    print("  Lesson: hook count should be MINIMIZED. Each new hook = blast radius across subclass.")
    print()
    print("  Mitigation:")
    print("    1. Default no-op for new hooks (preserves backward compat)")
    print("    2. Strategy injection instead of hook (if skeleton itself needs to evolve)")
    print("    3. Versioned base class (BaseV1, BaseV2)")


def demo_hook_coupling() -> None:
    section("Demo 2c - Hook coupling: hook accesses base internals")
    print()
    print("  Anti-pattern: subclass hook reads self._coincidence_threshold (private of base).")
    print("  -> Refactor base internal -> all subclasses break.")
    print("  Fix: hook receives data via parameters; base passes what hook needs.")
    print("       Hook returns value; base uses it. No private access.")
    print()
    print("  In our protocol above, hooks _activate_nmda(glu, depol) get all input via params,")
    print("  no self._private access. That's the correct shape.")


def demo_failure_modes() -> None:
    demo_skeleton_override_blocked()
    demo_fragile_base_class()
    demo_hook_coupling()


# =============================================================================
# 5. Demo 3 - Ellumm LessonProcessor template
# =============================================================================
@dataclass
class LessonContent:
    raw: str
    parsed: Optional[Any] = None


@dataclass
class UserResponse:
    payload: Any


@dataclass
class GradedResult:
    score: float
    feedback: str


class LessonProcessor(ABC):
    """Pipeline: load -> preprocess [HOOK] -> validate -> present [HOOK] ->
       collect [HOOK] -> grade [HOOK] -> save."""

    _SKELETON_METHOD = "process"

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls._SKELETON_METHOD in cls.__dict__:
            raise TypeError(f"{cls.__name__} cannot override 'process'")

    # TEMPLATE METHOD
    def process(self, lesson_path: str, user_id: str) -> GradedResult:
        print(f"\n  [{type(self).__name__}] process({lesson_path!r}, user={user_id})")
        content = self._load_content(lesson_path)
        print(f"    1. load_content -> {len(content.raw)} chars")
        content = self._preprocess_content(content)
        print(f"    2. preprocess [HOOK] -> parsed type={type(content.parsed).__name__}")
        self._validate_prereqs(user_id)
        print(f"    3. validate_prereqs OK")
        self._present(content)
        print(f"    4. present [HOOK]")
        response = self._collect_response()
        print(f"    5. collect_response [HOOK] -> {response.payload}")
        result = self._grade(response, content)
        print(f"    6. grade [HOOK] -> score={result.score}, fb={result.feedback!r}")
        self._save_progress(user_id, result)
        print(f"    7. save_progress")
        return result

    # SHARED
    def _load_content(self, path: str) -> LessonContent:
        return LessonContent(raw=f"[fake content of {path}]")

    def _validate_prereqs(self, user_id: str) -> None:
        pass

    def _save_progress(self, user_id: str, result: GradedResult) -> None:
        pass

    # HOOKS
    @abstractmethod
    def _preprocess_content(self, c: LessonContent) -> LessonContent: ...
    @abstractmethod
    def _present(self, c: LessonContent) -> None: ...
    @abstractmethod
    def _collect_response(self) -> UserResponse: ...
    @abstractmethod
    def _grade(self, r: UserResponse, c: LessonContent) -> GradedResult: ...


class MarkdownLessonProcessor(LessonProcessor):
    def _preprocess_content(self, c):
        c.parsed = {"type": "markdown_ast", "headings": ["H1", "H2"]}
        return c

    def _present(self, c):
        # render to HTML
        pass

    def _collect_response(self) -> UserResponse:
        return UserResponse(payload={"quiz_answers": [1, 2, 0]})

    def _grade(self, r, c) -> GradedResult:
        # auto-grade
        correct = sum(a == k for a, k in zip(r.payload["quiz_answers"], [1, 2, 0]))
        return GradedResult(score=correct / 3, feedback="auto-graded MCQ")


class VideoLessonProcessor(LessonProcessor):
    def _preprocess_content(self, c):
        c.parsed = {"type": "video", "duration_s": 600, "captions": True}
        return c

    def _present(self, c):
        pass

    def _collect_response(self) -> UserResponse:
        return UserResponse(payload={"watched_pct": 0.85, "reflection": "good!"})

    def _grade(self, r, c) -> GradedResult:
        s = r.payload["watched_pct"]
        return GradedResult(score=s, feedback="based on watch %")


class CodingLessonProcessor(LessonProcessor):
    def _preprocess_content(self, c):
        c.parsed = {"type": "coding", "tests": ["test_a", "test_b"]}
        return c

    def _present(self, c):
        pass

    def _collect_response(self) -> UserResponse:
        return UserResponse(payload={"code": "def add(a,b): return a+b"})

    def _grade(self, r, c) -> GradedResult:
        # run tests against r.payload["code"]
        passed = 2
        total = len(c.parsed["tests"])
        return GradedResult(score=passed / total, feedback=f"tests {passed}/{total} pass")


def demo_ellumm_lesson_processor() -> None:
    section("Demo 3 - Ellumm LessonProcessor: same skeleton, 3 subclass")
    for proc in (MarkdownLessonProcessor(), VideoLessonProcessor(), CodingLessonProcessor()):
        proc.process("lesson_22.md", user_id="u1")


# =============================================================================
# 6. Demo 4 - Functional alternative
# =============================================================================
def induce_ltp_func(
    stim: float, depol: float,
    *,
    activate_nmda: Callable[[float, float], float],
    activate_kinases: Callable[[float], str],
    should_consolidate: Callable[[float], bool] = lambda d: abs(d) > 0.3,
) -> dict:
    """Skeleton as function; hooks as keyword-only callables."""
    if stim < 0.2 or depol < 0.3:
        return {"delta": 0.0, "consolidated": False, "reason": "coincidence fail"}
    ca = activate_nmda(stim, depol)
    dominant = activate_kinases(ca)
    delta = ca / 1000 if "CaMK" in dominant else -ca / 1500   # toy formula
    return {
        "delta": round(delta, 2),
        "consolidated": should_consolidate(delta),
        "dominant_kinase": dominant,
    }


def demo_functional_template() -> None:
    section("Demo 4 - Functional Template Method (callbacks instead of subclass)")

    nmda_nr2b = lambda s, d: s * d * 1500
    nmda_nr2a = lambda s, d: s * d * 1000

    kin_camkii = lambda ca: "CaMKII"
    kin_pkc    = lambda ca: "PKC"

    print()
    for label, nmda, kinases in [
        ("NR2B + CaMKII (Hippocampal-like)",   nmda_nr2b, kin_camkii),
        ("NR2A + CaMKII+PKA (Cortex-like)",    nmda_nr2a, kin_camkii),
        ("mGluR-ish + PKC (Cerebellar-like)",  nmda_nr2a, kin_pkc),
    ]:
        r = induce_ltp_func(0.8, 0.7, activate_nmda=nmda, activate_kinases=kinases)
        print(f"  {label:40s} -> {r}")
    print("\n  -> Same skeleton, hooks as functions. No class needed for simple cases.")


# =============================================================================
# RUNNER
# =============================================================================
def main() -> None:
    demo_three_synapses()
    demo_failure_modes()
    demo_ellumm_lesson_processor()
    demo_functional_template()
    print("\n" + "=" * 70)
    print("  Het demo Lesson 22 - Template Method (LTP).")
    print("=" * 70)


if __name__ == "__main__":
    main()
