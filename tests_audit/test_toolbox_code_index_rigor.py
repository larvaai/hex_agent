"""Rigor for the read-only code index: AST(Python)+regex(JS/TS) symbol/reference/import indexing.

Complements tests/test_code_index.py (happy path) by pinning the *error and boundary* branches that
file leaves uncovered (80% baseline): the JS/TS regex indexer in full (_index_js_like, the biggest
gap), the path-jail escape envelopes, _clamp coercion, syntax-error tolerance, MAX_RESULTS/max_files
truncation, find_symbol/find_references clamp + early-return, dependency-graph dedup/skip, plus
property invariants on AST-derived symbols. The subject only imports core.schemas + safety.sandbox +
stdlib; the conftest AUTOUSE fixture gives every test a fresh AGENT_WORKSPACE_DIR, so workspace_dir()
already points at an isolated tmp dir. We create code files UNDER workspace_dir() (parents first).

Any genuine robustness gap is exposed via strict-less xfail with a file:line citation — never by
loosening an assertion to make a bug "pass".
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core.schemas import ToolRequest
from safety.sandbox import workspace_dir
from toolbox.code_index import (
    MAX_RESULTS,
    CodeDependencyGraph,
    CodeFindReferences,
    CodeFindSymbol,
    CodeIndex,
    _clamp,
    _code_files,
    _is_excluded,
    _rel,
)


def _req(_tool: str, **args) -> ToolRequest:
    return ToolRequest(name=_tool, args=args)


def _ws() -> Path:
    """Workspace root (already a fresh isolated tmp dir via the autouse conftest fixture)."""
    ws = workspace_dir()
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _write(rel: str, text: str) -> Path:
    """Write a code file UNDER the workspace, creating parent dirs first."""
    path = _ws() / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _symbols(result: dict, name: str) -> list[dict]:
    return [s for s in result["symbols"] if s["name"] == name]


# --------------------------------------------------------------------------------------
# code_index — Python AST: classes, methods, async, nested, imports, errors
# --------------------------------------------------------------------------------------


@pytest.mark.audit
def test_python_class_function_async_and_method_types():
    """A module-level function is 'function', an async def 'async_function', a def inside a class is
    'method', and a nested class -> method gets a dotted name. Exact names + linenos asserted."""
    src = (
        "class Outer:\n"            # line 1
        "    def m(self):\n"        # line 2 -> method 'Outer.m'
        "        pass\n"
        "    async def am(self):\n"  # line 4 -> method 'Outer.am' (class wins over async)
        "        pass\n"
        "    class Inner:\n"         # line 6 -> class 'Outer.Inner'
        "        def deep(self):\n"  # line 7 -> method 'Outer.Inner.deep'
        "            pass\n"
        "\n"
        "def top():\n"              # line 10 -> function 'top'
        "    pass\n"
        "\n"
        "async def atop():\n"       # line 13 -> async_function 'atop'
        "    pass\n"
    )
    _write("m.py", src)
    result = CodeIndex().execute(_req("code_index", path="m.py"))
    assert result["ok"] is True
    by_name = {s["name"]: s for s in result["symbols"]}
    assert by_name["Outer"]["type"] == "class" and by_name["Outer"]["lineno"] == 1
    assert by_name["Outer.m"]["type"] == "method" and by_name["Outer.m"]["lineno"] == 2
    # async method: class context overrides the async fallback type -> 'method' (code_index.py:91)
    assert by_name["Outer.am"]["type"] == "method" and by_name["Outer.am"]["lineno"] == 4
    assert by_name["Outer.Inner"]["type"] == "class" and by_name["Outer.Inner"]["lineno"] == 6
    assert by_name["Outer.Inner.deep"]["type"] == "method"
    assert by_name["top"]["type"] == "function" and by_name["top"]["lineno"] == 10
    # module-level async def -> 'async_function' (code_index.py:88, _visit_function fallback)
    assert by_name["atop"]["type"] == "async_function" and by_name["atop"]["lineno"] == 13
    # Every symbol carries a sane line span and the workspace-relative file.
    for s in result["symbols"]:
        assert s["lineno"] is not None and s["end_lineno"] is not None
        assert s["lineno"] <= s["end_lineno"]
        assert s["file"] == "m.py"


@pytest.mark.audit
def test_python_import_vs_import_from_with_relative_levels():
    """`import a, b.c` yields two 'import' rows (one per alias); `from .pkg import x, y` yields one
    'from_import' with module, names list, and level>0; a bare `from . import z` has module ''."""
    src = (
        "import os\n"                       # line 1 -> import os
        "import a.b, c\n"                   # line 2 -> import a.b ; import c
        "from .pkg import x, y\n"           # line 3 -> from_import module 'pkg' level 1
        "from ..deep import z\n"            # line 4 -> from_import module 'deep' level 2
        "from . import sibling\n"           # line 5 -> from_import module '' level 1
        "from pkg2 import thing\n"          # line 6 -> from_import module 'pkg2' level 0
    )
    _write("imp.py", src)
    result = CodeIndex().execute(_req("code_index", path="imp.py"))
    assert result["ok"] is True
    imports = result["imports"]
    plain = [i for i in imports if i["type"] == "import"]
    assert {i["module"] for i in plain} == {"os", "a.b", "c"}
    froms = {i["module"] or "<dot>": i for i in imports if i["type"] == "from_import"}
    assert froms["pkg"]["names"] == ["x", "y"] and froms["pkg"]["level"] == 1
    assert froms["deep"]["level"] == 2
    assert froms["<dot>"]["module"] == "" and froms["<dot>"]["level"] == 1
    assert froms["pkg2"]["level"] == 0
    # import-row lineno is preserved.
    assert {i["lineno"] for i in plain} == {1, 2}


@pytest.mark.audit
def test_python_syntax_error_lands_in_errors_but_index_still_ok():
    """A file that does not parse -> an entry in result['errors'] with type 'syntax_error', and the
    overall index still returns ok=True (code_index.py:169-170). A sibling clean file still indexes."""
    _write("broken.py", "def oops(:\n    pass\n")
    _write("good.py", "def fine():\n    return 1\n")
    result = CodeIndex().execute(_req("code_index", path="."))
    assert result["ok"] is True
    errs = result["errors"]
    assert any(e["type"] == "syntax_error" and e["file"] == "broken.py" for e in errs)
    # The clean sibling was still indexed despite the broken file.
    assert _symbols(result, "fine"), "clean file must still be indexed"


# --------------------------------------------------------------------------------------
# code_index — JS/TS regex indexer (_index_js_like) — the biggest coverage gap (131-142)
# --------------------------------------------------------------------------------------


@pytest.mark.audit
@pytest.mark.parametrize("ext", [".js", ".jsx", ".ts", ".tsx"])
def test_js_like_indexes_class_function_const_arrow_and_import(ext):
    """For every JS/TS extension: detect class, function, export-prefixed forms, const-arrow, and
    `import ... from '...'`. Assert EXACT symbol names + linenos and the import module string."""
    src = (
        "import { foo } from './foo';\n"        # line 1 -> import module './foo'
        "import bar from 'bar-pkg';\n"           # line 2 -> import module 'bar-pkg'
        "export class Widget {}\n"               # line 3 -> class Widget
        "class Plain {}\n"                        # line 4 -> class Plain
        "export function exported() {}\n"        # line 5 -> function exported
        "async function af() {}\n"                # line 6 -> function af
        "export const arrow = (a, b) => a + b;\n"  # line 7 -> function arrow
        "const asyncArrow = async () => 1;\n"     # line 8 -> function asyncArrow
        "let lateArrow = x => x;\n"               # line 9 -> function lateArrow
    )
    _write("comp" + ext, src)
    result = CodeIndex().execute(_req("code_index", path="comp" + ext))
    assert result["ok"] is True
    by_name = {s["name"]: s for s in result["symbols"]}
    assert by_name["Widget"] == {"type": "class", "name": "Widget", "file": "comp" + ext, "lineno": 3}
    assert by_name["Plain"]["type"] == "class" and by_name["Plain"]["lineno"] == 4
    assert by_name["exported"]["type"] == "function" and by_name["exported"]["lineno"] == 5
    assert by_name["af"]["type"] == "function" and by_name["af"]["lineno"] == 6
    # const-arrow forms (export const / const async / let single-param) all map to 'function'.
    assert by_name["arrow"]["type"] == "function" and by_name["arrow"]["lineno"] == 7
    assert by_name["asyncArrow"]["type"] == "function" and by_name["asyncArrow"]["lineno"] == 8
    assert by_name["lateArrow"]["type"] == "function" and by_name["lateArrow"]["lineno"] == 9
    # imports: exact module strings + linenos.
    imp = {i["module"]: i for i in result["imports"]}
    assert imp["./foo"]["lineno"] == 1 and imp["./foo"]["type"] == "import"
    assert imp["bar-pkg"]["lineno"] == 2


@pytest.mark.audit
def test_js_like_first_matching_regex_wins_per_line():
    """Per line the indexer breaks after the first regex match (code_index.py:138), so a line that is
    both a class and (hypothetically) something else yields exactly one symbol — no duplicates."""
    _write("one.ts", "export class Solo {}\n")
    result = CodeIndex().execute(_req("code_index", path="one.ts"))
    assert [s["name"] for s in result["symbols"]] == ["Solo"]
    assert result["symbols_count"] == 1


@pytest.mark.audit
def test_js_like_does_not_parse_python_constructs():
    """A .ts file uses the regex path, not AST: a Python `def` line is NOT a JS symbol. Guards against
    the dispatcher (_index_file) misrouting a non-.py suffix to the AST indexer (code_index.py:146-148)."""
    _write("nojs.ts", "def python_only():\n    pass\n")
    result = CodeIndex().execute(_req("code_index", path="nojs.ts"))
    assert result["ok"] is True
    assert result["symbols"] == []


# --------------------------------------------------------------------------------------
# code_index — sandbox escapes + excluded dirs + single-file / non-code roots (_code_files)
# --------------------------------------------------------------------------------------


@pytest.mark.audit
@pytest.mark.security
@pytest.mark.parametrize("bad_path", ["../etc", "../../../../etc/passwd", "/etc/passwd", "..\\esc", "C:/Windows"])
def test_index_path_escape_is_clean_failure(bad_path):
    """A path escaping the workspace -> ok=False with an error string, never a traceback
    (code_index.py:193-194 SandboxError branch). Covers POSIX traversal, absolute, and Windows syntax."""
    result = CodeIndex().execute(_req("code_index", path=bad_path))
    assert result["ok"] is False
    assert isinstance(result["error"], str) and result["error"]
    assert "symbols" not in result


@pytest.mark.audit
@pytest.mark.security
@pytest.mark.parametrize("excluded", [".git", "node_modules", "__pycache__", "var"])
def test_index_skips_excluded_directories(excluded):
    """Code under an EXCLUDED_DIRS subtree is never indexed; a sibling in a normal dir is
    (code_index.py:56 _is_excluded filter). Proves the exclusion is by path-part, not extension."""
    _write(excluded + "/hidden.py", "def secret_fn():\n    pass\n")
    _write("src/visible.py", "def visible_fn():\n    pass\n")
    result = CodeIndex().execute(_req("code_index", path="."))
    names = {s["name"] for s in result["symbols"]}
    assert "visible_fn" in names
    assert "secret_fn" not in names


@pytest.mark.audit
def test_index_skips_non_code_files_in_a_directory():
    """rglob hits non-code files (.txt/.md); only CODE_EXTENSIONS are indexed (code_index.py:56)."""
    _write("notes.txt", "def not_code():\n    pass\n")
    _write("readme.md", "# heading\n")
    _write("real.py", "def real():\n    pass\n")
    result = CodeIndex().execute(_req("code_index", path="."))
    assert result["files_count"] == 1
    assert {s["name"] for s in result["symbols"]} == {"real"}


@pytest.mark.audit
def test_index_single_non_code_file_root_yields_no_files():
    """_code_files(root, ...) on a single NON-code file -> empty file list, not truncated
    (code_index.py:50-51 single-file branch with the extension guard failing)."""
    target = _write("plain.txt", "hello\n")
    files, truncated = _code_files(target, 300)
    assert files == [] and truncated is False
    result = CodeIndex().execute(_req("code_index", path="plain.txt"))
    assert result["ok"] is True and result["files_count"] == 0


@pytest.mark.audit
def test_index_single_code_file_root_is_indexed():
    """The single-file branch happy side: a lone .py file root is indexed directly (code_index.py:50-51)."""
    target = _write("solo.py", "def solo():\n    pass\n")
    files, truncated = _code_files(target, 300)
    assert files == [target] and truncated is False


@pytest.mark.audit
def test_index_excluded_single_file_root_is_skipped():
    """A single-file root that itself sits in an excluded dir is rejected by the extension+exclusion
    guard in the is_file() branch (code_index.py:50)."""
    target = _write("node_modules/lib.js", "export class X {}\n")
    files, truncated = _code_files(target, 300)
    assert files == [] and truncated is False


# --------------------------------------------------------------------------------------
# _rel / _is_excluded — paths OUTSIDE the workspace (ValueError branches 36-37, 43-44)
# --------------------------------------------------------------------------------------


@pytest.mark.audit
def test_rel_outside_workspace_returns_raw_string():
    """_rel on a path that is NOT under the workspace -> relative_to raises ValueError, so the raw
    string is returned unchanged (code_index.py:36-37)."""
    outside = Path("/etc/hosts")
    assert _rel(outside) == str(outside)


@pytest.mark.audit
@pytest.mark.security
def test_is_excluded_outside_workspace_is_treated_as_excluded():
    """_is_excluded on a path outside the workspace -> ValueError branch returns True (fail-closed,
    code_index.py:43-44). A path the resolver wouldn't allow is never treated as indexable."""
    assert _is_excluded(Path("/etc/passwd")) is True


