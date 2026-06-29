"""
Lesson 40 — Ubiquitous Language Case Study
============================================

Maintain glossary-as-code cho 4 BC Ellumm, detect cross-BC term collision,
detect language drift in code, plan rename migration 5-phase
(Submission → Attempt) với impact analysis.

Run: python 40_ubiquitous_language.py
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple


# =============================================================================
# [GLOSSARY MODEL]
# =============================================================================

class TermKind(str, Enum):
    ENTITY = "entity"
    VALUE_OBJECT = "value_object"
    DOMAIN_EVENT = "domain_event"
    COMMAND = "command"
    AGGREGATE = "aggregate"
    SERVICE = "service"
    POLICY = "policy"


@dataclass
class Term:
    name: str
    kind: TermKind
    definition: str
    bounded_context: str
    since: date = field(default_factory=lambda: date(2026, 1, 1))
    until: Optional[date] = None              # set when deprecated
    synonyms: List[str] = field(default_factory=list)
    used_by: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    replaced_by: Optional[str] = None

    @property
    def is_deprecated(self) -> bool:
        return self.until is not None

    def __str__(self) -> str:
        marker = " (DEPRECATED)" if self.is_deprecated else ""
        return f"{self.name}{marker}: {self.definition[:50]}..."


class BCGlossary:
    """Per-BC glossary."""

    def __init__(self, bc_name: str) -> None:
        self.bc_name = bc_name
        self.terms: Dict[str, Term] = {}

    def add(self, term: Term) -> None:
        if term.bounded_context != self.bc_name:
            raise ValueError(f"Term {term.name} BC mismatch: {term.bounded_context} != {self.bc_name}")
        self.terms[term.name] = term

    def deprecate(self, name: str, replaced_by: str, until: date) -> None:
        if name in self.terms:
            term = self.terms[name]
            term.until = until
            term.replaced_by = replaced_by

    def rename(self, old: str, new: str, when: date) -> None:
        """Add new term with same kind+definition; deprecate old."""
        if old not in self.terms:
            raise ValueError(f"No term {old} to rename")
        old_term = self.terms[old]
        new_term = Term(
            name=new, kind=old_term.kind,
            definition=old_term.definition,
            bounded_context=self.bc_name,
            since=when,
            synonyms=[old] + old_term.synonyms,
            used_by=list(old_term.used_by),
            examples=list(old_term.examples),
        )
        self.add(new_term)
        self.deprecate(old, replaced_by=new, until=when)

    def active_terms(self) -> List[Term]:
        return [t for t in self.terms.values() if not t.is_deprecated]

    def deprecated_terms(self) -> List[Term]:
        return [t for t in self.terms.values() if t.is_deprecated]


# =============================================================================
# [GLOBAL GLOSSARY]   Cross-BC translation + collision detection
# =============================================================================

@dataclass
class CrossBCTranslation:
    bc_a: str
    term_a: str
    bc_b: str
    term_b: str
    notes: str = ""


class GlobalGlossary:
    def __init__(self) -> None:
        self.bcs: Dict[str, BCGlossary] = {}
        self.translations: List[CrossBCTranslation] = []

    def add_bc(self, glossary: BCGlossary) -> None:
        self.bcs[glossary.bc_name] = glossary

    def add_translation(self, t: CrossBCTranslation) -> None:
        self.translations.append(t)

    def detect_term_collisions(self) -> Dict[str, List[Tuple[str, Term]]]:
        """Find term names appearing in multiple BCs (different meanings)."""
        name_to_bcs: Dict[str, List[Tuple[str, Term]]] = defaultdict(list)
        for bc_name, glossary in self.bcs.items():
            for term in glossary.active_terms():
                name_to_bcs[term.name].append((bc_name, term))
        return {n: bcs for n, bcs in name_to_bcs.items() if len(bcs) >= 2}


# =============================================================================
# [DRIFT DETECTOR]
# =============================================================================

@dataclass
class DriftIssue:
    issue_type: str
    location: str
    detail: str


def detect_language_drift(code_source: str, glossary: BCGlossary) -> List[DriftIssue]:
    """Heuristic detector — find inconsistencies between code and glossary."""
    issues: List[DriftIssue] = []
    active = {t.name for t in glossary.active_terms()}
    deprecated = {t.name for t in glossary.deprecated_terms()}

    # 1. Find class definitions in code
    class_names = re.findall(r"class\s+(\w+)", code_source)
    # 2. Find function names
    function_names = re.findall(r"def\s+(\w+)", code_source)

    # 3. Detect deprecated term still referenced
    for name in class_names + function_names:
        for dep in deprecated:
            if dep.lower() in name.lower() and dep.lower() != name.lower():
                continue          # partial match — skip
            if dep == name:
                replaced = glossary.terms[dep].replaced_by
                issues.append(DriftIssue(
                    issue_type="DEPRECATED_TERM_USED",
                    location=f"class/def '{name}'",
                    detail=f"deprecated term, replaced by '{replaced}'",
                ))

    # 4. Detect class names not in glossary at all (undefined term)
    for name in class_names:
        if name in active or name in deprecated:
            continue
        # Skip Python infrastructure terms
        if name.endswith(("DTO", "VO", "Test", "Mock", "Helper", "Util")):
            continue
        # Skip common neutral names
        if name in {"object", "Protocol", "Enum", "Exception"}:
            continue
        issues.append(DriftIssue(
            issue_type="UNDEFINED_TERM",
            location=f"class '{name}'",
            detail="appears in code but not in glossary",
        ))

    # 5. Detect glossary entries not used in code (orphaned)
    for term_name in active:
        # Look for term in class/function/comment
        pattern = re.compile(rf"\b{re.escape(term_name)}\b", re.IGNORECASE)
        if not pattern.search(code_source):
            issues.append(DriftIssue(
                issue_type="ORPHANED_TERM",
                location=f"glossary entry '{term_name}'",
                detail="defined but not used in code",
            ))

    return issues


# =============================================================================
# [RENAME IMPACT ANALYZER]
# =============================================================================

@dataclass
class ImpactItem:
    layer: str            # code, test, db, event, doc, ui
    description: str


@dataclass
class MigrationPlan:
    old_name: str
    new_name: str
    bc_name: str
    phases: Dict[str, List[str]] = field(default_factory=dict)
    impacts: List[ImpactItem] = field(default_factory=list)


def analyze_rename_impact(old: str, new: str, bc_name: str) -> MigrationPlan:
    """Generate migration plan for rename within a BC."""
    plan = MigrationPlan(old_name=old, new_name=new, bc_name=bc_name)

    # Layer 1 — Code
    plan.impacts.append(ImpactItem("CODE",
        f"class {old} → class {new}"))
    plan.impacts.append(ImpactItem("CODE",
        f"methods: submit_{old.lower()}() → start_{new.lower()}()"))
    plan.impacts.append(ImpactItem("CODE",
        f"I{old}Repository → I{new}Repository"))
    plan.impacts.append(ImpactItem("CODE",
        f"{old}Factory → {new}Factory"))

    # Layer 2 — Tests
    plan.impacts.append(ImpactItem("TEST",
        f"test_{old.lower()}_* → test_{new.lower()}_*"))

    # Layer 3 — DB
    plan.impacts.append(ImpactItem("DB",
        f"table '{old.lower()}s' → 'attempts' (with migration script)"))
    plan.impacts.append(ImpactItem("DB",
        f"column {old.lower()}_id → {new.lower()}_id"))

    # Layer 4 — Events (Published Language!)
    plan.impacts.append(ImpactItem("EVENT",
        f"{old}GradedV1 → keep + add {new}GradedV2 (Published Language versioning)"))

    # Layer 5 — API
    plan.impacts.append(ImpactItem("API",
        f"POST /{old.lower()}s → POST /attempts (with redirect/deprecation)"))

    # Layer 6 — UI / Logs
    plan.impacts.append(ImpactItem("UI",
        f"Button 'Submit Quiz' → 'Start Attempt'"))
    plan.impacts.append(ImpactItem("UI",
        f"Error 'Submission failed' → 'Attempt failed'"))
    plan.impacts.append(ImpactItem("LOG",
        f"Log field {old.lower()}_id → {new.lower()}_id (update search queries)"))

    # Layer 7 — Docs / Glossary
    plan.impacts.append(ImpactItem("DOC",
        f"ADR-XX documenting rename rationale"))
    plan.impacts.append(ImpactItem("DOC",
        f"Glossary: mark {old} deprecated, add {new}"))

    # Phases
    plan.phases = {
        "Phase 1 — Deprecate (week 1)": [
            f"Add '{new}' as new term in glossary (preferred).",
            f"Mark '{old}' as deprecated (synonym, replaced_by={new}).",
            f"Code still uses {old}.",
            f"Draft ADR documenting rationale.",
        ],
        "Phase 2 — Dual support (week 2-4)": [
            f"Add new API endpoint /attempts aliasing /{old.lower()}s.",
            f"DB: add new column {new.lower()}_id NULL; backfill from {old.lower()}_id; keep both.",
            f"Publish both {old}GradedV1 AND {new}GradedV2 events.",
            f"Update internal code: class {old} → {new}.",
            f"Update tests.",
        ],
        "Phase 3 — Migration window (month 2-3)": [
            f"Notify downstream BCs to upgrade consumer from {old}GradedV1 → {new}GradedV2.",
            f"Monitor V1 consumer count → block new subscribers.",
            f"Update UI labels to use '{new}' term.",
            f"Update log fields + search queries.",
        ],
        "Phase 4 — Remove old (month 4)": [
            f"Drop old API endpoint /{old.lower()}s.",
            f"Drop old DB column {old.lower()}_id.",
            f"Stop publishing {old}GradedV1 events.",
            f"Remove '{old}' synonym references from glossary.",
        ],
        "Phase 5 — Cleanup (month 5)": [
            f"Code review for stragglers (grep '{old}' in repo).",
            f"Update Slack channel from #{old.lower()}s → #attempts.",
            f"Update Jira ticket templates.",
            f"Set 'until' date on '{old}' in glossary.",
        ],
    }
    return plan


# =============================================================================
# [CASE STUDY DATA — Build glossaries for 4 Ellumm BCs]
# =============================================================================

def build_quiz_authoring_glossary() -> BCGlossary:
    g = BCGlossary("Quiz Authoring")
    g.add(Term("Quiz", TermKind.AGGREGATE,
        "Aggregate root chứa Questions; có lifecycle draft/published/retired",
        "Quiz Authoring", used_by=["Quiz aggregate", "QuizPublished event"]))
    g.add(Term("Question", TermKind.VALUE_OBJECT,
        "Câu hỏi trong Quiz: text + correct_answer + weight",
        "Quiz Authoring", used_by=["Quiz.questions"]))
    g.add(Term("Author", TermKind.ENTITY,
        "User role trong Quiz Authoring BC — người tạo quiz",
        "Quiz Authoring", synonyms=["User"], used_by=["QuizContextUser"]))
    g.add(Term("QuizPublished", TermKind.DOMAIN_EVENT,
        "Quiz đã được publish, sẵn sàng cho student",
        "Quiz Authoring", used_by=["QuizPublished event"]))
    return g


def build_submission_glossary() -> BCGlossary:
    g = BCGlossary("Submission")
    g.add(Term("Submission", TermKind.AGGREGATE,
        "Aggregate root — 1 lần làm quiz của student; chứa Attempts",
        "Submission",
        used_by=["Submission aggregate", "SubmissionGraded event"]))
    g.add(Term("Attempt", TermKind.ENTITY,
        "1 lần thử của Submission (retry sinh ra Attempt mới)",
        "Submission", used_by=["Submission.attempts"]))
    g.add(Term("Score", TermKind.VALUE_OBJECT,
        "Raw points của 1 attempt — có max_points",
        "Submission", used_by=["Attempt.score"]))
    g.add(Term("Student", TermKind.ENTITY,
        "User role trong Submission BC — người làm quiz",
        "Submission", synonyms=["User"]))
    g.add(Term("SubmissionGraded", TermKind.DOMAIN_EVENT,
        "Submission đã được chấm, có score",
        "Submission", used_by=["SubmissionGraded event"]))
    return g


def build_leaderboard_glossary() -> BCGlossary:
    g = BCGlossary("Leaderboard")
    g.add(Term("Ranking", TermKind.AGGREGATE,
        "Aggregate root — bảng xếp hạng theo total points",
        "Leaderboard", used_by=["Ranking aggregate"]))
    g.add(Term("Position", TermKind.VALUE_OBJECT,
        "Vị trí của user trong ranking (rank #N)",
        "Leaderboard"))
    g.add(Term("Score", TermKind.VALUE_OBJECT,
        "Ranking value — derived từ raw points + time bonus",
        "Leaderboard", used_by=["Ranking.score"],
        examples=["KHÁC Score của Submission BC!"]))
    return g


def build_notification_glossary() -> BCGlossary:
    g = BCGlossary("Notification")
    g.add(Term("Recipient", TermKind.AGGREGATE,
        "Aggregate root cho người nhận thông báo",
        "Notification", synonyms=["User"]))
    g.add(Term("Receipt", TermKind.ENTITY,
        "1 lần thông báo cụ thể đã gửi (channel + body + sent_at)",
        "Notification"))
    g.add(Term("Channel", TermKind.VALUE_OBJECT,
        "Kênh thông báo: email / sms / push",
        "Notification"))
    return g


def build_global_glossary() -> GlobalGlossary:
    gg = GlobalGlossary()
    gg.add_bc(build_quiz_authoring_glossary())
    gg.add_bc(build_submission_glossary())
    gg.add_bc(build_leaderboard_glossary())
    gg.add_bc(build_notification_glossary())

    # Cross-BC translations (handle term collisions)
    gg.add_translation(CrossBCTranslation(
        bc_a="Submission", term_a="Student",
        bc_b="Quiz Authoring", term_b="Author",
        notes="Cùng user_id từ Auth0, khác semantic role",
    ))
    gg.add_translation(CrossBCTranslation(
        bc_a="Submission", term_a="Student",
        bc_b="Notification", term_b="Recipient",
        notes="ACL: AuthACL.to_notification_recipient()",
    ))
    gg.add_translation(CrossBCTranslation(
        bc_a="Submission", term_a="Score",
        bc_b="Leaderboard", term_b="Score",
        notes="DANGER: same name, different semantic. Submission.Score=raw; Leaderboard.Score=ranking value",
    ))
    return gg


# =============================================================================
# [DEMOS]
# =============================================================================

def banner(s: str) -> None:
    print("\n" + "=" * 76)
    print(f"  {s}")
    print("=" * 76)


def demo_1_per_bc_glossary() -> None:
    banner("DEMO 1 — Per-BC glossary for 4 Ellumm bounded contexts")
    gg = build_global_glossary()
    for bc_name, glossary in gg.bcs.items():
        print(f"\n  ┌─ {bc_name} ─ {len(glossary.active_terms())} active terms")
        for term in glossary.active_terms():
            syn = f" [synonyms: {term.synonyms}]" if term.synonyms else ""
            print(f"  │   • [{term.kind.value:<14}] {term.name}{syn}")
        print(f"  └─")
    total = sum(len(g.active_terms()) for g in gg.bcs.values())
    print(f"\n  Total: 4 BCs, {total} terms")
    assert total >= 15
    print("  PASS — glossary structured per-BC")


def demo_2_cross_bc_term_collision() -> None:
    banner("DEMO 2 — Cross-BC term collision detection")
    gg = build_global_glossary()
    collisions = gg.detect_term_collisions()

    print(f"\n  Terms appearing in multiple BCs: {len(collisions)}")
    for name, bcs in collisions.items():
        print(f"\n  ⚠ '{name}' has {len(bcs)} different meanings:")
        for bc, term in bcs:
            print(f"    - [{bc}] {term.definition[:55]}")
    assert "Score" in collisions
    print("\n  Cross-BC translations documented:")
    for t in gg.translations:
        print(f"    {t.bc_a}.{t.term_a} ↔ {t.bc_b}.{t.term_b}")
        print(f"       {t.notes}")
    print("  PASS — collision detected + translations documented")


def demo_3_drift_detector_healthy() -> None:
    banner("DEMO 3 — Drift detector on HEALTHY code (Submission BC)")
    glossary = build_submission_glossary()

    healthy_code = """
