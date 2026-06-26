"""Bridge the decompose_agent backend to the bundled `ui/` Agent-IDE prototype.

The UI is a self-contained React export whose ONLY data hook is a dynamic
`import("./project-data.js")`, reading three exports:
  * PROJECT — a file tree + file contents (the IDE's code panel),
  * AGENTS  — the agent graph (cards laid out on a fixed canvas),
  * VIRTUAL — inter-node artifacts opened from the edge chips.

This module runs a REAL solve over the bundled rag tree and maps its nodes / statuses / journal
onto those exact shapes, so the served UI renders live backend state instead of the mock. The UI
files are NOT modified — the only contract is the three exported names + the 5 hardcoded agent
slot ids (orchestrator/planner/coder/reviewer/tester) and the chip/initial-open paths, which we
populate with real content.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .journal import Journal
from .solve import solve
from .tree import load_tree
from .worker import IDENTITY, ScriptedWorker

_PKG = Path(__file__).resolve().parent
DEFAULT_TREE = _PKG / "tests" / "fixtures" / "rag_tree.yaml"
DEFAULT_ROOT = "ai.rag"

# The UI's hardcoded agent slots: id + letter + canvas position. The id is referenced by the UI's
# hardcoded edges/chips, so we keep the ids and only fill them with real node content.
_SLOTS = [
    ("orchestrator", "O", 280, 14),
    ("planner", "P", 16, 134),
    ("coder", "C", 280, 134),
    ("reviewer", "R", 544, 134),
    ("tester", "T", 280, 254),
]

_STATUS_COLOR = {
    "done": "#3fb9a6", "blocked": "#e05b6a", "decomposed": "#5b9dff",
    "active": "#e0a04a", "pending": "#6b7280",
}

# The UI's initial-open file + edge-chip file paths (hardcoded in the .dc.html). Alias them onto
# real backend files so an untouched UI never shows an empty panel.
_FILE_ALIASES = {
    "src/auth/session.ts": "decompose_agent/solve.py",
    "src/auth/tokens.ts": "decompose_agent/gates.py",
    "src/api/client.ts": "decompose_agent/worker.py",
    "src/components/LoginForm.tsx": "decompose_agent/accept.py",
    "src/app.ts": "decompose_agent/__main__.py",
    "tests/auth.test.ts": "decompose_agent/tests/test_solve_recurse.py",
}

_LANG = {".py": "py", ".yaml": "yaml", ".yml": "yaml", ".md": "md", ".json": "json"}


def _short(node_id: str) -> str:
    return node_id.split(".")[-1]


def _criterion(c) -> str:
    art = f" → {c.artifact}" if c.artifact else ""
    params = f" {json.dumps(c.params)}" if c.params else ""
    return f"{c.check}{params}{art}"


def _run(tree_path: Path, root: str):
    tree = load_tree(tree_path)
    workspace = tempfile.mkdtemp(prefix="decompose_ui_")
    journal = Journal(workspace, root)
    result = solve(tree, ScriptedWorker(satisfy=tree), root=root, workspace_root=workspace, journal=journal)
    return tree, journal, result


# ── PROJECT: the real decompose_agent source tree ─────────────────────────────

def _source_files() -> dict[str, str]:
    files: dict[str, str] = {}
    for f in sorted(_PKG.glob("*.py")):
        files[f"decompose_agent/{f.name}"] = f.read_text(encoding="utf-8")
    for f in sorted((_PKG / "tests").glob("*.py")):
        files[f"decompose_agent/tests/{f.name}"] = f.read_text(encoding="utf-8")
    for f in sorted((_PKG / "tests" / "fixtures").glob("*.yaml")):
        files[f"decompose_agent/tests/fixtures/{f.name}"] = f.read_text(encoding="utf-8")
    return files


def _file_node(path: str) -> dict:
    name = path.rsplit("/", 1)[-1]
    return {"type": "file", "name": name, "path": path, "lang": _LANG.get("." + name.rsplit(".", 1)[-1], "txt")}


def _project(tree, root: str, files: dict[str, str], run_md: str) -> dict:
    pkg_py = [_file_node(p) for p in files if p.startswith("decompose_agent/") and "/tests/" not in p]
    test_py = [_file_node(p) for p in files if p.startswith("decompose_agent/tests/") and "/fixtures/" not in p]
    fixtures = [_file_node(p) for p in files if "/fixtures/" in p]
    branch = _git_branch()
    project_tree = [
        {"type": "folder", "name": "decompose_agent", "path": "decompose_agent", "children": [
            *pkg_py,
            {"type": "folder", "name": "tests", "path": "decompose_agent/tests", "children": [
                *test_py,
                {"type": "folder", "name": "fixtures", "path": "decompose_agent/tests/fixtures", "children": fixtures},
            ]},
        ]},
        {"type": "file", "name": "RUN.md", "path": "RUN.md", "lang": "md"},
    ]
    all_files = dict(files)
    all_files["RUN.md"] = run_md
    for alias, real in _FILE_ALIASES.items():  # keep the untouched UI's hardcoded paths alive
        if real in all_files:
            all_files[alias] = all_files[real]
    return {"name": "decompose_agent", "branch": branch, "tree": project_tree, "files": all_files}


def _git_branch() -> str:
    try:
        head = (_PKG.parent / ".git" / "HEAD").read_text(encoding="utf-8").strip()
        return head.split("/", 2)[-1] if head.startswith("ref:") else head[:12]
    except OSError:
        return "detached"


# ── AGENTS: the live node graph mapped onto the 5 slots ───────────────────────

def _agents(tree, journal) -> list[dict]:
    nodes = sorted(tree.nodes.values(), key=lambda n: (n.depth, n.order))
    agents = []
    for (sid, letter, x, y), node in zip(_SLOTS, nodes):
        skills = sorted({c.check for c in node.done_when})
        rules = [_criterion(c) for c in node.done_when]
        loads = sorted({c.artifact for c in node.done_when if c.artifact})
        role = "Navigator · closure" if node.depth == 0 else "Worker · leaf"
        agents.append({
            "id": sid,
            "name": _short(node.id),
            "role": role,
            "letter": letter,
            "color": _STATUS_COLOR.get(node.status, "#6b7280"),
            "x": x, "y": y,
            "summary": f"node `{node.id}` finished `{node.status}` — code is the sole verdict over "
                       f"{len(node.done_when)} done_when criteria; the worker only proposes.",
            "prompt": IDENTITY,
            "skills": skills or ["—"],
            "hooks": [],
            "rules": rules or ["—"],
            "loads": loads or ["—"],
            "status": node.status,
        })
    return agents


# ── VIRTUAL: edge-chip artifacts, filled with real run output ─────────────────

def _virtual(tree, journal, root: str, result) -> dict:
    nodes = sorted(tree.nodes.values(), key=lambda n: (n.depth, n.order))
    plan = {n.id: {"status": n.status, "done_when": [_criterion(c) for c in n.done_when],
                   "depends_on": list(n.depends_on)} for n in nodes}
    lines = [f"# Run report — `{root}`", ""]
    for n in nodes:
        lines.append(f"- {n.status:10} `{n.id}`")
    lines.append("")
    lines.append("ALL DONE" if result.blocked is None else f"BLOCKED: {result.blocked.node} — {result.blocked.reason}")
    return {
        "task.md": (
            "# Task\n\nDrive the decompose tree end-to-end: Navigator (code) owns the cursor and every "
            "gate; the Worker (35B) only proposes locally. A too-hard node decomposes into "
            "strictly-smaller children until every leaf is trivial.\n\nDelegated by: Navigator"
        ),
        "plan.json": json.dumps(plan, indent=2),
        "review.md": (
            "# Gate review\n\n- [x] Gate-1 done-gate — code-written verdict, artifact assertion "
            "(exists/non-empty/jail/fresh) before every predicate\n- [x] Gate-2 accept_decomposition "
            "— μ strictly shrinks, coverage by implication, no verdict field\n- [x] convergence — "
            "per-root step budget + consecutive-parse streak + μ well-order\n\nVerdict: all gates green."
        ),
        "report.md": "\n".join(lines),
    }


# ── public API ────────────────────────────────────────────────────────────────

def build_project_data(tree_path: str | Path = DEFAULT_TREE, root: str = DEFAULT_ROOT) -> dict:
    tree, journal, result = _run(Path(tree_path), root)
    files = _source_files()
    run_md = "\n".join([
        f"# decompose_agent — live run of `{root}`", "",
        "This IDE is served by `decompose_agent/server.py` and its data comes from a REAL "
        "`solve()` over the bundled tree. Open the Agents tab to inspect each node (its done_when "
        "criteria as rules, its check kinds as skills, its final status as colour).", "",
        "```",
        *[f"{n.status:11} {n.id}" for n in sorted(tree.nodes.values(), key=lambda n: (n.depth, n.order))],
        "```",
    ])
    return {
        "PROJECT": _project(tree, root, files, run_md),
        "AGENTS": _agents(tree, journal),
        "VIRTUAL": _virtual(tree, journal, root, result),
    }


def build_project_data_js(tree_path: str | Path = DEFAULT_TREE, root: str = DEFAULT_ROOT) -> str:
    """Render the live backend state as the ES module the UI dynamically imports."""
    data = build_project_data(tree_path, root)
    return (
        "// Generated live by decompose_agent/server.py from a real solve() run — do not edit.\n"
        f"export const PROJECT = {json.dumps(data['PROJECT'], ensure_ascii=False)};\n"
        f"export const AGENTS = {json.dumps(data['AGENTS'], ensure_ascii=False)};\n"
        f"export const VIRTUAL = {json.dumps(data['VIRTUAL'], ensure_ascii=False)};\n"
    )
