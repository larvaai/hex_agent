#!/usr/bin/env python3
"""standards_graph — load the standards tree under <root>/harness/standards/ and
build the directed graph rule -> rule-group -> STD-area -> ARCH-goal -> vision.

The standards-domain mirror of the product graph builder. Structural-only:
parses frontmatter, resolves explicit id links, reserves the two layering-seam
fields on every node, and exposes a downstream() query. NO judgment — it never
decides whether a standard is good, only how the tree connects.

Layout (flat): one areas/STD-<AREA>.md per area; that file declares its
rule-groups and rules as frontmatter lists (the same expansion shape product
goals use inside brd.md). vision.md / STACK.md / charter.md are singletons at
the tree root. The standards tree is per-clone INPUT — the builder consumes it,
never invents standards.

Every node carries two reserved layering-seam fields a future cross-tree
resolver fills in: `applies_standards` (an inheritance ref, left None) and
`standards_compliance` (a compliance map, left {}). This builder never populates
or reads them.

CLI:
    standards_graph.py --root <project-dir> [--snapshot] [--downstream <ID>]
        --snapshot writes a JSON snapshot under harness/standards/.snapshots/
                   in addition to printing graph JSON to stdout.
        Always exits 0; emits graph JSON to stdout.
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import graph_core
from encoding_utils import configure_utf8_console, emit_json
from frontmatter_parser import parse_file

configure_utf8_console()


# Singleton/top-level artifacts globbed directly under harness/standards/; areas
# are flat under areas/. Rule-groups and rules are NOT separate files — they are
# expanded from frontmatter lists inside each area file.
ARTIFACT_GLOBS = {
    "stack": ["STACK.md"],
    "vision": ["vision.md"],
    "charter": ["charter.md"],
    "std_area": ["areas/*.md"],
}

# The single authoritative expected-child-type map for the hierarchy. The
# unaddressed-parent / orphan checks key off this; one home means adding a
# hierarchy level edits one place. Passed as a parameter into
# graph_core.matching_child_counts.
CHILD_TYPE_FOR_PARENT = {
    "arch_goal": "std_area",
    "std_area": "rule_group",
    "rule_group": "rule",
}

# Parent-scoped id grammar — the single authoritative home. The template
# generator imports these, never re-encodes them. Parent-scoped + globally
# unique without a central allocator.
ID_PATTERN_BY_TYPE = {
    "stack": re.compile(r"^STACK$"),
    "vision": re.compile(r"^VISION$"),
    "arch_goal": re.compile(r"^ARCH-G[0-9]+$"),
    "std_area": re.compile(r"^STD-[A-Z][A-Z0-9-]{0,15}$"),
    "rule_group": re.compile(r"^STD-[A-Z][A-Z0-9-]{0,15}-RG[0-9]+$"),
    "rule": re.compile(r"^STD-[A-Z][A-Z0-9-]{0,15}-RG[0-9]+-R[0-9]+$"),
}


def standards_dir(root: Path) -> Path:
    """The standards-tree root: <root>/harness/standards/ (the fs_guard zone)."""
    return Path(root) / "harness" / "standards"


def load_artifacts(std_dir: Path) -> List[Dict[str, Any]]:
    """Walk harness/standards/ and parse every artifact. Includes parse_error entries."""
    artifacts: List[Dict[str, Any]] = []
    for art_type, globs in ARTIFACT_GLOBS.items():
        for pattern in globs:
            for path in sorted(std_dir.glob(pattern)):
                parsed = parse_file(path)
                parsed["__type_hint"] = art_type
                artifacts.append(parsed)
    return artifacts


def _title_from_h1(body: str, node_id: Optional[str]) -> str:
    """Pull a human title from the artifact's first H1 (mirror of the product
    builder's helper). Strip a trailing ` — …<id>` qualifier templates append."""
    if not body:
        return ""
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("# "):
            h = line[2:].strip()
            if node_id and "—" in h:
                head, _, tail = h.rpartition("—")
                if node_id in tail:
                    h = head.strip() or h
            return h
    return ""


def _node_type(art: Dict[str, Any]) -> Optional[str]:
    """Resolve an artifact's type: a malformed (non-str) `type:` coerces to None
    so it falls back to the directory-derived hint instead of poisoning a key
    test downstream."""
    raw = art.get("frontmatter", {}).get("type")
    return (raw if isinstance(raw, str) else None) or art.get("__type_hint")


def _seam_fields() -> Dict[str, Any]:
    """The two reserved layering-seam fields a future resolver fills. This
    builder sets them to a constant empty value and never populates them."""
    return {"applies_standards": None, "standards_compliance": {}}