@pytest.mark.audit
def test_rel_inside_workspace_uses_forward_slashes():
    """Inside the workspace, _rel yields a forward-slash POSIX-style relative path (the happy side
    of 36-37) — nested components are joined with '/'."""
    p = _write("a/b/c.py", "x = 1\n")
    assert _rel(p) == "a/b/c.py"


# --------------------------------------------------------------------------------------
# max_files truncation + MAX_RESULTS cap (boundaries)
# --------------------------------------------------------------------------------------


@pytest.mark.audit
def test_max_files_truncation_sets_truncated_true():
    """When the directory holds more code files than max_files, _code_files stops early and
    truncated=True (code_index.py:54-55). The reported files_count equals the clamp."""
    for i in range(6):
        _write("f" + str(i) + ".py", "x = 1\n")
    result = CodeIndex().execute(_req("code_index", path=".", max_files=3))
    assert result["truncated"] is True
    assert result["files_count"] == 3


@pytest.mark.audit
def test_symbols_and_imports_capped_at_max_results():
    """A file with > MAX_RESULTS symbols/imports is truncated to MAX_RESULTS in the envelope
    (code_index.py:195-196). symbols_count reflects the pre-cap total."""
    n = MAX_RESULTS + 25
    lines = "".join("import mod" + str(i) + "\n" for i in range(n)) + "".join("def fn" + str(i) + "(): pass\n" for i in range(n))
    _write("big.py", lines)
    result = CodeIndex().execute(_req("code_index", path="big.py"))
    assert len(result["symbols"]) == MAX_RESULTS
    assert len(result["imports"]) == MAX_RESULTS
    # The pre-cap counts know the real totals.
    assert result["symbols_count"] == n and result["imports_count"] == n