class Submission:
    def __init__(self, student, score):
        self.student = student
        self.score = score
    def grade(self, attempt):
        attempt.score = compute()

class Attempt:
    attempt_no: int
    score: Score

class Score:
    points: float
    max_points: float

class Student:
    user_id: str

class SubmissionGraded:
    submission_id: str
    """

    issues = detect_language_drift(healthy_code, glossary)
    print(f"  Drift issues in HEALTHY code: {len(issues)}")
    for i in issues[:5]:
        print(f"    - [{i.issue_type}] {i.location}: {i.detail}")
    # Allow some orphans because demo code doesn't use every term
    assert len(issues) <= 2
    print("  PASS — healthy code passes drift check")


def demo_4_drift_detector_drifting() -> None:
    banner("DEMO 4 — Drift detector on DRIFTING code (mixed synonyms)")
    glossary = build_submission_glossary()

    # Mark "Submission" as deprecated → rename to "Attempt" (just for this test)
    test_glossary = build_submission_glossary()
    # Simulate: imagine someone uses outdated terms
    drifting_code = """
class QuizSession:
    def __init__(self, user):
        self.user = user

class SubmissionTry:
    score: float

class Cohort:
    students: list

class StudyGroup:
    members: list
    """

    issues = detect_language_drift(drifting_code, test_glossary)
    print(f"  Drift issues in DRIFTING code: {len(issues)}")
    for i in issues[:8]:
        print(f"    - [{i.issue_type}] {i.location}: {i.detail}")
    if len(issues) > 8:
        print(f"    ... and {len(issues) - 8} more")
    undefined = [i for i in issues if i.issue_type == "UNDEFINED_TERM"]
    assert len(undefined) >= 3
    print(f"\n  Found {len(undefined)} undefined terms (not in glossary)")
    print("  PASS — drift detected, action required (add to glossary or rename)")


def demo_5_rename_impact_analysis() -> None:
    banner("DEMO 5 — Rename impact: Submission → Attempt (full analysis)")
    plan = analyze_rename_impact("Submission", "Attempt", "Submission")

    print(f"\n  Rename: '{plan.old_name}' → '{plan.new_name}' in BC '{plan.bc_name}'")
    print(f"\n  IMPACT MATRIX ({len(plan.impacts)} items):")
    by_layer: Dict[str, List[str]] = defaultdict(list)
    for impact in plan.impacts:
        by_layer[impact.layer].append(impact.description)
    for layer, items in by_layer.items():
        print(f"\n  [{layer}]")
        for item in items:
            print(f"    • {item}")

    assert len(plan.impacts) >= 10
    assert any(i.layer == "EVENT" for i in plan.impacts)
    print("\n  PASS — multi-layer impact analyzed")


def demo_6_migration_plan_5_phases() -> None:
    banner("DEMO 6 — 5-phase migration plan generation")
    plan = analyze_rename_impact("Submission", "Attempt", "Submission")

    print(f"\n  Migration plan for {plan.old_name} → {plan.new_name}:")
    for phase, steps in plan.phases.items():
        print(f"\n  ┌─ {phase}")
        for step in steps:
            print(f"  │   • {step}")
        print(f"  └─")

    assert len(plan.phases) == 5
    print("\n  PASS — 5-phase plan covers deprecate → dual → migrate → remove → cleanup")


def demo_7_glossary_rename_operation() -> None:
    banner("DEMO 7 — Apply rename in glossary: Submission → Attempt")
    g = build_submission_glossary()

    print(f"\n  Before rename:")
    print(f"    Active terms:     {sorted(t.name for t in g.active_terms())}")
    print(f"    Deprecated terms: {sorted(t.name for t in g.deprecated_terms())}")

    # Note: this BC already has both Submission AND Attempt — we'll re-rename
    # for demonstration. In real, original Submission was renamed → Attempt.
    g.rename("Submission", "QuizAttempt", when=date(2026, 6, 1))

    print(f"\n  After rename Submission → QuizAttempt:")
    print(f"    Active terms:     {sorted(t.name for t in g.active_terms())}")
    print(f"    Deprecated terms: {sorted(t.name for t in g.deprecated_terms())}")

    submission_term = g.terms["Submission"]
    print(f"\n  'Submission' entry:")
    print(f"    until:       {submission_term.until}")
    print(f"    replaced_by: {submission_term.replaced_by}")

    new_term = g.terms["QuizAttempt"]
    print(f"\n  'QuizAttempt' entry:")
    print(f"    since:       {new_term.since}")
    print(f"    synonyms:    {new_term.synonyms}")
    print(f"    inherited:   kind={new_term.kind.value}, def='{new_term.definition[:30]}...'")

    assert submission_term.is_deprecated
    assert submission_term.replaced_by == "QuizAttempt"
    assert "Submission" in new_term.synonyms
    print("  PASS — rename in glossary preserves history + transitions term")


def demo_8_published_language_versioning_in_rename() -> None:
    banner("DEMO 8 — Published Language event versioning during rename")
    print("""
  When renaming Submission → Attempt, internal code can change quickly:
      class Submission  →  class Attempt
      method submit_*   →  method start_*

  But Published Language events (cross-BC contract) must transition slowly:

  ┌─ Phase 1: Add V2 alongside V1 (keep both)
  │     @frozen class SubmissionGradedV1  (KEEP, mark deprecated)
  │     @frozen class AttemptGradedV2    (NEW)
  │
  │     Producer publishes BOTH events.
  │     Downstream BCs initially consume V1, gradually migrate to V2.
  │
  ├─ Phase 2: Monitor V1 consumer count
  │     Track which downstream BCs still subscribe V1.
  │     Coordinate with their team to upgrade.
  │
  ├─ Phase 3: Sunset V1 (after 3-6 months)
  │     Stop publishing V1.
  │     Remove deprecated class.
  │
  └─ Important: V1 schema does NOT change in transition. Only add V2.

  This is the same versioning pattern as Lesson 31 EDA + Lesson 34 Published Language.
  """)
    print("  PASS — Published Language transition documented for cross-BC rename")


def demo_9_anti_patterns_showcase() -> None:
    banner("DEMO 9 — Anti-pattern showcase")
    patterns = [
        ("A", "No glossary",
         "Ask 3 devs 'what's X?' → 3 answers. Create glossary BEFORE code grows."),
        ("B", "Glossary in stale Confluence",
         "Last edit 2 years ago. Keep glossary AS CODE (committed with PR)."),
        ("C", "Code uses dev jargon",
         "SubmissionDTO, QuizManager - not business UL. Use business terms."),
        ("D", "Term overload undocumented",
         "Same class name in 2 BCs, no translation. Document in cross-BC table."),
        ("E", "Rename without ADR",
         "50 files changed, no rationale. Always create ADR."),
        ("F", "Big-bang rename",
         "Single PR renames everywhere → downstream breaks. Use 5-phase plan."),
        ("G", "Glossary out of sync",
         "Class definition diverged from glossary entry. CI gate."),
        ("H", "Deprecated term still in code",
         "grep finds 30 references to 'old name'. Schedule cleanup."),
        ("I", "No CI gate",
         "New class added without glossary update. Pre-commit hook + reviewer."),
        ("J", "Cross-BC term swap into event",
         "Internal naming leaked to Published Language. Keep Published Language stable."),
    ]
    for letter, name, why in patterns:
        print(f"  ANTI-PATTERN {letter} - {name}")
        print(f"    -> {why}")
    print()
    print("  PASS - 10 anti-patterns documented")


# =============================================================================
# RUN ALL
# =============================================================================

def main() -> int:
    demo_1_per_bc_glossary()
    demo_2_cross_bc_term_collision()
    demo_3_drift_detector_healthy()
    demo_4_drift_detector_drifting()
    demo_5_rename_impact_analysis()
    demo_6_migration_plan_5_phases()
    demo_7_glossary_rename_operation()
    demo_8_published_language_versioning_in_rename()
    demo_9_anti_patterns_showcase()

    print()
    print("=" * 76)
    print("  ALL 9 DEMOS PASS - Lesson 40 Ubiquitous Language verified")
    print("  PHASE DDD COMPLETE: Lessons 34-40 done (7 lessons)")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
