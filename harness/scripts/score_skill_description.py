#!/usr/bin/env python3
"""
Skill description format compliance scorer and dependency graph validator.

Scores SKILL.md descriptions on 5 structural criteria (deterministic, no LLM).
Also detects confusable skill pairs via Jaccard similarity and dependency cycles
via DFS. Walks harness/plugins/<plugin>/skills/<skill>/SKILL.md trees.

Note: This measures FORMAT COMPLIANCE (structure), not semantic effectiveness.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Degrade gracefully when yaml is absent — frontmatter parsed manually.
try:
    import yaml as _yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

try:
    from encoding_utils import configure_utf8_console, emit_json
    _ENCODING_UTILS = True
except ImportError:
    _ENCODING_UTILS = False

    def configure_utf8_console():  # type: ignore[misc]
        pass

    def emit_json(obj) -> None:  # type: ignore[misc]
        import json
        sys.stdout.write(json.dumps(obj, indent=2, ensure_ascii=False, default=str))
        sys.stdout.write("\n")
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Common action verbs that open well-structured skill descriptions.
ACTION_VERBS: frozenset[str] = frozenset({
    "add", "analyze", "answer", "apply", "automate",
    "build", "check", "configure", "create", "debug",
    "deploy", "design", "discover", "execute", "extract",
    "fix", "generate", "implement", "integrate", "manage",
    "monitor", "optimize", "orchestrate", "organize", "pack",
    "plan", "process", "research", "review", "run",
    "scan", "search", "set", "ship", "simplify",
    "stage", "style", "test", "track", "transform",
    "validate", "view", "visualize", "write",
})

# Trigger-phrase regexes.
_TRIGGER_RE = re.compile(r"\bUse\s+(for|when)\b", re.IGNORECASE)
_BROAD_FOR_RE = re.compile(r"\bfor\b.{8,}", re.IGNORECASE)

# Stop words excluded from Jaccard similarity.
_STOP_WORDS: frozenset[str] = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "for",
    "from", "has", "have", "if", "in", "is", "it", "not", "of", "on",
    "or", "so", "the", "to", "up", "use", "via", "vs", "was", "we",
    "when", "with", "you", "your",
})

# Template hint shown when a skill fails scoring.
TEMPLATE_HINT = (
    'Expected pattern: "{Action verb} {what}. '
    'Use for/when {2-3 use cases}. Supports {tech if relevant}."'
)

# Scoring weights (sum = 1.0).
W_LENGTH = 0.30
W_VERB = 0.10
W_TRIGGER = 0.25
W_USECASE = 0.20
W_BOUNDARY = 0.15

# Decision thresholds.
PASS_THRESHOLD = 0.6
CONFUSABLE_THRESHOLD = 0.80


# ---------------------------------------------------------------------------
# Score result dataclass
# ---------------------------------------------------------------------------

@dataclass
class FormatScore:
    """Result of scoring a single skill description."""

    skill_name: str
    description: str
    length_score: float = 0.0
    verb_score: float = 0.0
    trigger_score: float = 0.0
    usecase_score: float = 0.0
    boundary_score: float = 1.0  # default pass; caller may set to 0 if confusable
    issues: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        return (
            self.length_score * W_LENGTH
            + self.verb_score * W_VERB
            + self.trigger_score * W_TRIGGER
            + self.usecase_score * W_USECASE
            + self.boundary_score * W_BOUNDARY
        )

    @property
    def passed(self) -> bool:
        return self.total >= PASS_THRESHOLD

    def as_dict(self) -> dict:
        return {
            "skill_name": self.skill_name,
            "total": round(self.total, 4),
            "passed": self.passed,
            "length_score": self.length_score,
            "verb_score": self.verb_score,
            "trigger_score": self.trigger_score,
            "usecase_score": self.usecase_score,
            "boundary_score": self.boundary_score,
            "issues": self.issues,
        }


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------

def _score_length(desc: str) -> tuple[float, list[str]]:
    """Score description length. Optimal: 80-200 chars."""
    n = len(desc)
    issues: list[str] = []
    if n < 20:
        issues.append(f"Too short ({n} chars, min 20)")
        return 0.0, issues
    if n < 80:
        issues.append(f"Short ({n} chars, target 80-200)")
        return 0.5, issues
    if n <= 200:
        return 1.0, issues
    if n <= 300:
        issues.append(f"Long ({n} chars, target 80-200)")
        return 0.8, issues
    issues.append(f"Very long ({n} chars, max ~300)")
    return 0.5, issues


def _score_verb(desc: str) -> tuple[float, list[str]]:
    """Score whether description starts with an action verb."""
    first_word = desc.split()[0].lower().rstrip(".,;:!") if desc.strip() else ""
    if first_word in ACTION_VERBS:
        return 1.0, []
    # Some descriptions start with a modifier like "ALWAYS" before the verb.
    words = desc.split()
    if len(words) > 1 and words[1].lower().rstrip(".,;:!") in ACTION_VERBS:
        return 0.5, [f'Starts with "{words[0]}" not an action verb']
    return 0.0, [f'No action verb start (first word: "{first_word}")']


def _score_trigger(desc: str) -> tuple[float, list[str]]:
    """Score whether description contains a trigger/use-case phrase."""
    if _TRIGGER_RE.search(desc):
        return 1.0, []
    if _BROAD_FOR_RE.search(desc):
        return 0.7, ["Has 'for' context but missing explicit 'Use for/when'"]
    return 0.0, ["Missing trigger phrase ('Use for/when ...')"]


def _score_usecases(desc: str) -> tuple[float, list[str]]:
    """Score number of use cases (comma-separated items after trigger or first period)."""
    trigger_match = _TRIGGER_RE.search(desc)
    if trigger_match:
        after = desc[trigger_match.end():]
    else:
        dot = desc.find(".")
        after = desc[dot + 1:] if dot >= 0 else desc

    segments = [s.strip() for s in after.split(",") if s.strip()]
    n = len(segments)
    if n == 0:
        return 0.0, ["No use cases listed"]
    if n == 1:
        return 0.5, ["Only 1 use case (target 2-4)"]
    if n <= 4:
        return 1.0, []
    return 0.8, [f"{n} use cases (target 2-4, may be too many)"]


def score_description(name: str, description: str) -> FormatScore:
    """Score a skill description on 5 structural criteria. Deterministic, no LLM."""
    result = FormatScore(skill_name=name, description=description)
    result.length_score, length_issues = _score_length(description)
    result.verb_score, verb_issues = _score_verb(description)
    result.trigger_score, trigger_issues = _score_trigger(description)
    result.usecase_score, usecase_issues = _score_usecases(description)
    # boundary_score is set externally by check_confusable_pairs when needed.
    result.issues = length_issues + verb_issues + trigger_issues + usecase_issues
    return result


# ---------------------------------------------------------------------------
# Confusable pair detection (Jaccard)
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    """Tokenize text into lowercase words, excluding stop words."""
    return {
        w for w in re.findall(r"[a-z0-9]+", text.lower())
        if w not in _STOP_WORDS and len(w) > 1
    }


def check_confusable_pairs(skills: list[dict]) -> list[tuple[str, str, float]]:
    """Find skill pairs whose descriptions exceed the Jaccard similarity threshold.

    Uses word-token Jaccard index (stop words excluded).
    Returns list of (name_a, name_b, similarity).
    """
    pairs: list[tuple[str, str, float]] = []
    tokenized = [
        (str(s.get("name", "")), _tokenize(str(s.get("description", ""))))
        for s in skills
    ]
    for i in range(len(tokenized)):
        name_a, tokens_a = tokenized[i]
        if not tokens_a:
            continue
        for j in range(i + 1, len(tokenized)):
            name_b, tokens_b = tokenized[j]
            if not tokens_b:
                continue
            intersection = tokens_a & tokens_b
            union = tokens_a | tokens_b
            sim = len(intersection) / len(union) if union else 0.0
            if sim >= CONFUSABLE_THRESHOLD:
                pairs.append((name_a, name_b, sim))
    return pairs


# ---------------------------------------------------------------------------
# Dependency cycle detection (DFS)
# ---------------------------------------------------------------------------

def validate_dependency_graph(skills: list[dict]) -> list[str]:
    """Detect cycles in the skill dependency graph using iterative DFS.

    Reads the optional `requires` list from each skill dict.
    Returns list of error strings (empty list = no cycles).
    """
    graph: dict[str, list[str]] = {}
    for skill in skills:
        name = str(skill.get("name", ""))
        requires = skill.get("requires", [])
        if isinstance(requires, list) and requires:
            graph[name] = [str(r) for r in requires]

    if not graph:
        return []

    errors: list[str] = []
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n: WHITE for n in graph}

    # Iterative DFS avoids RecursionError on deep chains.
    for start in list(graph.keys()):
        if color.get(start, WHITE) != WHITE:
            continue
        stack: list[tuple[str, int]] = [(start, 0)]  # (node, neighbor_index)
        path: list[str] = []
        while stack:
            node, idx = stack.pop()
            if idx == 0:
                color[node] = GRAY
                path.append(node)
            neighbors = graph.get(node, [])
            if idx < len(neighbors):
                stack.append((node, idx + 1))
                neighbor = neighbors[idx]
                if neighbor not in color:
                    color[neighbor] = WHITE
                if color[neighbor] == GRAY:
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    errors.append(f"Cycle: {' -> '.join(cycle)}")
                elif color[neighbor] == WHITE:
                    stack.append((neighbor, 0))
            else:
                path.pop()
                color[node] = BLACK

    return errors


# ---------------------------------------------------------------------------
# Frontmatter parser (stdlib-only fallback)
# ---------------------------------------------------------------------------

def _parse_frontmatter(text: str) -> dict:
    """Extract YAML frontmatter from a SKILL.md string.

    Returns a dict with at least `name` and `description` keys.
    Tries PyYAML first; falls back to a minimal line-scanner if unavailable.
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fm_text = text[3:end].strip()

    if _YAML_AVAILABLE:
        try:
            return _yaml.safe_load(fm_text) or {}
        except Exception:
            pass

    # Minimal key: value scanner (handles simple single-line values only).
    result: dict = {}
    for line in fm_text.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


