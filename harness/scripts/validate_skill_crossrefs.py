#!/usr/bin/env python3
"""
Validate skill cross-references and workflow-chain integrity.

Scans SKILL.md bodies across all harness plugin dirs for /hs: and
/hs-<group>: references, builds a directed graph, checks expected SDLC
workflow chains, and reports orphans / hubs / broken refs.

Usage:
  python3 validate_skill_crossrefs.py <plugins-root>          # audit mode
  python3 validate_skill_crossrefs.py <plugins-root> --json   # JSON output
  python3 validate_skill_crossrefs.py --self-test             # run self-tests
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

try:
    import yaml as _yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

# Optional: UTF-8 console normalisation (degrades silently if absent)
try:
    _SCRIPTS_DIR = Path(__file__).resolve().parent
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    from encoding_utils import configure_utf8_console
    configure_utf8_console()
except Exception:
    pass

# ── Constants ────────────────────────────────────────────────────────────────

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
CODE_FENCE_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)

# Match /hs:<skill> and /hs-<group>:<skill> — the full qualified name is captured.
# Examples: /hs:cook  /hs-think:brainstorm  /hs-mem:remember
SKILL_REF_RE = re.compile(r"/(hs(?:-[a-z0-9]+)?:[a-z0-9][\w-]*)")

SKIP_DIRS = frozenset({"_shared", "template-skill", "__pycache__",
                        "node_modules", ".venv"})

# Expected SDLC workflow chains.  Each consecutive pair must have an edge
# (in either direction) somewhere across the skill graph.
# Advisory only — a missing edge is reported but does not crash the tool.
EXPECTED_CHAINS = {
    "development":   ["hs:plan", "hs:cook", "hs:code-review", "hs:ship"],
    "bugfix":        ["hs:scout", "hs:debug", "hs:fix", "hs:code-review"],
    "investigation": ["hs:scout", "hs:debug", "hs-think:brainstorm"],
}


# ── Frontmatter parsing ──────────────────────────────────────────────────────

def _parse_frontmatter(content: str) -> dict:
    """Extract frontmatter dict from SKILL.md content."""
    m = FRONTMATTER_RE.match(content)
    if not m:
        return {}
    raw = m.group(1)
    if _HAS_YAML:
        try:
            return _yaml.safe_load(raw) or {}
        except Exception:
            return {}
    # Minimal fallback: extract name only
    nm = re.search(r"^name:\s*[\"']?(.+?)[\"']?\s*$", raw, re.M)
    return {"name": nm.group(1).strip() if nm else ""}


# ── Ref extraction ───────────────────────────────────────────────────────────

def _extract_body_refs(content: str, own_name: str) -> set[str]:
    """Extract qualified skill references from body text, excluding code fences.

    Returns a set of strings like 'hs:cook' or 'hs-think:brainstorm'.
    The skill's own name is excluded (no self-edges).
    """
    m = FRONTMATTER_RE.match(content)
    body = content[m.end():] if m else content
    # Strip code fences before matching to avoid false positives
    body = CODE_FENCE_RE.sub("", body)
    refs = set(SKILL_REF_RE.findall(body))
    refs.discard(own_name)
    return refs


# ── Scanning ─────────────────────────────────────────────────────────────────

def scan_all_skills(plugins_root: Path) -> dict[str, dict]:
    """Walk all plugin dirs under plugins_root and collect skill metadata.

    Returns a dict keyed by the skill's qualified name (from the name: field),
    e.g. ``{"hs:cook": {"name": "hs:cook", "body_refs": {...}, ...}}``.

    Plugin layout expected:
        <plugins_root>/<plugin>/skills/<skill-dir>/SKILL.md
    """
    skills: dict[str, dict] = {}

    for plugin_dir in sorted(plugins_root.iterdir()):
        if not plugin_dir.is_dir() or plugin_dir.name.startswith("."):
            continue
        skills_dir = plugin_dir / "skills"
        if not skills_dir.is_dir():
            continue
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            if skill_dir.name in SKIP_DIRS or skill_dir.name.startswith("."):
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            content = skill_file.read_text(encoding="utf-8", errors="replace")
            fm = _parse_frontmatter(content)
            name = (fm.get("name") or "").strip()
            if not name:
                # Fall back to plugin:dir-name form
                name = f"{plugin_dir.name}:{skill_dir.name}"
            body_refs = _extract_body_refs(content, name)
            requires = fm.get("requires") or []
            related = fm.get("related") or []
            if isinstance(requires, str):
                requires = [requires]
            if isinstance(related, str):
                related = [related]
            skills[name] = {
                "name": name,
                "body_refs": body_refs,
                "requires": requires,
                "related": related,
                "path": str(skill_file),
            }

    return skills


# ── Graph analysis ───────────────────────────────────────────────────────────

def build_reference_graph(skills: dict[str, dict]) -> dict:
    """Build directed graph from skill cross-references.

    Returns a dict with keys:
        edges      — {src_name: [dst_name, ...]}
        orphans    — [name, ...] (no inbound AND no outbound edges)
        hubs       — [(name, in_degree), ...] sorted descending
        broken     — [(src_name, ref), ...] ref is not a known skill name
        in_degree  — {name: count}
        out_degree — {name: count}
    """
    all_names = set(skills.keys())
    edges: dict[str, set] = defaultdict(set)
    in_degree: dict[str, int] = defaultdict(int)
    out_degree: dict[str, int] = defaultdict(int)

    for name, data in skills.items():
        for ref in data["body_refs"]:
            if ref in all_names and ref != name:
                edges[name].add(ref)
                out_degree[name] += 1
                in_degree[ref] += 1

    # Orphans: no inbound AND no outbound
    orphans = [n for n in all_names if in_degree[n] == 0 and out_degree[n] == 0]

    # Hubs: in_degree >= 3
    hubs = [(n, in_degree[n]) for n in all_names if in_degree[n] >= 3]
    hubs.sort(key=lambda x: -x[1])

    # Broken: references that point to an unknown skill name
    broken = []
    for name, data in skills.items():
        for ref in data["body_refs"]:
            if ref not in all_names:
                broken.append((name, ref))

    return {
        "edges": {k: sorted(v) for k, v in edges.items()},
        "orphans": sorted(orphans),
        "hubs": hubs,
        "broken": broken,
        "in_degree": dict(in_degree),
        "out_degree": dict(out_degree),
    }


def check_expected_workflows(graph: dict, skills: dict) -> list[dict]:
    """Check SDLC workflow chains for missing consecutive edges.

    An edge is considered present if either direction (a->b or b->a) exists.
    Returns a list of missing-edge dicts: {"chain": ..., "from": ..., "to": ...}.
    Advisory only — callers decide how to surface the result.
    """
    edges = graph["edges"]
    missing = []
    for chain_name, chain in EXPECTED_CHAINS.items():
        for i in range(len(chain) - 1):
            src, dst = chain[i], chain[i + 1]
            fwd = dst in edges.get(src, set())
            rev = src in edges.get(dst, set())
            if not fwd and not rev:
                missing.append({"chain": chain_name, "from": src, "to": dst})
    return missing


# ── Output ───────────────────────────────────────────────────────────────────

def print_report(skills: dict, graph: dict, missing: list[dict]) -> None:
    """Print human-readable audit report to stdout."""
    print(f"\n=== Skill Cross-Reference Audit ===")
    print(f"Total skills scanned: {len(skills)}")
    print(f"Skills with outward refs: {len(graph['edges'])}")
    print(f"Orphaned skills: {len(graph['orphans'])}")
    print(f"Hub skills: {len(graph['hubs'])}")
    print(f"Broken references: {len(graph['broken'])}")
    print(f"Missing workflow edges: {len(missing)}")

    if graph["hubs"]:
        print("\n--- Hub Skills (in_degree >= 3) ---")
        for name, count in graph["hubs"]:
            print(f"  {name}: {count} inbound refs")

    if missing:
        print("\n--- Missing Workflow Edges ---")
        for m in missing:
            print(f"  [{m['chain']}] {m['from']} -> {m['to']}")

    if graph["broken"]:
        print("\n--- Broken References ---")
        for src, ref in graph["broken"]:
            print(f"  {src} -> /{ref} (not found)")

    if graph["orphans"]:
        print(f"\n--- Orphaned Skills ({len(graph['orphans'])}) ---")
        for name in graph["orphans"]:
            print(f"  {name}")


# ── Self-tests ───────────────────────────────────────────────────────────────

def _run_self_tests() -> bool:
    """Run inline self-tests with temporary SKILL.md fixtures.

    Returns True if all tests pass.
    """
    passed = 0
    failed = 0

    def _assert(cond: bool, label: str) -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  [OK] {label}")
        else:
            failed += 1
            print(f"  [X]  {label}")

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)

        def _write(plugin: str, skill_dir: str, name: str, body: str) -> None:
            d = base / plugin / "skills" / skill_dir
            d.mkdir(parents=True, exist_ok=True)
            (d / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: test\nuser-invocable: true\n---\n\n{body}",
                encoding="utf-8",
            )

        _write("hs", "plan", "hs:plan",
               "After deciding, run /hs:cook to implement.\n")
        _write("hs", "cook", "hs:cook",
               "Call /hs-think:brainstorm for ideas then /hs:code-review.\n")
        _write("hs-think", "brainstorm", "hs-think:brainstorm",
               "Ideation only.\n```\n/hs:plan should not match\n```\n")
        _write("hs", "orphan", "hs:orphan",
               "Standalone skill.\n")
        _write("hs", "broken", "hs:broken",
               "See /hs-x:ghost for help.\nAlso /hs:cook is good.\n")

        skills = scan_all_skills(base)
        graph = build_reference_graph(skills)

        print("Self-tests:")

        # T1: Spine ref /hs:cook detected in plan body
        plan_refs = skills.get("hs:plan", {}).get("body_refs", set())
        _assert("hs:cook" in plan_refs, "T1: /hs:cook ref detected in plan body")

        # T2: Namespaced ref /hs-think:brainstorm detected in cook body
        cook_refs = skills.get("hs:cook", {}).get("body_refs", set())
        _assert("hs-think:brainstorm" in cook_refs,
                "T2: /hs-think:brainstorm ref detected in cook body")

        # T3: Orphan has no in/out edges
        _assert("hs:orphan" in graph["orphans"], "T3: Orphan detection")

        # T4: hs:cook is referenced by plan and broken -> in_degree >= 2
        cook_in = graph["in_degree"].get("hs:cook", 0)
        _assert(cook_in >= 2, f"T4: Hub-like (hs:cook in_degree={cook_in})")

        # T5: Missing chain edges exist (development chain incomplete)
        missing = check_expected_workflows(graph, skills)
        _assert(len(missing) > 0, "T5: Missing chain edges detected")

        # T6: Broken reference /hs-x:ghost detected
        broken_refs = [ref for _, ref in graph["broken"]]
        _assert("hs-x:ghost" in broken_refs, "T6: Broken ref /hs-x:ghost detected")

        # T7: Self-reference excluded (brainstorm has no self-edge)
        bt_refs = skills.get("hs-think:brainstorm", {}).get("body_refs", set())
        _assert("hs-think:brainstorm" not in bt_refs,
                "T7: Self-reference excluded")

        # T8: Code-fence ref in brainstorm body excluded
        _assert("hs:plan" not in bt_refs,
                "T8: Code-fence ref excluded")

        n_tests = 8
        print(f"\nResults: {passed}/{n_tests} passed, {failed}/{n_tests} failed")
        return failed == 0


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    if "--self-test" in sys.argv:
        ok = _run_self_tests()
        sys.exit(0 if ok else 1)

    if len(sys.argv) < 2:
        print("Usage: validate_skill_crossrefs.py <plugins-root> [--json]",
              file=sys.stderr)
        sys.exit(2)

    plugins_root = Path(sys.argv[1])
    if not plugins_root.is_dir():
        print(f"Error: {plugins_root} is not a directory", file=sys.stderr)
        sys.exit(2)

    use_json = "--json" in sys.argv

    skills = scan_all_skills(plugins_root)
    graph = build_reference_graph(skills)
    missing = check_expected_workflows(graph, skills)

    if use_json:
        result = {
            "total_skills": len(skills),
            "edges": graph["edges"],
            "orphans": graph["orphans"],
            "hubs": [{"name": n, "in_degree": c} for n, c in graph["hubs"]],
            "broken": [{"from": s, "ref": r} for s, r in graph["broken"]],
            "missing_workflow_edges": missing,
        }
        print(json.dumps(result, indent=2))
    else:
        print_report(skills, graph, missing)

    # Non-zero exit only when workflow chains have gaps (advisory signal)
    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
