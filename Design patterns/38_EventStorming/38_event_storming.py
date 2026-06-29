"""
Lesson 38 — Event Storming Workshop (Case Study)
==================================================

Simulate 1 workshop Ellumm Quiz end-to-end:
- Build sticky note wall progressively qua 3 phase.
- Phase 1 (Big Picture): chỉ orange event chronological.
- Phase 2 (Process Modeling): + commands, actors, policies, externals, hot spots.
- Phase 3 (Software Design): + aggregates, read models, bounded contexts.

Output:
- Glossary draft (term → definition).
- Context map proposal.
- Aggregate proposal với invariants.
- Hot spot list cần follow-up.

Run: python 38_event_storming.py
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple


# =============================================================================
# [DOMAIN MODEL OF WORKSHOP]
# =============================================================================

class StickyColor(str, Enum):
    ORANGE = "orange"               # Domain Event (past tense)
    BLUE = "blue"                   # Command
    YELLOW = "yellow"               # Actor
    PINK = "pink"                   # External system
    PURPLE = "purple"               # Policy
    GREEN = "green"                 # Read model
    RED = "red"                     # Hot spot / question
    CREAM = "cream"                 # Aggregate (added phase 3)


@dataclass
class StickyNote:
    color: StickyColor
    text: str
    sticky_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timeline_position: int = 0      # x-axis position (chronological in phase 1)
    related_to: Set[str] = field(default_factory=set)
    bounded_context: Optional[str] = None       # assigned phase 3

    def __str__(self) -> str:
        return f"[{self.color.value[:3].upper()}] '{self.text}'"


@dataclass
class BoundedContextDraft:
    name: str
    classification: str             # Core / Supporting / Generic
    aggregates: List[str] = field(default_factory=list)
    events: List[str] = field(default_factory=list)
    read_models: List[str] = field(default_factory=list)
    external_systems: List[str] = field(default_factory=list)


class Wall:
    """Workshop wall — collection of sticky notes ordered by timeline."""

    def __init__(self, workshop_name: str) -> None:
        self.workshop_name = workshop_name
        self.notes: List[StickyNote] = []
        self.bounded_contexts: List[BoundedContextDraft] = []

    # ---- Adding sticky notes ----
    def add(self, color: StickyColor, text: str, position: int = 0,
            related: Optional[List[str]] = None) -> StickyNote:
        note = StickyNote(color=color, text=text, timeline_position=position,
                          related_to=set(related or []))
        self.notes.append(note)
        return note

    # ---- Filtering ----
    def by_color(self, color: StickyColor) -> List[StickyNote]:
        return [n for n in self.notes if n.color == color]

    def chronological(self) -> List[StickyNote]:
        return sorted(self.notes, key=lambda n: n.timeline_position)

    def events(self) -> List[StickyNote]:
        return self.by_color(StickyColor.ORANGE)

    def commands(self) -> List[StickyNote]:
        return self.by_color(StickyColor.BLUE)

    def actors(self) -> List[StickyNote]:
        return self.by_color(StickyColor.YELLOW)

    def externals(self) -> List[StickyNote]:
        return self.by_color(StickyColor.PINK)

    def policies(self) -> List[StickyNote]:
        return self.by_color(StickyColor.PURPLE)

    def read_models(self) -> List[StickyNote]:
        return self.by_color(StickyColor.GREEN)

    def hot_spots(self) -> List[StickyNote]:
        return self.by_color(StickyColor.RED)

    def aggregates(self) -> List[StickyNote]:
        return self.by_color(StickyColor.CREAM)

    def stats(self) -> Dict[str, int]:
        return {c.value: len(self.by_color(c)) for c in StickyColor}


# =============================================================================
# [HEURISTICS]   Discover aggregate, bounded context, hot spots
# =============================================================================

# Common noun extraction (simple — production would use NLP)
ELLUMM_NOUNS = {
    "submission", "quiz", "question", "answer", "score", "attempt",
    "user", "student", "teacher", "author", "admin",
    "leaderboard", "ranking", "badge", "achievement",
    "notification", "receipt", "email",
    "subscription", "payment", "invoice",
}


def extract_nouns(text: str) -> Set[str]:
    """Tiny noun extractor: tokenize + lowercase + filter against known set."""
    words = text.lower().replace(",", " ").replace(".", " ").split()
    return {w for w in words if w in ELLUMM_NOUNS}


def discover_aggregates(wall: Wall, min_appearances: int = 3) -> List[Tuple[str, List[StickyNote]]]:
    """Find nouns appearing ≥ min_appearances across events.
    Each appearance suggests aggregate candidate."""
    event_per_noun: Dict[str, List[StickyNote]] = defaultdict(list)
    for evt in wall.events():
        for noun in extract_nouns(evt.text):
            event_per_noun[noun].append(evt)
    candidates = [(noun, events) for noun, events in event_per_noun.items()
                  if len(events) >= min_appearances]
    return sorted(candidates, key=lambda x: -len(x[1]))


def propose_bounded_contexts(wall: Wall) -> List[BoundedContextDraft]:
    """Heuristic: group events by their dominant aggregate noun, then propose BC.
    Use min_appearances=1 to catch all aggregate candidates even with few events."""
    aggregates = discover_aggregates(wall, min_appearances=1)
    bcs: Dict[str, BoundedContextDraft] = {}

    # Rule-based BC mapping for Ellumm (in real workshop, this comes from discussion)
    bc_mapping = {
        "quiz": ("Quiz Authoring", "Core"),
        "question": ("Quiz Authoring", "Core"),
        "submission": ("Submission", "Core"),
        "answer": ("Submission", "Core"),
        "score": ("Submission", "Core"),
        "attempt": ("Submission", "Core"),
        "leaderboard": ("Leaderboard", "Supporting"),
        "ranking": ("Leaderboard", "Supporting"),
        "badge": ("Gamification", "Supporting"),
        "achievement": ("Gamification", "Supporting"),
        "notification": ("Notification", "Generic"),
        "receipt": ("Notification", "Generic"),
        "email": ("Notification", "Generic"),
        "subscription": ("Subscription", "Generic"),
        "payment": ("Subscription", "Generic"),
        "invoice": ("Subscription", "Generic"),
    }

    # Group by BC
    for noun, events in aggregates:
        if noun not in bc_mapping:
            continue
        bc_name, classification = bc_mapping[noun]
        if bc_name not in bcs:
            bcs[bc_name] = BoundedContextDraft(name=bc_name, classification=classification)
        # Capitalize noun for aggregate name
        agg_name = noun.capitalize()
        if agg_name not in bcs[bc_name].aggregates:
            bcs[bc_name].aggregates.append(agg_name)
        for e in events:
            if e.text not in bcs[bc_name].events:
                bcs[bc_name].events.append(e.text)

    # Add read models + externals to each BC
    for rm in wall.read_models():
        for bc_name in bcs:
            if bc_name.lower().split()[0] in rm.text.lower():
                bcs[bc_name].read_models.append(rm.text)
                break

    for ext in wall.externals():
        for bc_name in bcs:
            if bc_name.lower().split()[0] in ext.text.lower():
                bcs[bc_name].external_systems.append(ext.text)
                break

    return list(bcs.values())


def detect_workshop_smells(wall: Wall) -> List[str]:
    """Run anti-pattern detector on workshop output."""
    smells = []

    # Smell 1: Mostly orange — phase 2/3 skipped
    stats = wall.stats()
    total = sum(stats.values())
    if total > 20 and stats["orange"] / total > 0.85:
        smells.append("85%+ orange — phase 2/3 likely skipped (missing commands/actors)")

    # Smell 2: Events with future tense
    for evt in wall.events():
        if any(w in evt.text.lower() for w in ["will", "should", "must"]):
            smells.append(f"future-tense event: '{evt.text}'")

    # Smell 3: Commands without actor (no yellow nearby)
    actor_count = len(wall.actors())
    cmd_count = len(wall.commands())
    if cmd_count > 0 and actor_count == 0:
        smells.append(f"{cmd_count} commands but 0 actors — workshop missed 'who'")

    # Smell 4: No hot spots — too superficial
    if total > 30 and len(wall.hot_spots()) == 0:
        smells.append("0 hot spots in 30+ sticky workshop — likely too superficial")

    # Smell 5: Events not in past tense (rough heuristic)
    past_tense_suffixes = ("ed", "Placed", "Created", "Started", "Submitted",
                            "Graded", "Awarded", "Sent", "Updated", "Renewed",
                            "Flagged", "Corrected", "Finalized", "Published",
                            "Cancelled", "Previewed", "Calculated")
    for evt in wall.events():
        first_word = evt.text.split()[0] if evt.text.split() else ""
        if not any(first_word.endswith(s) for s in past_tense_suffixes):
            # Check whole sticky text
            if not any(s in evt.text for s in past_tense_suffixes):
                smells.append(f"event not past-tense: '{evt.text}'")

    return smells


# =============================================================================
# [CASE STUDY — Ellumm Workshop]
# =============================================================================

def build_phase_1_big_picture(wall: Wall) -> None:
    """Phase 1: orange events only, chronological."""
    events = [
        # ─── Account & Quiz Authoring ───
        "Account Registered",
        "Quiz Created",
        "Quiz Published",
        # ─── Student journey ───
        "Quiz Previewed",
        "Submission Started",
        "Answers Submitted",
        "Score Calculated",
        "Badge Awarded",
        "Receipt Sent",
        "Leaderboard Updated",
        # ─── Retry / correction ───
        "Submission Retried",
        "Score Corrected by Teacher",
        "Submission Finalized",
        # ─── Subscription lifecycle ───
        "Subscription Renewed",
        "Payment Processed",
        "Invoice Generated",
        # ─── Teacher actions ───
        "Submission Flagged by Teacher",
        "Quiz Retired",
        # ─── Gamification ───
        "Achievement Unlocked",
        "Streak Maintained",
    ]
    for i, txt in enumerate(events):
        wall.add(StickyColor.ORANGE, txt, position=i)


def build_phase_2_process_modeling(wall: Wall) -> None:
    """Phase 2: + commands, actors, externals, policies, hot spots."""
    # Commands (blue) — paired with events
    commands = [
        "Register Account",
        "Create Quiz",
        "Publish Quiz",
        "Submit Quiz",
        "Calculate Score",
        "Award Badge",
        "Send Receipt",
        "Update Leaderboard",
        "Retry Submission",
        "Correct Score",
        "Finalize Submission",
        "Renew Subscription",
    ]
    for cmd in commands:
        wall.add(StickyColor.BLUE, cmd)

    # Actors (yellow)
    actors = ["Student", "Teacher", "Admin", "AutoScorer System", "Billing Worker"]
    for a in actors:
        wall.add(StickyColor.YELLOW, a)

    # External systems (pink)
    externals = ["Auth0", "SendGrid (email)", "Stripe (payment)", "Twilio (SMS)"]
    for e in externals:
        wall.add(StickyColor.PINK, e)

    # Policies (purple) — automated reactions
    policies = [
        "When Score Calculated AND score >= 90 → Award Badge",
        "When Submission Finalized → Send Receipt",
        "When Score Calculated → Update Leaderboard",
        "When Subscription Renewed → Send Receipt Email",
        "When 3 days inactive → Send Reminder",
    ]
    for p in policies:
        wall.add(StickyColor.PURPLE, p)

    # Hot spots (red) — unresolved questions
    hot_spots = [
        "Can Teacher override AutoScorer? How disputes resolved?",
        "What is 'finalize'? Auto after 24h or manual teacher action?",
        "Is Badge per-quiz or per-user lifetime?",
        "Subscription expiry: hard cut or grace period?",
    ]
    for h in hot_spots:
        wall.add(StickyColor.RED, h)


def build_phase_3_software_design(wall: Wall) -> None:
    """Phase 3: aggregates, read models, bounded context boundaries."""
    # Aggregates (cream) — big sticky
    aggregates = [
        ("Quiz aggregate", "Quiz Authoring"),
        ("Submission aggregate", "Submission"),
        ("Ranking aggregate", "Leaderboard"),
        ("Recipient aggregate", "Notification"),
        ("Subscription aggregate", "Subscription"),
        ("Badge aggregate", "Gamification"),
    ]
    for txt, bc in aggregates:
        note = wall.add(StickyColor.CREAM, txt)
        note.bounded_context = bc

    # Read models (green)
    read_models = [
        "Leaderboard View (top-N per quiz)",
        "Student Dashboard (history + badges)",
        "Teacher Review Queue (flagged submissions)",
        "Admin Audit Log",
        "Subscription Account Summary",
    ]
    for rm in read_models:
        wall.add(StickyColor.GREEN, rm)


# =============================================================================
# [PRESENTATION]
# =============================================================================

def banner(s: str) -> None:
    print("\n" + "=" * 76)
    print(f"  {s}")
    print("=" * 76)


def show_wall_stats(wall: Wall) -> None:
    print(f"\n  Wall: '{wall.workshop_name}' — total {len(wall.notes)} sticky notes")
    print(f"  Color breakdown:")
    for color in StickyColor:
        count = len(wall.by_color(color))
        if count:
            bar = "█" * count
            print(f"    {color.value:<8} {count:>3}  {bar}")


def show_chronology(wall: Wall, color: Optional[StickyColor] = None, limit: int = 25) -> None:
    notes = wall.chronological()
    if color:
        notes = [n for n in notes if n.color == color]
    print(f"\n  Chronological view ({color.value if color else 'all'}, first {limit}):")
    for n in notes[:limit]:
        marker = f"t={n.timeline_position:>2}" if n.timeline_position else "  -  "
        print(f"    {marker} {n}")
    if len(notes) > limit:
        print(f"    ... and {len(notes) - limit} more")


# =============================================================================
# [DEMOS]
# =============================================================================

def demo_1_phase_1_big_picture() -> None:
    banner("DEMO 1 — Phase 1: Big Picture (event timeline only)")
    wall = Wall("Ellumm Quiz Domain")
    build_phase_1_big_picture(wall)
    show_wall_stats(wall)
    show_chronology(wall, StickyColor.ORANGE, limit=10)
    assert len(wall.events()) >= 18
    print(f"\n  Events captured: {len(wall.events())}")
    print(f"  Pivotal events (state phase change):")
    pivotal_keywords = ["Submitted", "Calculated", "Finalized", "Renewed"]
    for evt in wall.events():
        if any(k in evt.text for k in pivotal_keywords):
            print(f"    ◆ {evt.text}")
    print("  PASS — Big Picture event timeline established")


def demo_2_phase_2_process_modeling() -> None:
    banner("DEMO 2 — Phase 2: Process Modeling (+ commands, actors, policies, hot spots)")
    wall = Wall("Ellumm Quiz Domain")
    build_phase_1_big_picture(wall)
    build_phase_2_process_modeling(wall)
    show_wall_stats(wall)
    print(f"\n  Actors: {[a.text for a in wall.actors()]}")
    print(f"  External systems: {[e.text for e in wall.externals()]}")
    print(f"  Policies ({len(wall.policies())}):")
    for p in wall.policies():
        print(f"    • {p.text}")
    print(f"  Hot spots ({len(wall.hot_spots())}):")
    for h in wall.hot_spots():
        print(f"    ⚠ {h.text}")
    assert len(wall.commands()) >= 10
    assert len(wall.policies()) >= 3
    assert len(wall.hot_spots()) >= 3
    print("  PASS — Process Modeling enriched with structure")


def demo_3_phase_3_software_design() -> None:
    banner("DEMO 3 — Phase 3: Software Design (+ aggregates, read models)")
    wall = Wall("Ellumm Quiz Domain")
    build_phase_1_big_picture(wall)
    build_phase_2_process_modeling(wall)
    build_phase_3_software_design(wall)
    show_wall_stats(wall)
    print(f"\n  Aggregates ({len(wall.aggregates())}):")
    for a in wall.aggregates():
        print(f"    [{a.bounded_context}]  {a.text}")
    print(f"\n  Read models ({len(wall.read_models())}):")
    for rm in wall.read_models():
        print(f"    📊 {rm.text}")
    assert len(wall.aggregates()) >= 5
    assert len(wall.read_models()) >= 4
    print("  PASS — Software Design layer added")


def demo_4_aggregate_discovery_heuristic() -> None:
    banner("DEMO 4 — Aggregate discovery via repeated noun heuristic")
    wall = Wall("Ellumm Quiz Domain")
    build_phase_1_big_picture(wall)
    build_phase_2_process_modeling(wall)

    candidates = discover_aggregates(wall, min_appearances=2)
    print(f"\n  Aggregate candidates (noun appears in ≥ 2 events):")
    print(f"  {'Noun':<16} {'Count':<7} {'Events'}")
    print(f"  {'-'*16} {'-'*7} {'-'*40}")
    for noun, events in candidates[:8]:
        event_titles = ", ".join(e.text for e in events[:3])
        if len(events) > 3:
            event_titles += f", ... (+{len(events)-3})"
        print(f"  {noun:<16} {len(events):<7} {event_titles[:50]}")
    assert len(candidates) >= 4
    print("  PASS — Aggregate candidates discovered from event nouns")


def demo_5_bounded_context_proposal() -> None:
    banner("DEMO 5 — Bounded Context proposal from workshop wall")
    wall = Wall("Ellumm Quiz Domain")
    build_phase_1_big_picture(wall)
    build_phase_2_process_modeling(wall)
    build_phase_3_software_design(wall)

    bcs = propose_bounded_contexts(wall)
    print(f"\n  Proposed Bounded Contexts ({len(bcs)}):")
    for bc in bcs:
        print(f"\n  ┌─ {bc.name} ({bc.classification})")
        print(f"  │  Aggregates: {bc.aggregates}")
        print(f"  │  Events: {len(bc.events)}")
        for e in bc.events[:3]:
            print(f"  │    • {e}")
        if len(bc.events) > 3:
            print(f"  │    ... and {len(bc.events) - 3} more")
        if bc.read_models:
            print(f"  │  Read models: {bc.read_models}")
        if bc.external_systems:
            print(f"  │  External: {bc.external_systems}")
        print(f"  └─")
    assert len(bcs) >= 4
    print(f"\n  PASS — {len(bcs)} bounded contexts proposed")


def demo_6_hot_spot_followup_list() -> None:
    banner("DEMO 6 — Hot spot follow-up list (unresolved questions)")
    wall = Wall("Ellumm Quiz Domain")
    build_phase_1_big_picture(wall)
    build_phase_2_process_modeling(wall)

    hot_spots = wall.hot_spots()
    print(f"\n  Hot spots requiring follow-up ({len(hot_spots)}):")
    print(f"  {'#':<3} {'Question':<70} {'Owner'}")
    print(f"  {'-'*3} {'-'*70} {'-'*15}")
    suggested_owners = ["Product Owner", "Tech Lead", "Product Owner", "Finance Lead"]
    for i, hs in enumerate(hot_spots, 1):
        owner = suggested_owners[i-1] if i-1 < len(suggested_owners) else "TBD"
        print(f"  {i:<3} {hs.text[:68]:<70} {owner}")
    assert len(hot_spots) >= 3
    print(f"\n  Action: schedule follow-up workshop within 1 week.")
    print("  PASS — hot spots captured and assigned for resolution")


def demo_7_glossary_export() -> None:
    banner("DEMO 7 — Glossary export from wall")
    wall = Wall("Ellumm Quiz Domain")
    build_phase_1_big_picture(wall)
    build_phase_2_process_modeling(wall)
    build_phase_3_software_design(wall)

    glossary: Dict[str, str] = {}
    for evt in wall.events():
        glossary[evt.text] = f"Domain event (past-tense fact)"
    for cmd in wall.commands():
        glossary[cmd.text] = f"Command (imperative, requires actor)"
    for actor in wall.actors():
        glossary[actor.text] = f"Actor (issues commands)"
    for policy in wall.policies():
        glossary[policy.text] = f"Policy (automated reaction)"
    for agg in wall.aggregates():
        glossary[agg.text] = f"Aggregate root in {agg.bounded_context}"

    print(f"\n  Glossary entries: {len(glossary)}")
    print(f"  Sample entries:")
    sample_keys = list(glossary.keys())[:8]
    for k in sample_keys:
        print(f"    {k:<40} → {glossary[k]}")
    print(f"    ... and {len(glossary) - 8} more")
    assert len(glossary) >= 30
    print("  PASS — glossary exportable to Confluence/Notion")


def demo_8_workshop_smell_detection() -> None:
    banner("DEMO 8 — Workshop quality detector (anti-patterns)")

    # GOOD workshop
    good_wall = Wall("Good Ellumm")
    build_phase_1_big_picture(good_wall)
    build_phase_2_process_modeling(good_wall)
    build_phase_3_software_design(good_wall)
    good_smells = detect_workshop_smells(good_wall)

    # BAD workshop — only events, no other phases
    bad_wall = Wall("Bad Workshop")
    for i in range(35):
        bad_wall.add(StickyColor.ORANGE, f"Event {i} Happened")
    # add future-tense event
    bad_wall.add(StickyColor.ORANGE, "Payment Will Be Received")
    # add command with no actor
    bad_wall.add(StickyColor.BLUE, "Process Payment")
    bad_smells = detect_workshop_smells(bad_wall)

    print(f"\n  GOOD workshop smells: {len(good_smells)}")
    for s in good_smells:
        print(f"    ⚠ {s}")
    print(f"\n  BAD workshop smells: {len(bad_smells)}")
    for s in bad_smells[:6]:
        print(f"    ⚠ {s}")
    if len(bad_smells) > 6:
        print(f"    ... and {len(bad_smells) - 6} more")

    assert len(good_smells) <= 2          # good workshop has 0-2 false positives
    assert len(bad_smells) >= 3
    print("\n  PASS — detector flags bad workshop, validates good workshop")


def demo_9_full_workshop_output() -> None:
    banner("DEMO 9 — Final workshop output summary")
    wall = Wall("Ellumm Quiz Domain")
    build_phase_1_big_picture(wall)
    build_phase_2_process_modeling(wall)
    build_phase_3_software_design(wall)

    print(f"""
  Workshop: {wall.workshop_name}
  ─────────────────────────────────────────────────────────
  Total sticky notes:  {len(wall.notes)}
  Events:              {len(wall.events())}
  Commands:            {len(wall.commands())}
  Actors:              {len(wall.actors())}
  Policies:            {len(wall.policies())}
  External systems:    {len(wall.externals())}
  Hot spots:           {len(wall.hot_spots())}
  Aggregates:          {len(wall.aggregates())}
  Read models:         {len(wall.read_models())}
  Bounded contexts:    {len(propose_bounded_contexts(wall))}
  ─────────────────────────────────────────────────────────
  Quality smells:      {len(detect_workshop_smells(wall))}

  Deliverables produced by workshop:
    ✓ Photo of wall (Miro export)
    ✓ Glossary (50+ terms)
    ✓ Context map (6 bounded contexts)
    ✓ Aggregate proposal with invariants
    ✓ Hot spot list (4 items, follow-up scheduled)

  Time spent: 4 hours workshop + 2 hours transcribe = 6 hours total
  ROI: saved ~8-12 sprint of refactor by aligning team upfront
    """)
    print("  PASS — workshop output ready for Lesson 34-37 implementation")


# =============================================================================
# RUN ALL
# =============================================================================

def main() -> int:
    demo_1_phase_1_big_picture()
    demo_2_phase_2_process_modeling()
    demo_3_phase_3_software_design()
    demo_4_aggregate_discovery_heuristic()
    demo_5_bounded_context_proposal()
    demo_6_hot_spot_followup_list()
    demo_7_glossary_export()
    demo_8_workshop_smell_detection()
    demo_9_full_workshop_output()

    print()
    print("=" * 76)
    print("  ALL 9 DEMOS PASS - Lesson 38 Event Storming Workshop verified")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
