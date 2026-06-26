"""Slice 6b — the code-owned acceptance gate. CODE is the sole PASS/FAIL authority.

Vendored into dragzero (not imported from the sibling package) so `drag_from_zero`
stays self-contained. Two anti-gaming walls, neither reachable by a worker/LLM:

  * a **closed** CHECK_VOCAB — an unknown `check` FAILs ("unknown check"); prose can't
    smuggle in an un-checkable claim.
  * an **artifact assertion that runs BEFORE every predicate** — the file must exist,
    be non-empty, sit inside the sandbox root, and be FRESH (mtime >= activated_at).
    Empty == FAIL; a stale leftover can't pre-satisfy a gate.

A `done_when` criterion is the typed triple `{check, params, artifact}` — a QUESTION the
gate answers, never an answer. Any verdict-shaped key (`verdict`/`passed`/`status`/`score`/
`done`) is a forgery and is rejected at construction. `run_checks` is the only constructor
of a `Verdict`: there is no field a caller can set to force `ok`.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Sequence

FORBIDDEN_VERDICT_KEYS = frozenset({"verdict", "passed", "status", "score", "done"})
_CRITERION_KEYS = frozenset({"check", "params", "artifact"})
ARTIFACTLESS_CHECKS = frozenset({"all_children_done"})


class UnsafeArtifactPath(ValueError):
    """An artifact path escapes the sandbox root."""


def assert_safe_relpath(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        raise ValueError("artifact path must be a non-empty string")
    p = path.strip()
    if os.path.isabs(p) or p.startswith("~"):
        raise ValueError(f"artifact path must be relative and in-workspace: {path!r}")
    if ".." in PurePosixPath(p).parts:
        raise ValueError(f"artifact path must not escape the workspace ('..'): {path!r}")
    return p


@dataclass(frozen=True)
class DoneWhen:
    """One acceptance criterion: a question the gate answers. Never an answer."""

    check: str
    params: dict = field(default_factory=dict)
    artifact: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.check, str) or not self.check.strip():
            raise ValueError("done_when criterion is missing a non-empty 'check'")
        if not isinstance(self.params, dict):
            raise ValueError(f"done_when 'params' must be a mapping, got {type(self.params).__name__}")
        if self.artifact is not None:
            object.__setattr__(self, "artifact", assert_safe_relpath(self.artifact))
        elif self.check not in ARTIFACTLESS_CHECKS:
            raise ValueError(f"done_when criterion {self.check!r} requires an 'artifact' path")

    @classmethod
    def from_dict(cls, raw: Any) -> "DoneWhen":
        if not isinstance(raw, dict):
            raise ValueError(f"done_when criterion must be a mapping, got {type(raw).__name__}")
        extra = set(raw) - _CRITERION_KEYS
        forged = extra & FORBIDDEN_VERDICT_KEYS
        if forged:
            raise ValueError(
                f"done_when criterion must not carry a verdict field {sorted(forged)} — "
                "the gate writes the verdict, not the author"
            )
        if extra:
            raise ValueError(f"done_when criterion has unexpected field(s) {sorted(extra)}")
        return cls(check=raw.get("check"), params=dict(raw.get("params") or {}), artifact=raw.get("artifact"))

    def as_dict(self) -> dict:
        out: dict = {"check": self.check}
        if self.params:
            out["params"] = dict(self.params)
        if self.artifact is not None:
            out["artifact"] = self.artifact
        return out


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

    def as_dict(self) -> dict:
        return {"check": self.check, "artifact": self.artifact, "ok": self.ok, "reason": self.reason}


@dataclass(frozen=True)
class Verdict:
    node: str
    results: tuple
    node_verdict: str  # "PASS" | "FAIL" — written only by run_checks

    @property
    def ok(self) -> bool:
        return self.node_verdict == "PASS"

    @property
    def reasons(self) -> list:
        return [r.reason for r in self.results if not r.ok and r.reason]


# ── path jail + artifact assertion ────────────────────────────────────────────
def resolve_in_workspace(workspace: str | Path, artifact: str) -> Path:
    base = Path(workspace).resolve()
    target = (base / artifact).resolve()
    if target != base and base not in target.parents:
        raise UnsafeArtifactPath(f"artifact {artifact!r} escapes workspace {base}")
    return target


def _assert_artifact(workspace: Path, artifact: str, activated_at: float | None) -> str | None:
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


# ── predicates: pure (params, path) -> CheckResult ────────────────────────────
def _file_exists(params: dict, path: Path) -> CheckResult:
    return CheckResult(True)  # exists + non-empty proven by the artifact assertion


def _file_nonempty_lines(params: dict, path: Path) -> CheckResult:
    need = int(params.get("min", 1))
    got = _nonempty_lines(path)
    return CheckResult(got >= need, "" if got >= need else f"{got} non-empty lines < min {need}")


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


def _json_field_exists(params: dict, path: Path) -> CheckResult:
    try:
        _json_pointer_get(_load_json(path), params["ptr"])
    except (json.JSONDecodeError, ValueError, _PointerMiss, KeyError) as exc:
        return CheckResult(False, f"missing/invalid: {exc}")
    return CheckResult(True)


def _json_field_equals(params: dict, path: Path) -> CheckResult:
    try:
        value = _json_pointer_get(_load_json(path), params["ptr"])
    except (json.JSONDecodeError, ValueError, _PointerMiss, KeyError) as exc:
        return CheckResult(False, f"json/ptr error: {exc}")
    expected = params.get("value")
    return CheckResult(value == expected, "" if value == expected else f"{value!r} != {expected!r}")


def _json_field_in_range(params: dict, path: Path) -> CheckResult:
    try:
        value = _json_pointer_get(_load_json(path), params["ptr"])
        lo, hi = float(params["min"]), float(params["max"])
        num = float(value)
    except (json.JSONDecodeError, ValueError, TypeError, _PointerMiss, KeyError) as exc:
        return CheckResult(False, f"not a number in range: {exc}")
    return CheckResult(lo <= num <= hi, "" if lo <= num <= hi else f"{num} not in [{lo},{hi}]")


CHECK_VOCAB: dict[str, Callable[[dict, Path], CheckResult]] = {
    "file_exists": _file_exists,
    "file_nonempty_lines": _file_nonempty_lines,
    "grep_matches": _grep_matches,
    "grep_absent": _grep_absent,
    "json_field_exists": _json_field_exists,
    "json_field_equals": _json_field_equals,
    "json_field_in_range": _json_field_in_range,
}

ALL_CHILDREN_DONE = "all_children_done"


def _check_all_children_done(child_statuses: Sequence[str] | None) -> CheckResult:
    statuses = list(child_statuses or [])
    if not statuses:  # all([]) is True — block the vacuous-done case explicitly
        return CheckResult(False, "no children (vacuous-done blocked)")
    pending = [s for s in statuses if s != "done"]
    return CheckResult(not pending, "" if not pending else f"{len(pending)}/{len(statuses)} children not done")


def run_checks(
    done_when: Sequence[DoneWhen],
    workspace: str | Path,
    *,
    node_id: str = "?",
    activated_at: float | None = None,
    child_statuses: Sequence[str] | None = None,
) -> Verdict:
    """Evaluate every criterion in CODE and return the frozen verdict. Never raises on a bad
    artifact or a malformed predicate — those resolve to a FAIL result with a reason.

    node_verdict = PASS iff there is >=1 criterion AND all are ok (AND, no partial credit).
    An empty done_when is FAIL — "nothing to check" is never a pass.
    """
    workspace = Path(workspace)
    results: list[CriterionVerdict] = []
    for crit in done_when:
        if crit.check == ALL_CHILDREN_DONE:
            res = _check_all_children_done(child_statuses)
        elif crit.check not in CHECK_VOCAB:
            res = CheckResult(False, f"unknown check {crit.check!r}")
        else:
            reason = _assert_artifact(workspace, crit.artifact, activated_at)
            if reason is not None:
                res = CheckResult(False, reason)
            else:
                path = resolve_in_workspace(workspace, crit.artifact)
                res = CHECK_VOCAB[crit.check](crit.params, path)
        results.append(CriterionVerdict(check=crit.check, ok=res.ok, artifact=crit.artifact, reason=res.reason))

    node_verdict = "PASS" if results and all(r.ok for r in results) else "FAIL"
    return Verdict(node=node_id, results=tuple(results), node_verdict=node_verdict)


def build_done_when(raw: Sequence[dict]) -> list[DoneWhen]:
    """Author-time: build typed triples from raw dicts, rejecting forgeries. Raises on bad input."""
    return [DoneWhen.from_dict(c) for c in (raw or [])]


def mu(done_when: Sequence[DoneWhen]) -> int:
    """Node-local measure = done_when_count (the spec's sole well-ordered measure).
    Subtree μ is summed by the caller; an unsplittable criterion floors at 1."""
    return max(1, len(done_when))
