#!/usr/bin/env python3
"""bash_safety_guard.py — PreToolUse(Bash) compliance hook: destructive-command gate.

Blocks a small, high-precision set of catastrophic shell commands BEFORE they run:
root/system `rm -rf`, fork bomb, raw-device dd/mkfs/redirect/shred/wipefs,
`curl|sh`, recursive chmod/chown on root, and overwrite of critical system files.
Safety-first: this is the one gate that protects the HOST itself, independent of
any SDLC stage (gate_stage covers stage transitions; this covers blast radius).

Posture: compliance class — fail-CLOSED on its own errors, fail-OPEN on empty /
unparseable input (no command to gate). The pattern set is deliberately narrow and
TARGET-AWARE: it matches the wipe-the-machine class, NOT targeted deletes
(`rm -rf ./build`, `rm -rf /tmp/x`) or benign look-alikes (`dd of=file.img`,
`curl | jq`). It is defense-in-depth (raw-string regex over the command), not an
airtight sandbox — host perms and the AFK Docker isolation remain the primary
boundary; a determined operator can still spell a command around it.

HOOK_CLASS is a code constant; config (harness-hooks.yaml) can only toggle
enabled/mode, never reclassify the gate. Break-glass: `enabled: false` (the diff
is tracked and the skip is visible).
"""

import os
import re
import sys
from pathlib import Path

_HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HOOKS_DIR, "..", "scripts"))
if _HOOKS_DIR not in sys.path:
    sys.path.append(_HOOKS_DIR)
import hook_runtime  # noqa: E402

HOOK_CLASS = "compliance"
_NAME = Path(__file__).stem

# Bare catastrophic targets for rm/chmod: root, glob-root, home, or a bare
# top-level system dir (optionally a trailing `/` or `/*`). The trailing
# lookahead is what keeps it precise — `/home/user/...` is a SUBPATH and does
# NOT match (only bare /home, /home/ or /home/* do), so targeted deletes stay
# allowed. `(?:/\*?)?` accepts the bare dir, a trailing slash (`/etc/`) and the
# glob (`/etc/*`) — a trailing slash must NOT be a bypass.
_SYSDIRS = "etc|usr|bin|sbin|lib|lib64|boot|dev|proc|sys|root|var|opt|srv|home"
_DANG_TARGET = re.compile(
    r"(?:^|\s)(?:/|/\*|~|\$\{?HOME\}?|/(?:%s)(?:/\*?)?)(?=\s|$|;|&|\|)" % _SYSDIRS
)

# A command line splits into list/pipeline segments on these connectors; a
# dangerous target is only blamed on an rm/chmod in the SAME segment.
_CONNECTOR_RE = re.compile(r"[;&|\n]+")
# A trailing `#...` comment (at a word boundary) is not part of any command.
_COMMENT_RE = re.compile(r"(?:^|\s)#[^\n]*")

_RM_RECURSIVE = re.compile(r"\brm\b[^\n]*?(?:\s-\w*[rR]\w*\b|\s--recursive\b)")
_RM_NOPRESERVE = re.compile(r"\brm\b[^\n]*--no-preserve-root")
_FORKBOMB = re.compile(r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:")
_DD_DEV = re.compile(r"\bdd\b[^\n]*\bof=/dev/(?:sd|nvme|hd|vd|mmcblk|disk|xvd)")
_MKFS = re.compile(r"\bmkfs(?:\.\w+)?\b[^\n]*/dev/")
_REDIR_DEV = re.compile(r">\s*/dev/(?:sd|nvme|hd|vd|mmcblk|disk|xvd)[a-z0-9]*")
_SHRED_DEV = re.compile(r"\bshred\b[^\n]*/dev/")
_WIPEFS = re.compile(r"\b(?:wipefs|sgdisk)\b[^\n]*/dev/")
_CURL_SH = re.compile(r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:sudo\s+)?(?:ba|da|z|k)?sh\b")
_CHMOD_RECURSIVE = re.compile(r"\b(?:chmod|chown)\b[^\n]*\s-\w*[rR]\w*\b")
_CRIT_OVERWRITE = re.compile(
    r"(?:>|\btee\b[^\n]*)\s*/etc/(?:passwd|shadow|sudoers|group|fstab|hosts)\b"
)


def _clean(cmd: str) -> str:
    """Normalize a command for target matching: drop a trailing `#` comment and
    surrounding quotes. A system dir hidden in a comment must not false-trip the
    gate, and a quoted root (`rm -rf '/'`) must not slip past it."""
    no_comment = _COMMENT_RE.sub(" ", cmd)
    return no_comment.replace("'", "").replace('"', "")


def _segments(cmd: str):
    """Split a cleaned command into list/pipeline segments so a dangerous target
    in one segment is never blamed on an rm/chmod in another."""
    return _CONNECTOR_RE.split(cmd)


# Quoted spans. Two LENGTH-PRESERVING normalizations share these so a quoted
# dangerous verb (`echo "rm -rf /"`) is ignored WHILE a quoted target
# (`rm -rf '/'`) is still seen — contradictory needs that one view cannot serve.
_QUOTED_SPAN_RE = re.compile(r"'[^']*'|\"[^\"]*\"")


def _verb_view(cmd: str) -> str:
    """Comment → spaces, quoted SPANS → underscores (content destroyed). A
    dangerous VERB living inside a quote is then not seen as a command, killing
    false positives like `git log --grep="rm -rf /"`. Length-preserving."""
    s = _COMMENT_RE.sub(lambda m: " " * len(m.group(0)), cmd)
    return _QUOTED_SPAN_RE.sub(lambda m: "_" * len(m.group(0)), s)


def _target_view(cmd: str) -> str:
    """Comment → spaces, quote CHARS → spaces (content kept). A quoted TARGET
    like `rm -rf '/'` is still seen as `/` at a word boundary. Length-preserving,
    so its offsets align with the verb view for per-segment pairing."""
    s = _COMMENT_RE.sub(lambda m: " " * len(m.group(0)), cmd)
    return s.replace("'", " ").replace('"', " ")


def _segment_spans(view: str):
    """(start, end) of each list/pipeline segment, by offset — so the verb view
    and the target view (same length) are sliced at the same boundaries."""
    spans, start = [], 0
    for m in _CONNECTOR_RE.finditer(view):
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(view)))
    return spans


