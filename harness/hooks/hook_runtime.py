#!/usr/bin/env python3
"""hook_runtime.py — one shared runtime for all harness hooks.

Ported from product-spec hook_runtime.py (crash audit, stdin/stdout skeleton,
config cache, telemetry wrapper) and generalized for the harness:

  * 3 hook classes instead of 2 hard-coded stem sets:
      - telemetry:  default ON,  fail-open, always {"continue": true}
      - nudge:      default OFF, advisory (stderr + exit 0)
      - compliance: default ON + BLOCKING, fail-CLOSED (exit 2 + reason)
    The class is a CODE CONSTANT in each hook file (`HOOK_CLASS = "..."`),
    never config data: a broken config file must not change what a
    hook is, only whether it is enabled and which mode it runs in.
  * config = harness-hooks.yaml (human-edited config is YAML).
    PyYAML is imported lazily INSIDE the config loader so telemetry/nudge
    paths stay importable without it; the compliance wrapper turns a missing
    dep into exit 2 + the install command.
  * resolve_actor(): every hook resolves identity independently —
    session file is an optional cache, never a prerequisite.

Telemetry/nudge public functions are fail-open: they never raise back into a
hook. The compliance wrapper is the one place that fails closed by design.
"""

import json
import os
import re
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

# --- shared Bash script matcher (single home for the Pre/Post:Bash pair) ------
# mark_bash_start (PreToolUse:Bash) and track_script_execution (PostToolUse:Bash)
# read ONE matcher from here so they can never drift out of lockstep. It matches
# a harness script (harness/scripts/<f>.py|sh or harness/e2e/<f>.py|sh) run in
# EXECUTION position — not merely referenced. A bare substring would count
# `grep ... scripts/check_fence.py`, `ls .../verify_install.py`, `cat ...` as
# runs and (via any read-back of these records) inflate the run signal with
# greps. Requiring a command boundary + optional interpreter is what keeps the
# signal real. group(1) = the harness-relative path (scripts/<f> | e2e/<f>).
#
# The path may carry an arbitrary leading dir prefix (`./`, an absolute path, or
# `"$CLAUDE_PROJECT_DIR"/...`): `(?:\S*/)?harness/` consumes it WITHOUT reopening
# the substring hole — it cannot bridge the space at an argument position, so a
# grep/ls/cat of the path (even an absolute one) still has no boundary in front
# and stays rejected.
#
# A bare `(` is NOT a boundary char: it opens a regex/code group as often as a
# subshell, so `python3 -c '... re.compile(r"(harness/scripts/x.py)")'` would
# false-count the capture group as a run. A genuine subshell that runs a harness
# script still presents a real boundary before the script (`(cd d && …`, `(…; …`)
# via the ; & | newline class, so dropping `(` loses no real execution signal.
SCRIPT_RE = re.compile(
    r"(?:^|[\n;|&])\s*"                                    # command boundary
    r"(?:[A-Za-z_]\w*=\S*\s+)*"                            # optional leading VAR=val env
    r"(?:(?:\S*/)?(?:python3?|bash|sh)(?:\s+-\S+)*\s+)?"   # optional interpreter (+ flags)
    r"(?:\S*/)?harness/((?:scripts|e2e)/[^\s]+\.(?:py|sh))"  # optional dir prefix (abs/$VAR/.)
)

# --- crash audit (ported PS as-is, env names re-prefixed) --------------------

_LOG_NAME = "hook-crashes.log"
_LOG_MAX_BYTES = 256 * 1024  # coarse cap; over this we rotate to .1 then truncate


def _hooks_dir() -> Path:
    return Path(__file__).resolve().parent


def _log_dir() -> Path:
    # HARNESS_HOOK_LOG_DIR lets tests redirect the crash log to a tmp dir.
    raw = os.environ.get("HARNESS_HOOK_LOG_DIR")
    return Path(raw) if raw else _hooks_dir() / ".logs"


def _audit_disabled() -> bool:
    # Always-on by default; off via env, and silent under pytest so test runs
    # never write the real crash log.
    return bool(
        os.environ.get("HARNESS_HOOK_AUDIT_DISABLED")
        or os.environ.get("PYTEST_CURRENT_TEST")
    )


def log_hook_error(hook_name, exc) -> None:
    """Append ONE line (UTC ts, hook, exc type, message, traceback tail) to
    hook-crashes.log. Itself fail-open: any IO error is swallowed. Logs
    exception metadata ONLY, never the stdin payload (no PII leak)."""
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
            pass  # no file yet, or unstattable — nothing to rotate
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass  # fail-open: a crash logger must never crash a hook


# --- stdin / stdout skeleton (ported PS as-is) --------------------------------

def _parse(raw) -> dict:
    if not raw or not str(raw).strip():
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def read_stdin_json() -> dict:
    """Read stdin and parse it as a JSON object. Empty/malformed → {} (fail-open)."""
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    return _parse(raw)