# --------------------------------------------------------------------------------------
# _clamp — coercion of None / non-int / negative / huge (154-155)
# --------------------------------------------------------------------------------------


@pytest.mark.audit
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, 50),        # TypeError -> default
        ("x", 50),         # ValueError -> default
        ([], 50),          # TypeError (int([]) raises) -> default
        (-7, 1),           # below lo -> clamped up to lo
        (0, 1),            # below lo -> lo
        (10**9, 100),      # above hi -> clamped down to hi
        (37, 37),          # in range -> unchanged
        ("42", 42),        # numeric string -> coerced
        (3.9, 3),          # float truncates toward zero via int()
    ],
)
def test_clamp_coercion_matrix(value, expected):
    """_clamp(value, lo=1, hi=100, default=50): non-int/None -> default; out-of-range -> clamp."""
    assert _clamp(value, 1, 100, 50) == expected


@pytest.mark.audit
def test_index_max_files_garbage_falls_back_to_default():
    """A non-numeric max_files is clamped to the 300 default rather than crashing (code_index.py:190,
    via _clamp 154-155). Indexing a small tree still succeeds."""
    _write("a.py", "def a(): pass\n")
    result = CodeIndex().execute(_req("code_index", path=".", max_files="not-a-number"))
    assert result["ok"] is True and result["files_count"] == 1


