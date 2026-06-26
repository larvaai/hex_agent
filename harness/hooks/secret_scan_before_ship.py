#!/usr/bin/env python3
"""secret_scan_before_ship.py — pre-ship secret-leak gate (compliance, fail-closed).

Fires only at the leak boundary — a Bash command that advances the push/pr/ship/deploy
stage (stage_detector) — and scans the diff of the commits about to LEAVE the machine
(`git log --branches --not --remotes -p`). A likely secret in an added line of a
non-excluded file blocks the op with an actionable reason. test/fixture/docs paths are
excluded so the gate never self-blocks on its own fixtures and avoids the common false
positive. The thorough backstop is the hs-research:security-scan skill; this gate catches
the high-confidence machine-readable leak at the last moment.

Posture: compliance, fail-CLOSED on its own errors (run_compliance_hook). A git failure
that yields no diff is treated as nothing-to-scan (the wrapper passes on absent signal,
not on a detected secret). Break-glass: enabled:false in harness-hooks.yaml.
"""
import os
import re
import subprocess
import sys

_HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (_HOOKS_DIR, os.path.join(_HOOKS_DIR, "..", "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import hook_runtime  # noqa: E402

HOOK_CLASS = "compliance"
_HOOK = "secret_scan_before_ship"

# Stages where committed content actually leaves the machine.
_SHIP_STAGES = ("push", "pr", "ship", "deploy")

# High-confidence machine-readable secret shapes (mirrors the security-scan skill's
# secret-and-dependency reference). Precision-first: each requires a distinctive prefix
# or a key=quoted-value assignment, so prose does not false-match.
_PATTERNS = [
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("pem-private-key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
    ("anthropic-key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("generic-secret", re.compile(
        r"""(?i)(?:api[_-]?key|apikey|api[_-]?secret|secret|token|credential)\s*[:=]\s*['"][A-Za-z0-9/+=_-]{16,}['"]""")),
]

# Paths excluded from scanning: tests, fixtures, examples, docs, lockfiles. Excluding
# them is standard secret-scan practice and prevents the gate from blocking on its own
# fake-secret fixtures.
_EXCLUDE_RE = re.compile(
    r"(?:^|/)(?:tests?|spec|specs|fixtures?|examples?|samples?|mocks?|__tests__)(?:/|$)"
    r"|(?:^|/)test_[^/]*$|_test\.[a-z]+$|\.(?:md|lock)$",
    re.IGNORECASE)


def _excluded(path: str) -> bool:
    return bool(_EXCLUDE_RE.search(path or ""))


def scan_text(text: str) -> list:
    """Return the names of secret patterns that match `text` (deduped, ordered)."""
    hits = []
    for name, rx in _PATTERNS:
        if rx.search(text or "") and name not in hits:
            hits.append(name)
    return hits


def scannable_added_lines(diff: str) -> str:
    """The added (`+`) content of non-excluded files in a unified diff, header-stripped."""
    out = []
    excluded = False
    for line in (diff or "").splitlines():
        if line.startswith("+++ "):
            raw = line[4:].strip()
            path = raw[2:] if raw.startswith("b/") else raw
            excluded = _excluded(path)
            continue
        # NOTE: a "+++ b/path" header is already consumed above (with its
        # trailing space + continue), so a line reaching here that starts
        # with "+++" can only be ADDED CONTENT whose text starts with "++"
        # ("+" added-marker + "++..."); matching it as a header would drop
        # that content and let a secret on such a line evade the scan.
        if line.startswith("--- "):
            continue
        if excluded:
            continue
        if line.startswith("+"):
            out.append(line[1:])
    return "\n".join(out)


def gather_unpushed_diff(root: str) -> str:
    """The patch of commits not yet on any remote (everything, in a remote-less repo).
    Returns "" on any git failure — an unverifiable diff is no signal, not a secret."""
    try:
        r = subprocess.run(
            ["git", "-C", root, "log", "--branches", "--not", "--remotes",
             "-p", "--no-color", "--max-count=200"],
            capture_output=True, text=True, timeout=30)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def gate_reason(command: str, root: str):
    """None ⇒ allow; string ⇒ block reason. Only ship-class stages are scanned."""
    import stage_detector
    stage = stage_detector.detect_stage(command)
    if stage not in _SHIP_STAGES:
        return None
    hits = scan_text(scannable_added_lines(gather_unpushed_diff(root)))
    if not hits:
        return None
    return ("secret-scan blocked %s: the diff to be pushed contains likely secrets (%s). "
            "Remove them from the commits (and rotate the credential if it is real) before "
            "shipping; run /hs-research:security-scan for a full audit, or break-glass via "
            "enabled:false in harness/hooks/harness-hooks.yaml." % (stage, ", ".join(hits)))


def core(data):
    tool_input = data.get("tool_input") or {}
    command = tool_input.get("command")
    if not isinstance(command, str) or not command:
        return None
    import harness_paths
    return gate_reason(command, str(harness_paths.root()))


def main() -> None:
    import json
    raw = hook_runtime.read_stdin_json()
    hook_runtime.run_compliance_hook(_HOOK, core, raw=json.dumps(raw))


if __name__ == "__main__":
    main()
