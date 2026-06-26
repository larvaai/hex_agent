#!/usr/bin/env python3
"""stage_detector.py — map a Bash command to the SDLC stage it advances.

detect_stage(command) returns one of push|commit|pr|ship|deploy, or None.
Patterns are BOUNDARY-STRICT: they only match where a command can
actually start — string start or right after `;`, `&`, `|`, `(`, or a
newline. So `echo "git push"` (the string is an argument) and `git pushing`
(word boundary) do NOT match.

Wrapper reach (hardening): a wrapper AT a command head is unwrapped and
recursed — `sh -c 'git push'`, `bash -c "..."`, `eval '...'` — and a
path-qualified binary (`/usr/bin/git`, `./gh`) is still that binary. A wrapper
name INSIDE a quoted argument is NOT unwrapped (boundary rule), and obfuscation
the unwrap cannot reach (unquoted eval args, `$var` indirection, base64) stays
the floor. The git pre-push hook still covers the push stage at the transport
level regardless of how the push command was spelled. guess_stage() additionally
samples a NARROW set of free-floating words — only the ship/deploy class
(release / publish / ship / deploy*, see _GUESS_PATTERNS) — as advisory trace
(never a gate signal). push/commit/pr words are deliberately NOT sampled: they
are far too common in ordinary prose to be signal, so a wrapper-hidden
`sh -c 'git push'` stays invisible to this guess channel and is covered ONLY by
the transport-level pre-push hook, not by the trace sample.
"""

import re

# Where a command head can begin: start-of-string or right after a shell
# separator. Quoted strings never satisfy this, which is the whole point.
# Backtick opens a command substitution and `{` a brace group — both run
# their body, so both are command positions. A backtick inside single quotes
# is literal text; treating it as a boundary anyway can only over-detect
# (false block), never let a real stage command through.
_BOUNDARY = r"(?:^|[;&|({\n`])\s*"

# `do`/`then`/`else` introduce a command position inside compound statements
# (loop and conditional bodies). Whole words only — `dosomething` is a name.
_KEYWORDS = r"(?:(?:do|then|else)\s+)*"

# Benign prefixes that leave the following verb a real command head — they
# RUN their argument vector rather than quoting it:
#   * VAR=value assignments, values possibly quoted;
#   * exec-style wrappers (sudo, env, timeout 30, nice -n 10, …) with their
#     own flags. `-u <arg>`/`-g <arg>`/`-p <arg>`/`-n <arg>` are the
#     separated-argument flags these wrappers commonly take (`-p` is npx's
#     --package); bare numbers cover timeout durations. The package-runner
#     wrappers (`npx`/`bunx`, and the two-token `pnpm dlx`/`yarn dlx`) RUN the
#     following tool, so `npx vercel deploy` is a real deploy — they belong
#     here. `sh -c '…'` stays out by design: its payload is a quoted string, not
#     a command head (documented limitation).
_PREFIXES = (
    r"(?:(?:\w+=(?:'[^']*'|\"[^\"]*\"|\S*)"
    r"|(?:sudo|env|command|nohup|nice|stdbuf|timeout|time|xargs|npx|bunx)"
    r"(?:\s+(?:-[ugpn]\s+\S+|-{1,2}[\w.,:=/+-]+|\d+(?:\.\d+)?[smhd]?))*"
    r"|(?:pnpm|yarn)\s+dlx(?:\s+(?:-{1,2}[\w.,:=/+-]+))*"
    r")\s+)*"
)

# A binary may be named by a path: `/usr/bin/git`, `./gh`, `bin/vercel`. The
# verb head is still that tool, so allow an optional path prefix before it.
_PATHPFX = r"(?:[\w./+-]*/)?"

_HEAD = _BOUNDARY + _KEYWORDS + _PREFIXES + _PATHPFX

# Ordered: first hit wins. More specific stages (pr/ship/deploy) before the
# generic git verbs is not required — patterns are mutually exclusive — but
# keep deploy CLIs grouped for readability.
# `\b` treats `-` as a boundary, so `push\b` would match `push-helper`; the
# lookahead requires a real end-of-word (whitespace/end/separator) instead.
_EOW = r"(?![\w-])"