# ---------------------------------------------------------------------------
# Skills discovery
# ---------------------------------------------------------------------------

def discover_skills(plugins_root: str | Path) -> list[dict]:
    """Walk a plugins root dir and load all SKILL.md files.

    Expected layout:
        <plugins_root>/<plugin>/skills/<skill-name>/SKILL.md

    Also handles a flat layout where SKILL.md appears at any depth.
    """
    root = Path(plugins_root)
    skills: list[dict] = []
    for skill_md in sorted(root.rglob("SKILL.md")):
        try:
            text = skill_md.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = _parse_frontmatter(text)
        if not fm:
            continue
        name = str(fm.get("name", skill_md.parent.name))
        description = str(fm.get("description", ""))
        requires = fm.get("requires", [])
        if not isinstance(requires, list):
            requires = []
        skills.append({
            "name": name,
            "description": description,
            "requires": requires,
            "path": str(skill_md),
        })
    return skills


# ---------------------------------------------------------------------------
# Report printing
# ---------------------------------------------------------------------------

def print_format_compliance_report(
    scores: list[FormatScore],
    confusable: list[tuple[str, str, float]],
    cycles: list[str],
) -> None:
    """Print a human-readable format compliance report to stdout."""
    print("\n" + "=" * 70)
    print("FORMAT COMPLIANCE REPORT")
    print("(Structural format check — not semantic effectiveness)")
    print("=" * 70)

    sorted_scores = sorted(scores, key=lambda s: s.total)
    passed = sum(1 for s in scores if s.passed)
    failed = len(scores) - passed

    for s in sorted_scores:
        status = "[OK]" if s.passed else "[!!]"
        print(f"  {status} {s.total:.2f}  {s.skill_name}")
        if not s.passed and s.issues:
            for issue in s.issues[:3]:
                print(f"           {issue}")
            print(f"           {TEMPLATE_HINT}")

    print(f"\nSummary: {passed} passed, {failed} failed (threshold {PASS_THRESHOLD})")

    if confusable:
        print(f"\nConfusable Pairs ({len(confusable)}):")
        for name_a, name_b, sim in confusable:
            print(f"  [!] {name_a} <-> {name_b} (similarity {sim:.2f})")

    if cycles:
        print(f"\nDependency Cycles ({len(cycles)}):")
        for err in cycles:
            print(f"  [X] {err}")

    print("=" * 70)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    configure_utf8_console()

    parser = argparse.ArgumentParser(
        description="Score skill description format compliance across harness plugin dirs."
    )
    parser.add_argument(
        "plugins_root",
        help="Root directory to recurse for SKILL.md files (e.g. harness/plugins).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON report instead of human-readable text.",
    )
    args = parser.parse_args(argv)

    skills = discover_skills(args.plugins_root)

    scores: list[FormatScore] = [
        score_description(s["name"], s["description"]) for s in skills
    ]

    confusable = check_confusable_pairs(skills)

    # Mark confusable skills by lowering their boundary_score.
    confusable_names = {name for pair in confusable for name in pair[:2]}
    for sc in scores:
        if sc.skill_name in confusable_names:
            sc.boundary_score = 0.0
            sc.issues.append("Description too similar to another skill (confusable pair)")

    cycles = validate_dependency_graph(skills)

    if args.json:
        emit_json({
            "tool": "score_skill_description",
            "plugins_root": args.plugins_root,
            "skill_count": len(skills),
            "pass_threshold": PASS_THRESHOLD,
            "scores": [sc.as_dict() for sc in scores],
            "confusable_pairs": [
                {"skill_a": a, "skill_b": b, "similarity": round(sim, 4)}
                for a, b, sim in confusable
            ],
            "dependency_cycles": cycles,
            "summary": {
                "passed": sum(1 for sc in scores if sc.passed),
                "failed": sum(1 for sc in scores if not sc.passed),
            },
        })
    else:
        print_format_compliance_report(scores, confusable, cycles)

    return 0


if __name__ == "__main__":
    sys.exit(main())