def _node_from_singleton(fm: Dict[str, Any], file_rel: str, node_type: str,
                         body: str) -> Dict[str, Any]:
    nid = graph_core._scalar_id(fm.get("id"))
    body = body or ""
    return {
        "id": nid,
        "type": node_type,
        "title": fm.get("title") or fm.get("name") or _title_from_h1(body, nid) or "",
        "status": fm.get("status"),
        "owner": fm.get("owner"),
        "version": fm.get("version"),
        "body_hash": graph_core._content_fingerprint([body]),
        "content_hash": graph_core._content_fingerprint([body]),
        "metrics": fm.get("metrics") or [],
        "depends_on": graph_core._as_id_list(fm.get("depends_on")),
        "file": file_rel,
        **_seam_fields(),
    }


def _node_from_goal(goal: Dict[str, Any], parent_file: str) -> Dict[str, Any]:
    """Expand one charter goal into an arch_goal node (mirror of product goal
    expansion). `metrics` is preserved verbatim so the gate / template can
    enforce 'metric required' — the builder itself never judges."""
    nid = graph_core._scalar_id(goal.get("id"))
    return {
        "id": nid,
        "type": "arch_goal",
        "title": goal.get("title") or "",
        "status": goal.get("status"),
        "owner": goal.get("owner"),
        "version": goal.get("version"),
        "metrics": goal.get("metrics") or [],
        "depends_on": graph_core._as_id_list(goal.get("depends_on")),
        "body_hash": None,
        "content_hash": graph_core._content_fingerprint([
            "arch_goal", goal.get("title"), goal.get("status"),
            goal.get("metrics"), goal.get("owner"),
        ]),
        "file": parent_file,
        **_seam_fields(),
    }


def _node_from_rule_group(rg: Dict[str, Any], std_area_id: str,
                          parent_file: str) -> Dict[str, Any]:
    nid = graph_core._scalar_id(rg.get("id"))
    return {
        "id": nid,
        "type": "rule_group",
        "title": rg.get("title") or "",
        "status": rg.get("status"),
        "owner": rg.get("owner"),
        "version": rg.get("version"),
        "metrics": rg.get("metrics") or [],
        "std_area": graph_core._scalar_link(std_area_id),
        "depends_on": graph_core._as_id_list(rg.get("depends_on")),
        "body_hash": None,
        "content_hash": graph_core._content_fingerprint([
            "rule_group", rg.get("title"), rg.get("status"), rg.get("owner"),
        ]),
        "file": parent_file,
        **_seam_fields(),
    }


def _node_from_rule(rule: Dict[str, Any], rule_group_id: str,
                    parent_file: str) -> Dict[str, Any]:
    nid = graph_core._scalar_id(rule.get("id"))
    raw_checks = rule.get("compliance_checks")
    checks = [x for x in raw_checks if x not in (None, "")] \
        if isinstance(raw_checks, list) else []
    return {
        "id": nid,
        "type": "rule",
        "title": rule.get("title") or "",
        "status": rule.get("status"),
        "owner": rule.get("owner"),
        "version": rule.get("version"),
        "metrics": rule.get("metrics") or [],
        "compliance_checks": checks,
        "rule_group": graph_core._scalar_link(rule_group_id),
        "depends_on": graph_core._as_id_list(rule.get("depends_on")),
        "body_hash": None,
        # content_hash folds the rule's compliance checks (the standards
        # equivalent of acceptance_criteria) so a checks-only edit is detectable.
        "content_hash": graph_core._content_fingerprint([
            "rule", rule.get("title"), rule.get("status"), checks,
        ]),
        "file": parent_file,
        **_seam_fields(),
    }


def build_nodes(artifacts: List[Dict[str, Any]], std_dir: Path) -> List[Dict[str, Any]]:
    """Convert parsed artifacts to graph nodes. Charter goals expand to arch_goal
    nodes; std-area rule_groups + rules expand from the area's frontmatter."""
    nodes: List[Dict[str, Any]] = []
    for art in artifacts:
        if not art["ok"]:
            continue
        fm = art["frontmatter"]
        try:
            rel = Path(art["file"]).resolve().relative_to(std_dir.resolve()).as_posix()
        except ValueError:
            # A symlinked artifact resolving OUTSIDE the standards tree has no
            # tree-relative id. Demote it to a parse_error (collected by
            # _assemble_graph) rather than crash the never-raises contract.
            art["ok"] = False
            art["error"] = "resolves outside the standards tree: %s" % art["file"]
            continue
        node_type = _node_type(art)
        body = art.get("body") or ""

        if node_type == "charter":
            for g in fm.get("goals") or []:
                if isinstance(g, dict):
                    nodes.append(_node_from_goal(g, parent_file=rel))
        elif node_type == "std_area":
            area_id = graph_core._scalar_id(fm.get("id"))
            nodes.append({
                "id": area_id,
                "type": "std_area",
                "title": fm.get("title") or _title_from_h1(body, area_id) or "",
                "status": fm.get("status"),
                "owner": fm.get("owner"),
                "version": fm.get("version"),
                "metrics": fm.get("metrics") or [],
                # arch_goals: list of charter-goal ids this area addresses.
                "arch_goals": _as_str_list(fm.get("arch_goals")),
                "depends_on": graph_core._as_id_list(fm.get("depends_on")),
                "body_hash": graph_core._content_fingerprint([body]),
                "content_hash": graph_core._content_fingerprint([body]),
                "file": rel,
                **_seam_fields(),
            })
            for rg in fm.get("rule_groups") or []:
                if not isinstance(rg, dict):
                    continue
                nodes.append(_node_from_rule_group(rg, area_id, rel))
                rg_id = graph_core._scalar_id(rg.get("id"))
                for rule in rg.get("rules") or []:
                    if isinstance(rule, dict):
                        nodes.append(_node_from_rule(rule, rg_id, rel))
        elif node_type in ("stack", "vision"):
            nodes.append(_node_from_singleton(fm, rel, node_type, body))
    return nodes