_STAGE_PATTERNS = [
    ("push", re.compile(_HEAD + r"git\s+(?:-[-\w]+(?:[= ]\S+)?\s+)*push" + _EOW)),
    ("commit", re.compile(_HEAD + r"git\s+(?:-[-\w]+(?:[= ]\S+)?\s+)*commit" + _EOW)),
    ("pr", re.compile(_HEAD + r"gh\s+pr\s+(?:create|merge|ready)" + _EOW)),
    ("ship", re.compile(_HEAD + r"gh\s+release\s+create" + _EOW)),
    ("ship", re.compile(_HEAD + r"(?:npm|pnpm|yarn)\s+publish" + _EOW)),
    # Polyglot package release verbs — each unambiguously ships a package; the
    # in-session gate is their only gate (no git transport to backstop).
    ("ship", re.compile(_HEAD + r"cargo\s+publish" + _EOW)),
    ("ship", re.compile(_HEAD + r"poetry\s+publish" + _EOW)),
    ("ship", re.compile(_HEAD + r"twine\s+upload" + _EOW)),
    ("ship", re.compile(_HEAD + r"gem\s+push" + _EOW)),
    ("ship", re.compile(_HEAD + r"dotnet\s+nuget\s+push" + _EOW)),
    ("deploy", re.compile(
        _HEAD + r"(?:wrangler|vercel|netlify|firebase|fly|flyctl|railway)\s+deploy" + _EOW)),
    ("deploy", re.compile(_HEAD + r"(?:npm|pnpm|yarn)\s+(?:run\s+)?deploy" + _EOW)),
]

# Free-floating words worth SAMPLING (advisory `stage_guess` trace event):
# they appear anywhere — file names, sh -c payloads, prose — so they are far
# too noisy to gate on, but exactly the data that reveals evasion patterns.
_GUESS_PATTERNS = [
    ("ship", re.compile(r"\b(?:release|publish)\b")),
    ("ship", re.compile(r"\bship\b")),
    ("deploy", re.compile(r"\bdeploy\w*\b")),
]


# Wrapper unwrap (boundary-anchored, so a wrapper name inside a quoted argument
# is NOT unwrapped): `sh -c '<payload>'` / `bash -c "<payload>"` and
# `eval '<payload>'` hide the real command head in a quoted string the
# boundary-strict patterns cannot see. detect_stage recurses, so a nested
# `sh -c 'sh -c "git push"'` resolves by repeated unwrap. Obfuscation the unwrap
# does NOT reach (unquoted eval args, `$var` indirection, base64) stays the
# documented floor — the transport pre-push hook backstops push regardless.
_WRAP_C_RE = re.compile(
    _BOUNDARY + _KEYWORDS + _PREFIXES +
    r"(?:[\w./+-]*/)?(?:sh|bash|dash|zsh|ash|ksh)(?:\s+-\w+)*\s+-c\s+"
    r"(['\"])(.*?)\1", re.S)
_EVAL_RE = re.compile(
    _BOUNDARY + _KEYWORDS + _PREFIXES + r"eval\s+(['\"])(.*?)\1", re.S)


def detect_stage(command):
    """Stage name for a command that REALLY advances that stage, else None."""
    if not command or not isinstance(command, str):
        return None
    for stage, pattern in _STAGE_PATTERNS:
        if pattern.search(command):
            return stage
    # No direct head: try unwrapping a boundary-anchored wrapper and recurse.
    for rx in (_WRAP_C_RE, _EVAL_RE):
        for m in rx.finditer(command):
            inner = detect_stage(m.group(2))
            if inner:
                return inner
    return None


def guess_stage(command):
    """Advisory-only guess from free-floating stage words. Never a gate
    signal — feeds the `stage_guess` trace sampling. None when nothing hints."""
    if not command or not isinstance(command, str):
        return None
    hard = detect_stage(command)
    if hard:
        return hard
    for stage, pattern in _GUESS_PATTERNS:
        if pattern.search(command):
            return stage
    return None