def _reason(cmd: str):
    """Return an actionable block reason, or None to allow. Ordered: rm first
    (most common catastrophic), then device writes, then remote-exec / perms.
    rm/chmod recursion is matched against the SAME segment as its target, so a
    system dir living in another segment, a comment, or an `echo` arg cannot
    false-trip the gate; self-contained patterns run over the whole command.

    Two views (same length, offset-aligned): the VERB view masks quoted spans so
    a dangerous verb quoted as a literal string (`git log --grep="rm -rf /"`) is
    not read as a command; the TARGET view keeps quote content so `rm -rf '/'`
    is still caught. (A verb quoted in isolation, `"rm" -rf /`, is the documented
    not-airtight residual.)"""
    vv = _verb_view(cmd)
    tv = _target_view(cmd)
    spans = _segment_spans(vv)
    if _RM_NOPRESERVE.search(vv):
        return ("`rm --no-preserve-root` — that flag exists only to enable a root "
                "wipe. Remove it; target a specific subpath.")
    if any(_RM_RECURSIVE.search(vv[s:e]) and _DANG_TARGET.search(tv[s:e])
           for s, e in spans):
        return ("recursive `rm` targeting a root / system / bare-home path. Target "
                "a specific project subpath instead (e.g. ./build, /tmp/<name>).")
    if _FORKBOMB.search(vv):
        return "fork bomb (`:(){ :|:& };:`) — would exhaust process table."
    if _DD_DEV.search(vv):
        return "`dd` writing to a raw block device (/dev/...) — would destroy a disk."
    if _MKFS.search(vv):
        return "`mkfs` on a block device — would format/erase a filesystem."
    if _REDIR_DEV.search(vv):
        return "redirect overwriting a raw block device (/dev/...)."
    if _SHRED_DEV.search(vv):
        return "`shred` on a raw block device — irreversible disk wipe."
    if _WIPEFS.search(vv):
        return "`wipefs`/`sgdisk` on a block device — would erase partition signatures."
    if _CURL_SH.search(vv):
        return ("piping a remote download straight into a shell (`curl ... | sh`) — "
                "download to a file, inspect, then run.")
    if any(_CHMOD_RECURSIVE.search(vv[s:e]) and _DANG_TARGET.search(tv[s:e])
           for s, e in spans):
        return "recursive chmod/chown on a root / system path — would break the host."
    if _CRIT_OVERWRITE.search(vv):
        return "overwrite of a critical system file under /etc."
    return None


def core(data: dict):
    """Compliance core: None ⇒ allow; str ⇒ block reason. Only gates Bash tool
    calls; anything else (and empty commands) passes."""
    if data.get("tool_name") != "Bash":
        return None
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not isinstance(cmd, str) or not cmd.strip():
        return None
    return _reason(cmd)


def main() -> int:
    # Compliance wrapper: fail-closed on its own errors, fail-open on absent input,
    # honors the enabled gate; blocks with exit 2 + reason when core returns a str.
    hook_runtime.run_compliance_hook(_NAME, core)
    return 0


if __name__ == "__main__":
    sys.exit(main())