# --------------------------------------------------------------------------------------
# code_find_symbol — case-insensitive substring, empty name, clamp, escape
# --------------------------------------------------------------------------------------


@pytest.mark.audit
def test_find_symbol_case_insensitive_substring():
    """The query is lowercased and matched as a substring against each symbol name (code_index.py:214)."""
    _write("s.py", "class HttpClient:\n    def Connect(self):\n        pass\n\ndef helper(): pass\n")
    result = CodeFindSymbol().execute(_req("code_find_symbol", name="CLIENT", path="s.py"))
    assert result["ok"] is True
    names = {m["name"] for m in result["matches"]}
    assert "HttpClient" in names
    # 'client' substring does not match 'helper' or the method 'Connect'.
    assert "helper" not in names
    assert result["count"] == len(result["matches"])
    # The echoed name preserves the caller's original casing (code_index.py:215).
    assert result["name"] == "CLIENT"


@pytest.mark.audit
@pytest.mark.parametrize("empty", ["", None])
def test_find_symbol_empty_name_is_error(empty):
    """An empty/absent name -> {'ok': False, 'error': 'name is required'} (code_index.py:205-206).
    None stringifies to '' before the truthiness gate, so it is rejected too."""
    args = {} if empty is None else {"name": empty}
    result = CodeFindSymbol().execute(ToolRequest(name="code_find_symbol", args={**args, "path": "."}))
    assert result == {"ok": False, "error": "name is required"}


