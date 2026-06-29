#!/usr/bin/env python3
"""privacy_read_guard.py — block reads of secret files behind human approval (compliance).

PreToolUse:Read gate. When the LLM tries to Read a likely-secret file
(.env / .env.* , *.pem , *.key , credentials , secrets.yaml , id_rsa / id_ed25519)
the read is BLOCKED (exit 2) and an @@PRIVACY_PROMPT@@ marker carrying
AskUserQuestion JSON is emitted, so the controller surfaces the decision to the
human. On approval the file is read out-of-band via `bash cat <path>` (this gate
matches the Read tool only, so the approved bash read passes); on denial the agent
continues without the file.

Restores the upstream block->approve control that an earlier port had downgraded
to an advisory nudge. Compliance posture: default ON (a gate that ships asleep
protects nothing), fail-closed on its OWN errors, fail-open on absent/unparseable
input — blocking every Read on a transport hiccup would brick the session, and an
unparseable payload names no file to gate. example/sample/template files are
documentation and are exempt. HOOK_CLASS lives here in code, never in config.

Known residual (documented, not silently ignored): the human is asked, but the
approved read travels over `bash cat`, which this Read-matcher gate does not see —
a deliberately-evasive agent could read a secret straight over bash without
tripping the gate. Closing that fully means gating bash file-reads too (high
false-positive cost) or an out-of-band approval store; tracked in BACKLOG.
"""

import json
import os
import re
import sys
from pathlib import Path

# Block text is ASCII, but guard stderr encoding so a non-UTF-8 locale degrades to
# replacement chars instead of raising mid-write.
try:
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001 — older/detached streams; never fatal
    pass

_HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HOOKS_DIR, "..", "scripts"))
if _HOOKS_DIR not in sys.path:
    sys.path.append(_HOOKS_DIR)
import hook_runtime  # noqa: E402

HOOK_CLASS = "compliance"
_NAME = Path(__file__).stem

# Documentation/template files carrying these suffixes are exempt — they ship in
# repos as examples and hold no real secrets.
_SAFE = re.compile(r"\.(example|sample|template)$", re.IGNORECASE)

# Likely-secret path shapes (ported detection set). Matched against the full path
# so an absolute or nested target still trips (anchors use (^|/) and $).
# All patterns are case-INSENSITIVE: on a case-insensitive filesystem (macOS,
# Windows) `.ENV` IS the real `.env`, so a case variant must trip the same gate
# — a case-sensitive pattern here is a silent secret leak.
_SENSITIVE = [
    re.compile(r"(^|/)\.env$", re.IGNORECASE),   # .env, path/to/.env
    re.compile(r"(^|/)\.env\.", re.IGNORECASE),  # .env.local, .env.production, ...
    re.compile(r"credentials", re.IGNORECASE),
    re.compile(r"secrets?\.ya?ml$", re.IGNORECASE),
    re.compile(r"\.pem$", re.IGNORECASE),        # private keys / certs
    re.compile(r"\.key$", re.IGNORECASE),        # private keys
    # SSH private keys — all four common types (rsa/dsa/ecdsa/ed25519); ECDSA
    # is the default on many modern systems, so gating only rsa/ed25519 leaked it.
    # The (?!\.pub) lookahead lets the PUBLIC counterpart (id_rsa.pub, ...) read
    # freely — a public key is not a secret, and a false block trains rubber-stamping.
    re.compile(r"(^|/)id_(?:rsa|dsa|ecdsa|ed25519)(?!\.pub)", re.IGNORECASE),
]

_PROMPT_START = "@@PRIVACY_PROMPT_START@@"
_PROMPT_END = "@@PRIVACY_PROMPT_END@@"


_APPROVAL_PREFIX = "APPROVED:"


def _has_approval(path: str) -> bool:
    """True when a read path carries the human-approval sentinel (APPROVED:<path>)."""
    return bool(path) and path.startswith(_APPROVAL_PREFIX)


