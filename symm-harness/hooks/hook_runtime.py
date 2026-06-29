#!/usr/bin/env python3
"""hook_runtime.py — one shared runtime for all symm-harness hooks.

Ported from harness/hooks/hook_runtime.py, trimmed for a solo tree: dropped the
Bash-script matcher and the guard_policy posture bridge (symm ships zero
compliance gates today). What remains is the part worth keeping:

  3 hook classes, each a CODE CONSTANT (`HOOK_CLASS = "..."`) in the hook file —
  never config data, so a broken config can change whether a hook runs, never
  what it IS:
    - telemetry:  default ON,  fail-OPEN, always {"continue": true}
    - nudge:      default OFF, advisory (stderr + exit 0)
    - compliance: default ON + BLOCKING, fail-CLOSED (exit 2 + reason)

  config = symm-hooks.yaml (enabled/mode overrides only; PyYAML imported lazily
  so telemetry/nudge stay importable without it).
  resolve_actor(): attribution, not auth — env-derived, spoofable.

telemetry/nudge wrappers never raise back into a hook. The compliance wrapper
is the one place that fails closed by design.
"""

import json
import os
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import paths  # noqa: E402  — pure resolver, single source of root/state dirs

# --- crash audit -------------------------------------------------------------

_LOG_NAME = "hook-crashes.log"
_LOG_MAX_BYTES = 256 * 1024


def _hooks_dir() -> Path:
    return Path(__file__).resolve().parent


def _log_dir() -> Path:
    raw = os.environ.get("SYMM_HOOK_LOG_DIR")
    return Path(raw) if raw else _hooks_dir() / ".logs"


def _audit_disabled() -> bool:
    return bool(
        os.environ.get("SYMM_HOOK_AUDIT_DISABLED")
        or os.environ.get("PYTEST_CURRENT_TEST")
    )


def log_hook_error(hook_name, exc) -> None:
    """Append ONE line (UTC ts, hook, exc type/msg, tb tail) to
    hook-crashes.log. Fail-open; logs exception metadata ONLY, never stdin."""
    if _audit_disabled():
        return
    try:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        tb_tail = tb.strip().splitlines()[-1] if tb.strip() else ""
        line = json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "hook": str(hook_name),
                "type": type(exc).__name__,
                "msg": str(exc)[:500],
                "tb": tb_tail[:500],
            },
            ensure_ascii=False,
        )
        d = _log_dir()
        d.mkdir(parents=True, exist_ok=True)
        p = d / _LOG_NAME
        try:
            if p.stat().st_size > _LOG_MAX_BYTES:
                p.replace(d / (_LOG_NAME + ".1"))
        except OSError:
            pass
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass  # a crash logger must never crash a hook


# --- stdin / stdout skeleton -------------------------------------------------

def _parse(raw) -> dict:
    if not raw or not str(raw).strip():
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def read_stdin_json() -> dict:
    """Read stdin, parse as JSON object. Empty/malformed → {} (fail-open)."""
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    return _parse(raw)


def emit_continue() -> None:
    """Emit the non-blocking contract: {"continue": true}."""
    try:
        sys.stdout.write(json.dumps({"continue": True}))
        sys.stdout.flush()
    except Exception:
        pass


# --- per-hook config (enabled/mode overrides ONLY) ---------------------------

_CLASS_DEFAULTS = {
    "telemetry": {"enabled": True, "mode": "advisory"},
    "nudge": {"enabled": False, "mode": "advisory"},
    "compliance": {"enabled": True, "mode": "blocking"},
}

_config_cache = None  # None = not yet loaded


def _load_config() -> dict:
    """Parse symm-hooks.yaml once per process. Malformed/missing/no-PyYAML ⇒ {}
    (every hook then falls to its class default) + a crash-log line."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    cfg = {}
    try:
        p = paths.config_file()
        if p.is_file():
            import yaml  # lazy: missing dep degrades to class defaults
            raw = yaml.safe_load(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("hooks"), dict):
                cfg = raw["hooks"]
    except Exception as e:  # noqa: BLE001 — config must never crash a hook
        log_hook_error("hook_runtime", e)
        cfg = {}
    _config_cache = cfg
    return cfg


def _reset_config_cache() -> None:
    """Test seam: drop the cache so a fresh file is re-read."""
    global _config_cache
    _config_cache = None


def _hook_entry(name: str) -> dict:
    entry = _load_config().get(name)
    return entry if isinstance(entry, dict) else {}


def hook_enabled(name: str, hook_class: str) -> bool:
    """Explicit `enabled` bool in config wins; else the class default.
    SYMM_TELEMETRY_DISABLED forces telemetry OFF (no effect on nudge/compliance).
    hook_class comes from the hook's HOOK_CLASS — config cannot reclassify."""
    defaults = _CLASS_DEFAULTS.get(hook_class, _CLASS_DEFAULTS["nudge"])
    if hook_class == "telemetry" and os.environ.get("SYMM_TELEMETRY_DISABLED"):
        return False
    val = _hook_entry(name).get("enabled")
    return val if isinstance(val, bool) else defaults["enabled"]