@pytest.mark.audit
def test_find_symbol_max_results_clamped():
    """max_results clamps the match list (code_index.py:209,214). 10 matching symbols, cap 4 -> 4."""
    _write("many.py", "".join("def match_" + str(i) + "(): pass\n" for i in range(10)))
    result = CodeFindSymbol().execute(_req("code_find_symbol", name="match_", path="many.py", max_results=4))
    assert result["ok"] is True and result["count"] == 4


@pytest.mark.audit
@pytest.mark.security
def test_find_symbol_path_escape_is_clean_failure():
    """A non-empty name but an escaping path -> SandboxError -> ok=False (code_index.py:212-213)."""
    result = CodeFindSymbol().execute(_req("code_find_symbol", name="anything", path="../../etc"))
    assert result["ok"] is False and isinstance(result["error"], str)


# --------------------------------------------------------------------------------------
# code_find_references — raw substring per line, strip+truncate, early max_results return
# --------------------------------------------------------------------------------------


@pytest.mark.audit
def test_find_references_raw_substring_strip_and_truncate():
    """References match a raw substring per line; the stored line is stripped and capped at 300 chars
    (code_index.py:237). Whitespace is trimmed; an over-long line is truncated."""
    long_tail = "z" * 400
    src = "    needle here\n" + "x = '" + long_tail + "'  # needle\n" + "no match line\n"
    _write("ref.py", src)
    result = CodeFindReferences().execute(_req("code_find_references", name="needle", path="ref.py"))
    assert result["ok"] is True
    assert result["count"] == 2
    first = result["references"][0]
    assert first["lineno"] == 1
    assert first["line"] == "needle here"  # leading whitespace stripped
    # Every stored line is capped at 300 characters.
    assert all(len(r["line"]) <= 300 for r in result["references"])


@pytest.mark.audit
def test_find_references_early_truncation_returns_on_max_results():
    """Once max_results references are collected the search returns immediately with truncated=True
    (code_index.py:238-239) — it does not scan the remaining matches."""
    _write("rep.py", "".join("target\n" for _ in range(10)))
    result = CodeFindReferences().execute(_req("code_find_references", name="target", path="rep.py", max_results=3))
    assert result["ok"] is True
    assert result["truncated"] is True
    assert result["count"] == 3 and len(result["references"]) == 3


@pytest.mark.audit
def test_find_references_no_truncation_reports_false():
    """When fewer matches than the cap exist, truncated reflects the file-walk truncation flag (False
    here) rather than the early-return path (code_index.py:240)."""
    _write("few.py", "alpha\nbeta\nalpha\n")
    result = CodeFindReferences().execute(_req("code_find_references", name="alpha", path="few.py", max_results=50))
    assert result["ok"] is True and result["truncated"] is False and result["count"] == 2


@pytest.mark.audit
@pytest.mark.parametrize("empty", ["", None])
def test_find_references_empty_name_is_error(empty):
    """Empty/absent name -> error envelope (code_index.py:223-224)."""
    args = {} if empty is None else {"name": empty}
    result = CodeFindReferences().execute(ToolRequest(name="code_find_references", args={**args, "path": "."}))
    assert result == {"ok": False, "error": "name is required"}


@pytest.mark.audit
@pytest.mark.security
def test_find_references_path_escape_is_clean_failure():
    """An escaping path resolves to a SandboxError before the file walk (code_index.py:230-231)."""
    result = CodeFindReferences().execute(_req("code_find_references", name="x", path="/etc"))
    assert result["ok"] is False and isinstance(result["error"], str)


# --------------------------------------------------------------------------------------
# code_dependency_graph — dedup per file, skip entries lacking file/module, escape
# --------------------------------------------------------------------------------------


