# Harness contract (always-load, <=60 lines)

## Three posture hooks -- HOOK_CLASS constant in code

| Class | Default | On failure | Config-changeable |
|---|---|---|---|
| telemetry | ON | fail-open, silent | enabled |
| nudge | OFF | fail-open, advisory stderr | enabled |
| compliance | **ON + blocking** | **fail-closed exit 2 + reason** | enabled/mode (advisory opt-in) |

`harness/hooks/harness-hooks.yaml` config CANNOT change the class; it is set in each hook's code.

## Declared gate = real wiring (co-presence)

| Gate in prose | Real hook/file |
|---|---|
| Stage gate push/pr/ship/deploy | `harness/hooks/gate_stage.py` + `harness/data/stage-policy.yaml` |
| Pre-push transport | `harness/install/git-pre-push-hook.sh` (installer places this in `.git/hooks/`) |
| Session attribution | `harness/hooks/session_init.py` |

## Three honest truths (do not over-trust what the harness promises)

1. **Gate = presence gate + role-consistency, NOT authentication**: proves a step
   RAN; pr/ship/deploy also require plan-approval (reviewer in team.yaml AND not
   the author, plan hash normalized) -- raises the cost of fraud, nothing more.
2. **actor = attribution, NOT authentication**: resolved from env
   (CI -> session cache -> HARNESS_USER -> git email -> $USER), spoofable, never
   an authz signal. It answers "recorded as whom", not "proved to be whom".
3. **Gate config is tamper-visible, not tamper-proof**: config can be edited in
   an emergency (tracked in git; diff + trace exposed); `HARNESS_*` env pointing to
   a different config/policy is a known gap (trace names the actual file). Guards
   accidental drift, NOT an insider. fs_guard is a script-path containment helper
   -- it does NOT block raw LLM Write calls; the stage gate only sees
   PreToolUse(Bash), other tools ungated (push still uses pre-push transport); state has no at-rest protection.

## Event-class -> store table

| Event | Store | Retention |
|---|---|---|
| gate_*, session_*, approval, DEC, memory_gap_* | `harness/state/trace/` (JSONL/day) | no rotation |
| usage counters (skill/script) | `harness/state/telemetry/` | rotate at 8MB, 1 generation .bak |
| claim files (acquire/release/reclaim) | `harness/state/claims/` -- RENAME-LIFECYCLE exception: JSON immutable, rename only, audit via trace | tombstone kept, no GC |

Machine-written store: append-only JSONL, no read-modify-write; every record
has actor + ts.

## Autonomy

`HARNESS_AUTONOMY=default|ask_all|god` -- default: hs:cook runs per-phase
autonomously, STOPS to wait for human at plan-approval + ship; ask_all: stops at
every phase; god: does not stop but trace is complete. No level self-ships past
the artifact gate.

## Standards are input

`harness/standards/` receives system-architecture + code-standards when the repo is
cloned locally (one clone per dev, shared standards); hs:plan/hs:cook read these
before starting -- if missing, they stop and prompt to load them (details:
`harness/standards/README.md`). On-demand: `harness/rules/{config-reference,workflow-handoffs,verification-mechanism,tdd-discipline}.md`; skills hs:plan/cook/test.