def hook_mode(name: str, hook_class: str) -> str:
    """'blocking' | 'advisory' for an enabled hook. telemetry/nudge are always
    advisory (config cannot escalate). compliance: explicit config mode wins,
    else blocking — a gate's safe default is to gate."""
    if hook_class != "compliance":
        return "advisory"
    explicit = _hook_entry(name).get("mode")
    return explicit if explicit in ("advisory", "blocking") else "blocking"


# --- actor resolution (attribution, NOT auth) --------------------------------

def _git_user_email() -> str:
    try:
        out = subprocess.run(
            ["git", "config", "user.email"],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def resolve_actor(session_id=None) -> str:
    """CI marker → session-file cache (optional) → SYMM_USER → git email → $USER.
    Agent suffix from SYMM_AGENT. Format: user:<u>[/agent:<a>] | ci."""
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS") or os.environ.get("GITLAB_CI"):
        return "ci"
    if session_id:
        try:
            p = paths.sessions_dir() / ("%s.json" % session_id)
            if p.is_file():
                cached = json.loads(p.read_text(encoding="utf-8")).get("actor")
                if cached:
                    return str(cached)
        except Exception:
            pass  # cache miss/corrupt → fall through
    user = (
        os.environ.get("SYMM_USER")
        or _git_user_email()
        or os.environ.get("USER", "unknown")
    )
    actor = "user:%s" % user
    agent = os.environ.get("SYMM_AGENT")
    if agent:
        actor += "/agent:%s" % agent
    return actor


# --- telemetry wrapper (fail-open) -------------------------------------------

def run_telemetry_hook(name, core, raw=None) -> None:
    """Read stdin (or `raw`), check enabled, run core inside a fail-open guard.
    ALWAYS continues — telemetry must never break the op it observes."""
    data = read_stdin_json() if raw is None else _parse(raw)
    try:
        if hook_enabled(name, "telemetry"):
            core(data)
    except Exception as e:  # noqa: BLE001
        log_hook_error(name, e)
    emit_continue()


# --- nudge wrapper (advisory) ------------------------------------------------

def run_nudge_hook(name, core, raw=None) -> None:
    """core(data) may return a string → printed to stderr as advisory.
    Default OFF. Always exits 0 / continues."""
    data = read_stdin_json() if raw is None else _parse(raw)
    try:
        if hook_enabled(name, "nudge"):
            msg = core(data)
            if msg:
                sys.stderr.write("[advisory] %s\n" % msg)
    except Exception as e:  # noqa: BLE001
        log_hook_error(name, e)
    emit_continue()


# --- compliance wrapper (fail-CLOSED) ----------------------------------------

def run_compliance_hook(name, core, raw=None) -> None:
    """core(data) contract: None ⇒ pass; string ⇒ block reason. Every exception
    (incl. ImportError) lands in the except arm and blocks with exit 2. In
    `mode: advisory` the reason is warned and the op continues. Disabled ⇒ skip.

    Fail-open edge: empty/unparseable stdin → {} → core sees no input and passes
    (blocking on a transport hiccup would DoS the session). The gate fails closed
    on ITS OWN errors, open on absent input."""
    try:
        data = read_stdin_json() if raw is None else _parse(raw)
        if not hook_enabled(name, "compliance"):
            emit_continue()
            sys.exit(0)
        reason = core(data)
        if reason:
            if hook_mode(name, "compliance") == "advisory":
                sys.stderr.write("[advisory] %s: %s\n" % (name, reason))
                emit_continue()
                sys.exit(0)
            sys.stderr.write("[%s] BLOCKED: %s\n" % (name, reason))
            sys.exit(2)
        emit_continue()
        sys.exit(0)
    except SystemExit:
        raise
    except ImportError as e:
        log_hook_error(name, e)
        sys.stderr.write(
            "[%s] BLOCKED: dependency missing (%s). Run: pip install pyyaml\n"
            % (name, e)
        )
        sys.exit(2)
    except Exception as e:  # noqa: BLE001 — fail CLOSED with audit trail
        log_hook_error(name, e)
        sys.stderr.write(
            "[%s] BLOCKED: gate crashed (%s: %s). Fail-closed by policy; see "
            "hook-crashes.log. Emergency bypass: set `enabled: false` for this "
            "hook in symm-hooks.yaml (tracked in git, traced).\n"
            % (name, type(e).__name__, e)
        )
        sys.exit(2)
