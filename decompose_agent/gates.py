"""Gate-1: the done-gate runner. CODE is the sole PASS/FAIL authority.

Two anti-gaming walls, both enforced here and nowhere a worker can reach:
  * a **closed** CHECK_VOCAB — a criterion whose `check` is not a known predicate FAILs
    ("unknown check"); prose can't smuggle in an un-checkable claim.
  * an **artifact assertion that runs BEFORE every predicate** — the artifact must exist,
    be non-empty, sit inside the node's workspace, and be FRESH (mtime >= activated_at).
    Empty == FAIL; a stale file left over from a prior run can't pre-satisfy a gate.

`run_checks` is the only constructor of a `Verdict` — there is no field or path a caller or
worker can use to set `ok`. node_verdict = PASS iff every criterion's result is ok (AND, no
partial credit). `all_children_done` is structural (reads child statuses, no artifact) and
blocks the empty case explicitly — `all([])` is True in Python, so 0 children must FAIL (F1).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from .node import Node


class UnsafeArtifactPath(ValueError):
    """An artifact path escapes the node workspace (defense-in-depth; Node also jails)."""


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    reason: str = ""


@dataclass(frozen=True)
class CriterionVerdict:
    check: str
    ok: bool
    artifact: str | None
    reason: str


@dataclass(frozen=True)
class Verdict:
    node: str
    results: tuple[CriterionVerdict, ...]
    node_verdict: str  # "PASS" | "FAIL" — written only here

    @property
    def ok(self) -> bool:
        return self.node_verdict == "PASS"


# ── path jail ─────────────────────────────────────────────────────────────────


def resolve_in_workspace(workspace: str | Path, artifact: str) -> Path:
    """Resolve `artifact` under `workspace`, refusing anything that escapes it."""
    base = Path(workspace).resolve()
    target = (base / artifact).resolve()
    if target != base and base not in target.parents:
        raise UnsafeArtifactPath(f"artifact {artifact!r} escapes workspace {base}")
    return target


def _assert_artifact(workspace: Path, artifact: str, activated_at: float | None) -> str | None:
    """Return a failure reason, or None if the artifact passes exists/non-empty/jail/fresh."""
    try:
        path = resolve_in_workspace(workspace, artifact)
    except UnsafeArtifactPath as exc:
        return f"unsafe artifact path: {exc}"
    if not path.is_file():
        return f"missing artifact {artifact!r}"
    if path.stat().st_size == 0:
        return f"empty artifact {artifact!r}"
    if activated_at is not None and path.stat().st_mtime < activated_at:
        return f"stale artifact {artifact!r} (mtime < activated_at)"
    return None


# ── tiny JSON-pointer (RFC6901 subset) ────────────────────────────────────────


class _PointerMiss(Exception):
    pass


def _json_pointer_get(obj: Any, ptr: str) -> Any:
    if ptr in ("", "/"):
        return obj
    cur = obj
    for raw in ptr.lstrip("/").split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, dict):
            if token not in cur:
                raise _PointerMiss(ptr)
            cur = cur[token]
        elif isinstance(cur, list):
            try:
                cur = cur[int(token)]
            except (ValueError, IndexError):
                raise _PointerMiss(ptr)
        else:
            raise _PointerMiss(ptr)
    return cur


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _load_json(path: Path) -> Any:
    return json.loads(_read_text(path))


def _nonempty_lines(path: Path) -> int:
    return sum(1 for line in _read_text(path).splitlines() if line.strip())


# ── data checks: pure (params, artifact_path) -> CheckResult ──────────────────


def _file_exists(params: dict, path: Path) -> CheckResult:
    return CheckResult(True)  # exists + non-empty already proven by the artifact assertion


def _file_nonempty_lines(params: dict, path: Path) -> CheckResult:
    need = int(params.get("min", 1))
    got = _nonempty_lines(path)
    return CheckResult(got >= need, "" if got >= need else f"{got} non-empty lines < min {need}")


def _row_count_gte(params: dict, path: Path) -> CheckResult:
    need = int(params.get("n", 1))
    got = _nonempty_lines(path)
    return CheckResult(got >= need, "" if got >= need else f"{got} rows < n {need}")


def _grep_matches(params: dict, path: Path) -> CheckResult:
    need = int(params.get("min", 1))
    try:
        rx = re.compile(params["pattern"])
    except (KeyError, re.error) as exc:
        return CheckResult(False, f"bad grep pattern: {exc}")
    got = sum(1 for line in _read_text(path).splitlines() if rx.search(line))
    return CheckResult(got >= need, "" if got >= need else f"{got} matches < min {need}")


def _grep_absent(params: dict, path: Path) -> CheckResult:
    try:
        rx = re.compile(params["pattern"])
    except (KeyError, re.error) as exc:
        return CheckResult(False, f"bad grep pattern: {exc}")
    for line in _read_text(path).splitlines():
        if rx.search(line):
            return CheckResult(False, f"forbidden pattern present: {params['pattern']!r}")
    return CheckResult(True)


def _json_field_equals(params: dict, path: Path) -> CheckResult:
    try:
        value = _json_pointer_get(_load_json(path), params["ptr"])
    except (json.JSONDecodeError, ValueError, _PointerMiss, KeyError) as exc:
        return CheckResult(False, f"json/ptr error: {exc}")
    expected = params.get("value")
    return CheckResult(value == expected, "" if value == expected else f"{value!r} != {expected!r}")


def _json_field_exists(params: dict, path: Path) -> CheckResult:
    try:
        _json_pointer_get(_load_json(path), params["ptr"])
    except (json.JSONDecodeError, ValueError, _PointerMiss, KeyError) as exc:
        return CheckResult(False, f"missing/invalid: {exc}")
    return CheckResult(True)


def _json_field_in_range(params: dict, path: Path) -> CheckResult:
    try:
        value = _json_pointer_get(_load_json(path), params["ptr"])
        lo, hi = float(params["min"]), float(params["max"])
        num = float(value)
    except (json.JSONDecodeError, ValueError, TypeError, _PointerMiss, KeyError) as exc:
        return CheckResult(False, f"not a number in range: {exc}")
    return CheckResult(lo <= num <= hi, "" if lo <= num <= hi else f"{num} not in [{lo},{hi}]")


def _json_len_gte(params: dict, path: Path) -> CheckResult:
    try:
        value = _json_pointer_get(_load_json(path), params["ptr"])
        need = int(params["n"])
        got = len(value)
    except (json.JSONDecodeError, ValueError, TypeError, _PointerMiss, KeyError) as exc:
        return CheckResult(False, f"len error: {exc}")
    return CheckResult(got >= need, "" if got >= need else f"len {got} < n {need}")


CHECK_VOCAB: dict[str, Callable[[dict, Path], CheckResult]] = {
    "file_exists": _file_exists,
    "file_nonempty_lines": _file_nonempty_lines,
    "row_count_gte": _row_count_gte,
    "grep_matches": _grep_matches,
    "grep_absent": _grep_absent,
    "json_field_equals": _json_field_equals,
    "json_field_exists": _json_field_exists,
    "json_field_in_range": _json_field_in_range,
    "json_len_gte": _json_len_gte,
}

ALL_CHILDREN_DONE = "all_children_done"


def _check_all_children_done(child_statuses: Sequence[str] | None) -> CheckResult:
    statuses = list(child_statuses or [])
    if not statuses:  # F1: all([]) is True — block the empty case explicitly
        return CheckResult(False, "no children (vacuous-done blocked)")
    pending = [s for s in statuses if s != "done"]
    return CheckResult(not pending, "" if not pending else f"{len(pending)}/{len(statuses)} children not done")


def run_checks(node: Node, workspace: str | Path, *, child_statuses: Sequence[str] | None = None) -> Verdict:
    """Evaluate every criterion in CODE and return the frozen verdict. Never raises on a bad
    artifact or a malformed predicate — those resolve to a FAIL result with a reason."""
    workspace = Path(workspace)
    results: list[CriterionVerdict] = []
    for crit in node.done_when:
        if crit.check == ALL_CHILDREN_DONE:
            res = _check_all_children_done(child_statuses)
        elif crit.check not in CHECK_VOCAB:
            res = CheckResult(False, f"unknown check {crit.check!r}")
        else:
            reason = _assert_artifact(workspace, crit.artifact, node.activated_at)
            if reason is not None:
                res = CheckResult(False, reason)
            else:
                path = resolve_in_workspace(workspace, crit.artifact)
                res = CHECK_VOCAB[crit.check](crit.params, path)
        results.append(CriterionVerdict(check=crit.check, ok=res.ok, artifact=crit.artifact, reason=res.reason))

    node_verdict = "PASS" if results and all(r.ok for r in results) else "FAIL"
    return Verdict(node=node.id, results=tuple(results), node_verdict=node_verdict)
