---
name: hs:cook
description: Execute an approved plan phase by phase — TDD red→green, generate verification/review-decision artifacts, trace every step.
category: core
license: AGPL-3.0
keywords: [cook, execute, approved, plan, phase, tdd]
when_to_use: "Execute an approved plan phase by phase — TDD red→green, generate verification/review-decision artifacts, trace every step."
argument-hint: "<plan-path> [--phase <id>] [--parallel]"
user-invocable: true
allowed-tools: [Bash, Read, Write, Edit, MultiEdit, Grep, Glob, Task]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs:cook — execute plan by phase

Input: path to a human-approved plan. No approved plan → return to hs:plan
(gate `require_plan` blocks hard stages if you try to skip this).

**Context isolation:** cook should run from a CLEAN context —
ideally `/clear` after approving the plan, then `/hs:cook <absolute-path>`.
Planning carryover (research, debate, red-team) shifts cook's focus.
The nudge `cook_isolation_nudge` reminds you if plan+cook are detected in the same session (advisory,
does not block). Details: `references/context-isolation.md`;
backing: `harness/rules/workflow-handoffs.md` #5.

**General rules**: `harness/rules/tdd-discipline.md` (red→green, 100%
pass) + `harness/rules/verification-mechanism.md` (evidence,
posture gate). Read first. Gates that require human review (per-phase, review-decision) apply
`harness/rules/plannotator-review-gates.md` — diffs use `review`.

## Step 0 — Standards are input

Same as hs:plan: read `harness/standards/` before writing code. Code follows
the shared `code-standards.md` — that is why the harness exists on this machine.

## Per-phase loop

1. **Conformance checklist**: read the phase file; list files to create/modify; verify naming/format
   match standards; any deviation from the plan → STOP and ask, do not silently change.
   Details: `references/implement-test-loop.md` (5-item checklist + verify-after-file).
2. **TDD red→green**: follow tdd-discipline rule — test-first intentional FAIL →
   implement until green → re-run full suite → paired commit test+module.
   Sub-steps 3.T / 3.I / 3.V + fix-loop: `references/per-phase-tdd.md`.
   On green, before advancing, a **simplification pass**: if the change grew a special
   case or duplicated an existing pattern, collapse it (suite stays green). Pattern
   library: `harness/plugins/hs-think/skills/problem-solving/references/simplification-cascades.md`.
3. **Verify before done**: before writing artifact and advancing phase — suite green,
   no new lint/type errors, every acceptance criterion has evidence (file:line),
   no silent contract change. If a side effect appears → STOP AskUserQuestion with 2-4
   choices; do not self-patch. Details: `references/verify-before-done.md`.
4. **Artifacts (machine-written JSON)**: at end of phase write
   `plans/<plan>/artifacts/verification.json` (+ `review-decision.json` when review occurred;
   schema in `harness/schemas/`). Gate reads artifact from **filesystem**, no commit needed —
   `.gitignore plans/**/*` hides new plan dirs so artifacts do NOT auto-commit
   (correct policy, not a bug; see rule verification-mechanism).
5. **Trace**: significant steps emit events via `harness/hooks/trace_log.py`
   (append_event — actor auto-resolved, do NOT hand-craft JSONL). Carve-out: phases declared
   stateless (frontmatter `stateless: true` or comment `# stateless-by-design`)
   → skip trace for that phase; gate_stage still runs (trace is telemetry fail-open,
   not a compliance gate).

## Pause cadence — HARNESS_AUTONOMY

| Level | Behavior |
|---|---|
| `default` | run per-phase sequence automatically; **pause at 2 checkpoints: plan approval + ship** |
| `ask_all` | pause after EVERY phase |
| `god` | no pauses (trace still records fully — autonomy comes with a trace) |

Resolve the level deterministically — do not eyeball the env. At each boundary run
`python3 harness/scripts/autonomy_policy.py --boundary <plan_approval|phase|ship>` and
pause only when it prints `pause` (`--show` emits the resolved level + full matrix). A
missing/invalid level falls back to `default`.

All levels do NOT self-ship: stage `push|pr|ship|deploy` always goes through artifact gate.

When pausing for human (`ask_all` after a phase, or before writing `review-decision.json`):
ask AskUserQuestion with 3 options [Review directly (Plannotator) / Approve / Reject];
choosing (1) → `plannotator_surface.py review <diff>` (rule `plannotator-review-gates.md`).

## Parallel execution (opt-in `--parallel`)

Default is **sequential** (everything above). `--parallel` lets independent phases cook
concurrently to save wall-clock — without ever weakening a gate or trusting a subagent on
sight. Full protocol: `references/parallel-execution.md`. Backing: `harness/rules/orchestration-protocol.md`.