def emit_continue() -> None:
    """Emit the non-blocking contract: {"continue": true} on stdout."""
    try:
        sys.stdout.write(json.dumps({"continue": True}))
        sys.stdout.flush()
    except Exception:
        pass  # fail-open


# --- per-hook config (YAML, enabled/mode overrides ONLY) ----------------------

_CONFIG_NAME = "harness-hooks.yaml"

# Per-class defaults. The compliance row is the deliberate inversion of the
# source corpus: a gate that ships asleep protects nothing.
_CLASS_DEFAULTS = {
    "telemetry": {"enabled": True, "mode": "advisory"},
    "nudge": {"enabled": False, "mode": "advisory"},
    "compliance": {"enabled": True, "mode": "blocking"},
}

_config_cache = None  # module-level; None = not yet loaded


def _config_path() -> Path:
    # HARNESS_HOOK_CONFIG (tests) wins; otherwise the YAML sits next to this
    # module, resolved off __file__ (durable, not CWD/env).
    raw = os.environ.get("HARNESS_HOOK_CONFIG")
    return Path(raw) if raw else _hooks_dir() / _CONFIG_NAME


def _load_config() -> dict:
    """Parse the config once per process. Malformed/unreadable/missing-PyYAML
    ⇒ {} (every hook then falls to its per-class default) + a crash-log line.
    The lazy yaml import keeps telemetry/nudge importable without PyYAML."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    cfg = {}
    try:
        p = _config_path()
        if p.is_file():
            import yaml  # lazy: missing dep degrades to class defaults here
            raw = yaml.safe_load(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("hooks"), dict):
                cfg = raw["hooks"]
    except Exception as e:  # noqa: BLE001 — malformed config must never crash a hook
        log_hook_error("hook_runtime", e)
        cfg = {}
    _config_cache = cfg
    return cfg


def _reset_config_cache() -> None:
    """Test seam: drop the per-process config cache so a fresh file is re-read."""
    global _config_cache
    _config_cache = None


def _telemetry_globally_disabled() -> bool:
    return bool(os.environ.get("HARNESS_TELEMETRY_DISABLED"))


def _hook_entry(name: str) -> dict:
    entry = _load_config().get(name)
    return entry if isinstance(entry, dict) else {}


def _guard_policy_mode(name: str):
    """The unified posture for a REGISTERED guard ('off'|'warn'|'block'), or
    None if `name` is not a registered guard or the posture engine is
    unavailable. Lazy + defensive: guard_policy lives in ../scripts and imports
    trace_log (which imports this module), so importing it at call time avoids a
    cycle, and any failure degrades to None so the caller falls to its class
    default -- the posture bridge must never break a hook."""
    try:
        import guard_policy  # lazy: avoid an import cycle
    except Exception:  # noqa: BLE001
        try:
            sys.path.append(str(_hooks_dir().parent / "scripts"))
            import guard_policy
        except Exception:  # noqa: BLE001
            return None
    if name not in guard_policy.GUARD_REGISTRY:
        return None
    try:
        return guard_policy.resolve_mode(name)
    except Exception:  # noqa: BLE001 -- malformed policy must not crash a hook
        return None


def hook_enabled(name: str, hook_class: str) -> bool:
    """Is hook ``name`` of ``hook_class`` enabled?

    Precedence: an explicit bool `enabled` in config wins (back-compat); else
    the unified guard policy when `name` is a registered guard (off => off);
    else the class default. The HARNESS_TELEMETRY_DISABLED kill-switch forces
    telemetry OFF and has no effect on nudge/compliance. `hook_class` comes from
    the hook's own HOOK_CLASS constant -- config cannot reclassify a hook.
    """
    defaults = _CLASS_DEFAULTS.get(hook_class, _CLASS_DEFAULTS["nudge"])
    if hook_class == "telemetry" and _telemetry_globally_disabled():
        return False
    val = _hook_entry(name).get("enabled")
    if isinstance(val, bool):
        return val
    gmode = _guard_policy_mode(name)
    if gmode is not None:
        return gmode != "off"
    return defaults["enabled"]


def hook_mode(name: str, hook_class: str) -> str:
    """Enforcement mode for an ENABLED hook: 'blocking' | 'advisory'.

    telemetry/nudge: always advisory; config cannot escalate them to blocking.
    compliance precedence: an explicit `mode` of 'advisory'/'blocking' in config
    wins (back-compat); else the unified guard policy when `name` is registered
    (warn => advisory, block => blocking); else blocking -- the safe default for
    a gate is to gate.
    """
    if hook_class != "compliance":
        return "advisory"
    explicit = _hook_entry(name).get("mode")
    if explicit in ("advisory", "blocking"):
        return explicit
    gmode = _guard_policy_mode(name)
    if gmode is not None:
        return "advisory" if gmode == "warn" else "blocking"
    return "blocking"


# --- actor resolution -------------------------------------------

def _git_user_email() -> str:
    try:
        out = subprocess.run(
            ["git", "config", "user.email"],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def _state_dir() -> Path:
    raw = os.environ.get("HARNESS_STATE_DIR")
    if raw:
        return Path(raw)
    # default: harness/state next to this module's parent (harness/hooks/..)
    return _hooks_dir().parent / "state"


def resolve_actor(session_id=None) -> str:
    """Resolve the acting identity. Attribution, NOT authentication —
    env-derived, spoofable, never an authz signal.

    Order: CI marker → session file cache (optional — a hook must work when
    session_init never ran) → HARNESS_USER → git config user.email →
    $USER. Agent suffix from HARNESS_AGENT. Format: user:<u>[/agent:<a>] | ci.
    """
    if os.environ.get("CI") or os.environ.get("GITLAB_CI") or os.environ.get("GITHUB_ACTIONS"):
        return "ci"

    if session_id:
        try:
            p = _state_dir() / "sessions" / ("%s.json" % session_id)
            if p.is_file():
                cached = json.loads(p.read_text(encoding="utf-8")).get("actor")
                if cached:
                    return str(cached)
        except Exception:
            pass  # cache miss/corrupt → fall through to env chain

    user = (
        os.environ.get("HARNESS_USER")
        or _git_user_email()
        or os.environ.get("USER", "unknown")
    )
    actor = "user:%s" % user
    agent = os.environ.get("HARNESS_AGENT")
    if agent:
        actor += "/agent:%s" % agent
    return actor


# --- telemetry convenience wrapper (ported PS) ---------------------------------

def run_telemetry_hook(name, core, raw=None) -> None:
    """Skeleton for telemetry hooks: read stdin JSON (or ``raw``), check
    enabled; if disabled, emit continue WITHOUT running core. Core runs inside
    a fail-open guard routing exceptions to the crash log. ALWAYS continues."""
    data = read_stdin_json() if raw is None else _parse(raw)
    try:
        if hook_enabled(name, "telemetry"):
            core(data)
    except Exception as e:  # noqa: BLE001 — telemetry must never break the op
        log_hook_error(name, e)
    emit_continue()


# --- nudge wrapper -------------------------------------------------------------

def run_nudge_hook(name, core, raw=None) -> None:
    """Skeleton for nudge hooks (default OFF): core(data) may return a message
    string → printed to stderr as advisory. Always exits 0 / continues."""
    data = read_stdin_json() if raw is None else _parse(raw)
    try:
        if hook_enabled(name, "nudge"):
            msg = core(data)
            if msg:
                sys.stderr.write("[advisory] %s\n" % msg)
    except Exception as e:  # noqa: BLE001 — a nudge must never break the op
        log_hook_error(name, e)
    emit_continue()


# --- compliance wrapper — fail-CLOSED, its own top-level guard ----------

def run_compliance_hook(name, core, raw=None) -> None:
    """Top-level wrapper for compliance hooks. NOT built on the telemetry
    skeleton: that one is fail-open by contract, a gate must be fail-closed.

    core(data) contract: return None ⇒ pass; return a string ⇒ block reason.
    EVERY exception raised by core — including ImportError from a machine
    that skipped preflight and config trouble — lands in the except arm and
    blocks with exit 2 + an actionable reason. In `mode: advisory` (explicit
    opt-in) the reason is warned to stderr and the op continues. Disabled
    (explicit `enabled: false`) ⇒ skip core, exit 0.

    Deliberate fail-open edge: empty or unparseable STDIN becomes {} (see
    read_stdin_json), so core sees no command and passes. Blocking every
    Bash call whenever the transport hiccups would be a denial-of-service on
    the whole session; a payload that cannot be parsed also yields no
    command to gate. The gate therefore fails closed on ITS OWN errors, and
    open on absent input.

    This function never raises and never exits 0 on a broken enabled gate.
    """
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
        # Missing dependency — point at the fix, then fail closed.
        log_hook_error(name, e)
        sys.stderr.write(
            "[%s] BLOCKED: dependency missing (%s).\n"
            "Run: python3 harness/scripts/preflight_deps.py\n"
            "or:  pip install pyyaml pytest\n" % (name, e)
        )
        sys.exit(2)
    except Exception as e:  # noqa: BLE001 — fail CLOSED, with audit trail
        log_hook_error(name, e)
        sys.stderr.write(
            "[%s] BLOCKED: gate crashed (%s: %s). Fail-closed by policy; "
            "see hook-crashes.log. To bypass IN AN EMERGENCY set "
            "`enabled: false` for this hook in harness-hooks.yaml — the "
            "change is tracked in git and traced.\n" % (name, type(e).__name__, e)
        )
        sys.exit(2)