def _as_str_list(v: Any) -> List[str]:
    """Coerce an `arch_goals` reference list to a list of strs, preserving order.

    A bare string is NOT char-split; a non-list yields []. Order is preserved
    (unlike depends_on which sorts) so multi-goal addressing renders under each
    goal in declared order, matching the product brd_goals edge order."""
    if not isinstance(v, list):
        return []
    return [x for x in v if isinstance(x, str)]


def build_edges(nodes: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """For each child node, emit edges to its parent(s) by id. arch_goal and
    vision/stack are roots with no outbound edge (same convention as product
    goals)."""
    edges: List[Dict[str, str]] = []
    for n in nodes:
        ntype = n["type"]
        if ntype == "rule" and n.get("rule_group"):
            edges.append({"from": n["id"], "to": n["rule_group"], "kind": "rule_group"})
        elif ntype == "rule_group" and n.get("std_area"):
            edges.append({"from": n["id"], "to": n["std_area"], "kind": "std_area"})
        elif ntype == "std_area":
            goals = n.get("arch_goals")
            for g in (goals if isinstance(goals, list) else []):
                if isinstance(g, str):
                    edges.append({"from": n["id"], "to": g, "kind": "arch_goal"})
    return edges


def _assemble_graph(artifacts: List[Dict[str, Any]], std_dir: Path,
                    root: Path) -> Dict[str, Any]:
    nodes = build_nodes(artifacts, std_dir)
    edges = build_edges(nodes)
    parse_errors = [{"file": a["file"], "error": a["error"]}
                    for a in artifacts if not a["ok"]]
    return {
        "version": "1.0",
        "generated_at": graph_core._now(),
        "nodes": nodes,
        "edges": edges,
        "parse_errors": parse_errors,
        "root_path": str(root),
    }


def _missing_dir_graph(root: Path) -> Dict[str, Any]:
    return {
        "version": "1.0",
        "generated_at": graph_core._now(),
        "nodes": [],
        "edges": [],
        "parse_errors": [],
        "missing_standards_dir": True,
        "root_path": str(root),
    }


def build_graph(root: Path) -> Dict[str, Any]:
    """Top-level: parse the standards tree, build, return graph JSON. Always
    returns a well-formed dict; never raises on a malformed tree."""
    std_dir = standards_dir(root)
    if not std_dir.exists():
        return _missing_dir_graph(root)
    artifacts = load_artifacts(std_dir)
    return _assemble_graph(artifacts, std_dir, root)


def downstream(graph: Dict[str, Any], node_id: str):
    """Set of node ids reachable as descendants of node_id."""
    return graph_core._closure(graph_core.children_of(graph), node_id)


def write_snapshot(graph: Dict[str, Any], root: Path) -> Path:
    """Write a content-hashed snapshot under harness/standards/.snapshots/."""
    snap_dir = standards_dir(root) / ".snapshots"
    return graph_core.write_snapshot(graph, snap_dir)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="project root (contains harness/standards/)")
    ap.add_argument("--snapshot", action="store_true", help="also write a snapshot file")
    ap.add_argument("--downstream", default=None,
                    help="print downstream set for the given ID and exit")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    graph = build_graph(root)

    if args.downstream:
        ids = sorted(downstream(graph, args.downstream))
        emit_json({"node": args.downstream, "downstream": ids})
        return 0

    if args.snapshot:
        snap = write_snapshot(graph, root)
        graph["__snapshot_path"] = str(snap.relative_to(root))

    emit_json(graph)
    return 0


if __name__ == "__main__":
    sys.exit(main())