@pytest.mark.audit
def test_dependency_graph_dedups_modules_per_file():
    """The same module imported twice in one file appears once in that file's bucket
    (code_index.py:259). Distinct modules are all listed."""
    _write("dep.py", "import os\nimport os\nimport sys\nfrom os import path\n")
    result = CodeDependencyGraph().execute(_req("code_dependency_graph", path="dep.py"))
    assert result["ok"] is True
    bucket = result["graph"]["dep.py"]
    assert bucket.count("os") == 1  # deduped despite two `import os` lines
    assert "sys" in bucket
    assert result["files_count"] == 1


@pytest.mark.audit
def test_dependency_graph_groups_imports_by_file():
    """Two files each contribute their own bucket keyed by the workspace-relative path."""
    _write("pkg/a.py", "import json\n")
    _write("pkg/b.py", "import re\n")
    result = CodeDependencyGraph().execute(_req("code_dependency_graph", path="."))
    assert result["ok"] is True
    assert result["graph"]["pkg/a.py"] == ["json"]
    assert result["graph"]["pkg/b.py"] == ["re"]


@pytest.mark.audit
def test_dependency_graph_skips_relative_import_with_empty_module():
    """`from . import x` produces a from_import row whose module is '' — a falsy module is skipped, so
    it never creates a graph bucket (code_index.py:256-257). A real-module sibling still appears."""
    _write("rel.py", "from . import sibling\nimport realmod\n")
    result = CodeDependencyGraph().execute(_req("code_dependency_graph", path="rel.py"))
    assert result["ok"] is True
    assert result["graph"]["rel.py"] == ["realmod"]  # the empty-module relative import was dropped


@pytest.mark.audit
@pytest.mark.security
def test_dependency_graph_path_escape_is_clean_failure():
    """An escaping path -> SandboxError -> ok=False, no graph key (code_index.py:251-252)."""
    result = CodeDependencyGraph().execute(_req("code_dependency_graph", path="../../etc"))
    assert result["ok"] is False and isinstance(result["error"], str)
    assert "graph" not in result


@pytest.mark.audit
def test_dependency_graph_empty_workspace_is_empty_graph():
    """An empty workspace yields an empty graph and zero files (no buckets to skip or build)."""
    _ws()  # ensure the dir exists but is empty
    result = CodeDependencyGraph().execute(_req("code_dependency_graph", path="."))
    assert result == {"ok": True, "files_count": 0, "graph": {}}


# --------------------------------------------------------------------------------------
# Property — AST symbols are well-formed; indexing is idempotent
# --------------------------------------------------------------------------------------

import keyword

_PY_IDENT = st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=6).filter(
    lambda s: s.isidentifier() and not keyword.iskeyword(s) and not keyword.issoftkeyword(s)
)


@st.composite
def _python_modules(draw):
    """Generate small but structurally valid Python modules: top-level funcs, async funcs, and a
    class with methods. Names are deduped so the produced source always parses."""
    names = draw(st.lists(_PY_IDENT, min_size=1, max_size=6, unique=True))
    lines = []
    for i, n in enumerate(names):
        kind = i % 4
        if kind == 0:
            lines.append("def " + n + "():\n    return 1\n")
        elif kind == 1:
            lines.append("async def " + n + "():\n    return 2\n")
        elif kind == 2:
            lines.append("class " + n + ":\n    def method_" + n + "(self):\n        return 3\n")
        else:
            lines.append("import " + n + "\n")
    return "\n".join(lines) + "\n"


@pytest.mark.audit
@pytest.mark.property
@given(src=_python_modules())
def test_property_generated_python_symbols_are_well_formed(src):
    """For any generated valid module: it parses (sanity), every symbol name is non-empty, and every
    symbol's lineno <= end_lineno. Pins the AST invariants the index relies on."""
    ast.parse(src)  # the generator only emits parseable source
    _write("gen.py", src)
    result = CodeIndex().execute(_req("code_index", path="gen.py"))
    assert result["ok"] is True
    assert result["errors"] == []
    for s in result["symbols"]:
        assert s["name"], "symbol names must be non-empty"
        assert s["lineno"] is not None and s["end_lineno"] is not None
        assert s["lineno"] <= s["end_lineno"]


@pytest.mark.audit
@pytest.mark.property
@given(src=_python_modules())
def test_property_indexing_is_idempotent(src):
    """Indexing the same file twice yields identical envelopes — the index is a pure function of file
    content (no hidden ordering/state). Compares symbols, imports, and counts."""
    _write("idem.py", src)
    first = CodeIndex().execute(_req("code_index", path="idem.py"))
    second = CodeIndex().execute(_req("code_index", path="idem.py"))
    assert first == second