- **Resolve the opt-in deterministically** — do not eyeball it. `--parallel` flag >
  `HARNESS_COOK_PARALLEL` env > `cook.parallel` config (`harness/data/cook.yaml`) > default
  OFF. `cook.parallel_max` (advisory) caps fan-out — the agent applies it; the planner emits the partition, not the cap. Run
  `python3 harness/scripts/cook_parallel_plan.py --root . --phases-json <f> --expand`
  (add `--parallel` to force ON) → it prints `parallel_enabled` + the safe partition.
- **Partition before fanning out**: the partitioner groups only phases marked
  `parallel_safe` in their phase frontmatter **whose `owns` globs are disjoint**. Any
  ownership overlap (same file / generated artifact / migration / shared config) demotes
  BOTH phases to sequential and is reported in `conflicts` — **never parallel-edit a shared
  path, never fall back silently**.
- **Delegate**: each parallel slice → one `developer` subagent in an isolated **worktree**,
  given the full delegation context (task · read/modify globs · acceptance · constraints · env).
- **Verify every slice — MANDATORY, never trust on sight** (two tiers):
  1. cook **self-verifies**: re-run that slice's tests + lint, read its diff against the
     phase's acceptance criteria;
  2. risky slice → spawn an **independent verifier subagent** (`independent-revalidator` or
     `code-reviewer`) that re-derives correctness from the diff alone.
  A slice that fails either tier does NOT merge — it returns to sequential rework.
- **Integration barrier**: after all verified slices merge, run the **full suite serially**
  (the real green gate) before writing `verification.json` and committing. Parallelism only
  speeds the build; the integration gate stays serial and strict.
- Gates are unchanged: `gate_stage.py` still requires the artifact; `--parallel` never bypasses it.

## HARD-GATE (real wiring)

`harness/hooks/gate_stage.py` (PreToolUse Bash, compliance, fail-closed) blocks
hard stages when `verification.json` is missing (block exit 2 with creation path) /
review-decision verdict != PASS. Gate is a presence gate (rule
verification-mechanism) — role-check is in plan_approval, not in this gate.

## References (load on demand)

| Drawer | Content | When to load |
|---|---|---|
| `references/per-phase-tdd.md` | Sub-steps 3.T/3.I/3.V, fix-loop, stateless phase | When per-phase TDD detail is needed |
| `references/implement-test-loop.md` | 5-item conformance checklist, verify-after-file | When the code-check order needs reminding |
| `references/context-isolation.md` | Why isolation matters, /clear procedure, exceptions | When plan+cook are in the same session |
| `references/parallel-execution.md` | Opt-in `--parallel` protocol: resolve → partition → delegate → verify → integration barrier | When cooking with `--parallel` |
| `references/verify-before-done.md` | 5 verification invariants, end-of-phase checklist, side-effect check | When preparing to advance a phase |
| `references/subagent-patterns.md` | Task-tool snippets for every subagent role: researcher, scout, review, adversarial, simplify, git | When selecting which subagent pattern to use in a workflow step |
| `references/workflow-steps.md` | Step-by-step workflow for all modes (interactive/auto/fast/parallel/no-test/code) including review gates | When the full mode-specific step sequence needs reminding |
| `_shared/workflow-artifacts.md` | JSON artifact schema (context-snippets/risk-gate/verification/review-decision/adversarial-validation), approval rules, redaction policy | When writing or validating review/finalize artifacts |

## Observe checkpoint (end-of-work)

When cook finishes, if this run surfaced a judgment a counter cannot see, record ONE closed-vocab
signal so the harness learns from it — emit only a REAL observation, not every run. Vocabulary lives
in `harness/data/observation-signals.yaml`.

```bash
python3 harness/scripts/emit_observation.py --skill hs:cook \
    --signal <gate-repeat-block|plan-revised-post-approval|thin-evidence> \
    --payload "<one line: what happened>"
```

Surfaces in the read-only `observations` lens (honesty-gated). Skip it silently when nothing notable
happened — a fabricated signal is worse than none.

## Boundaries

- Do not modify `harness-hooks.yaml`/`stage-policy.yaml` to pass the gate — these files are git-tracked;
  any change is visible in the diff + trace. Genuinely stuck → ask the human.
- Work that arises outside the plan scope → BACKLOG.md; do not steer the plan mid-flight.
- Mid-phase, if the planned direction stalls and 2-3 alternatives are measurably comparable, escalate to
  `hs-think:bakeoff` (probe the alternatives, decide by numbers) instead of grinding one direction — then resume cook.
