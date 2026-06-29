"""Whitelisted, no-shell command runner for cmd-gate checks (`test_passes`).

The safety boundary is the WHITELIST: an author may only name a pre-registered `cmd_id`, never a
raw command string. Templates are operator-controlled argv LISTS; params fill `{name}` placeholders
as SEPARATE argv elements with `shell=False` — so there is no shell to inject into. Every run gets
a hard timeout, a scrubbed env, and the node's own dir as cwd.

NOT enforced here: network isolation. True no-net needs a container / namespace sandbox; on a bare
host it can't be done portably, so this runner does NOT claim it. The real, portable walls are:
whitelist-only cmd_ids · no shell · hard timeout · scrubbed env. Register only commands you trust.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

# operator-registered argv templates: cmd_id -> argv list, e.g. {"pytest_q": ["python3","-m","pytest","-q","{path}"]}
CMD_TEMPLATES: dict[str, list[str]] = {}

# checks that RUN a command instead of reading an artifact (the gate runner handles them specially)
CMD_CHECKS = frozenset({"test_passes"})

# params consumed by the gate (not substituted into the command). Everything else fills a placeholder.
CONTROL_KEYS = frozenset({"cmd_id", "timeout"})

DEFAULT_TIMEOUT = 30.0
MAX_TIMEOUT = 300.0  # hard cap — a worker-proposed timeout can't hang the solver loop
_SAFE_ENV = {"PATH": "/usr/bin:/bin:/usr/local/bin", "LANG": "C.UTF-8"}
_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def register_cmd(cmd_id: str, argv: list[str]) -> None:
    """Operator action — add a trusted command template to the whitelist."""
    if not isinstance(argv, (list, tuple)) or not argv:
        raise ValueError("cmd template must be a non-empty argv list")
    CMD_TEMPLATES[cmd_id] = list(argv)


def unsafe_path_value(value) -> bool:
    """A string value that looks like a path escape (absolute / `..` segment / `~`). Used to keep an
    author from steering a cmd's path argument outside the node's dir."""
    if not isinstance(value, str):
        return False
    s = value.strip()
    return os.path.isabs(s) or s.startswith("~") or ".." in s.replace("\\", "/").split("/")


@dataclass(frozen=True)
class CmdResult:
    ok: bool           # the process ran to completion (False = a runner error: not whitelisted / bad param / timeout / exec)
    code: int | None
    stdout: str
    reason: str = ""


def _fill(token: str, params: dict) -> str:
    out = token
    for key, value in params.items():
        out = out.replace("{" + str(key) + "}", str(value))
    return out


def run_cmd(cmd_id: str, params: dict, cwd: str | Path, timeout: float = DEFAULT_TIMEOUT) -> CmdResult:
    """Fail-closed exec boundary. Beyond the whitelist + no-shell, it: only fills params that are
    ACTUAL placeholders in the template (no extra-key injection), refuses path-escape values, and
    clamps the timeout. This layer is safe regardless of what upstream validated."""
    template = CMD_TEMPLATES.get(cmd_id)
    if template is None:
        return CmdResult(False, None, "", f"cmd_id {cmd_id!r} not whitelisted")
    placeholders = {m for tok in template for m in _PLACEHOLDER_RE.findall(tok)}
    fill = {k: v for k, v in (params or {}).items() if k not in CONTROL_KEYS}
    for key, value in fill.items():
        if key not in placeholders:
            return CmdResult(False, None, "", f"param {key!r} is not a placeholder in cmd {cmd_id!r}")
        if unsafe_path_value(value):
            return CmdResult(False, None, "", f"param {key!r} has an unsafe path value")
    try:
        timeout = max(0.1, min(float(timeout), MAX_TIMEOUT))
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT
    argv = [_fill(tok, fill) for tok in template]
    try:
        proc = subprocess.run(  # noqa: S603 — argv list, shell=False, whitelist-only, jailed params; no injection surface
            argv, cwd=str(cwd), timeout=timeout, capture_output=True, text=True,
            shell=False, env=dict(_SAFE_ENV),
        )
    except subprocess.TimeoutExpired:
        return CmdResult(False, None, "", f"timeout after {timeout}s")
    except (FileNotFoundError, OSError, ValueError) as exc:
        return CmdResult(False, None, "", f"exec error: {exc}")
    return CmdResult(True, proc.returncode, proc.stdout, "")