def _strip_approval(path: str) -> str:
    """The real path with any APPROVED: sentinel removed."""
    return path[len(_APPROVAL_PREFIX):] if _has_approval(path) else path


def _is_sensitive(path: str) -> bool:
    # Detect sensitivity on the CLEAN path so an APPROVED: sentinel can never bypass
    # the gate by breaking the pattern match (it would otherwise read as non-secret).
    clean = _strip_approval(path or "")
    if not clean:
        return False
    base = clean.rsplit("/", 1)[-1]
    if _SAFE.search(base):
        return False
    return any(p.search(clean) for p in _SENSITIVE)


_READ_TOOLS = ("Read", "NotebookRead")


def _read_target(data: dict) -> str:
    """The file path a pure-read tool is about to open; '' for any other tool.
    Covers Read and NotebookRead (both read a file whole); write-intent tools
    (Edit/Write) are out of scope here — they go through write_guard."""
    if data.get("tool_name") not in _READ_TOOLS:
        return ""
    inp = data.get("tool_input") or {}
    return str(inp.get("file_path") or inp.get("path") or "")


def _block_reason(path: str) -> str:
    """An actionable block reason embedding the @@PRIVACY_PROMPT@@ marker the
    controller parses to raise an AskUserQuestion."""
    base = path.rsplit("/", 1)[-1]
    prompt = {
        "type": "PRIVACY_PROMPT",
        "file": path,
        "basename": base,
        "question": {
            "header": "File Access",
            "text": ('Read "%s"? It may hold secrets (API keys, passwords, '
                     "tokens)." % base),
            "options": [
                {"label": "Approve",
                 "description": "Allow reading %s this time" % base},
                {"label": "Skip", "description": "Continue without this file"},
            ],
        },
    }
    return (
        "reading a secrets file (%s) requires human approval — this protects "
        "sensitive data, it is not an error.\n%s\n%s\n%s\n"
        "Ask the user with AskUserQuestion using the JSON above. If approved, retry the "
        'Read with the path prefixed by APPROVED: (Read "APPROVED:%s") — the gate allows '
        "it and audit-logs the override; or read it out-of-band via bash cat. If denied, "
        "continue without the file."
        % (path, _PROMPT_START, json.dumps(prompt), _PROMPT_END, path)
    )


def core(data: dict):
    """Compliance core: None ⇒ allow; str ⇒ block reason. Gates only a Read of a
    secrets file; every other tool and every non-secret path passes."""
    target = _read_target(data)
    if not _is_sensitive(target):
        return None
    if _has_approval(target):
        return None  # human-approved override (main strips the sentinel + audits)
    return _block_reason(target)


def _allow_stripped_output(data: dict) -> dict:
    """PreToolUse allow decision that strips the APPROVED: sentinel from the path the
    Read tool opens, so the approved read targets the real file."""
    inp = dict(data.get("tool_input") or {})
    for k in ("file_path", "path"):
        if k in inp and isinstance(inp[k], str):
            inp[k] = _strip_approval(inp[k])
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason":
                "human-approved sensitive read (APPROVED: sentinel)",
            "updatedInput": inp,
        }
    }


def main() -> int:
    # An APPROVED: sentinel on a sensitive read is a human-approved override: allow it,
    # strip the sentinel so Read opens the real file, and audit-log the override.
    raw = hook_runtime.read_stdin_json()
    target = _read_target(raw)
    if _has_approval(target) and _is_sensitive(target):
        try:
            import trace_log
            trace_log.append_event(hook=_NAME, event="privacy_override_approved",
                                   tool="Read", target=_strip_approval(target),
                                   status="APPROVED", tool_input=raw.get("tool_input"))
        except Exception:
            pass
        sys.stdout.write(json.dumps(_allow_stripped_output(raw)) + "\n")
        return 0
    # Compliance wrapper: fail-closed on its own errors, fail-open on absent input.
    hook_runtime.run_compliance_hook(_NAME, core, raw=json.dumps(raw))
    return 0


if __name__ == "__main__":
    sys.exit(main())
