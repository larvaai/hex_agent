---
name: hs-think:problem-solving
description: Structured unblocking — identify the block type, choose the right technique, reframe before resuming implementation. Use when stuck in a loop, complexity escalates, or a hypothesis fails 3+ times.
category: think
license: AGPL-3.0
keywords: [problem-solving, structured, unblocking, identify, block, type]
when_to_use: "Use when stuck in a loop, complexity escalates, or a hypothesis fails 3+ times."
argument-hint: "<problem> [--report]"
user-invocable: true
allowed-tools: [Read, Write, Glob, Grep, Bash]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs-think:problem-solving — structured unblocking

Identify the type of block -> choose a technique -> apply systematically -> exit the loop.
**No implementation.** No file writes outside `plans/reports/`.

**Evidence rule** in `harness/rules/verification-mechanism.md` — insights from a technique
must be anchored to a `file:line` or a concrete observation; unanchored -> tag `[UNVERIFIED]`.

## When to use

- Complexity escalating: same thing implemented 5+ ways, special cases keep growing
- Creative block: conventional solutions are not enough, a breakthrough is needed
- Recurring pattern: same problem appearing in many places, continuously reinventing wheels
- Forced hypothesis: feeling that "there is only one way", unable to question the premise
- Scale uncertainty: not sure the design will work in production
- **Broken code / failing tests -> use `hs:debug` instead** (not this skill)

## Quick dispatch — symptom -> technique

| Symptom | Technique | Reference |
|---|---|---|
| Same thing implemented 5+ ways, special cases growing | Simplification Cascades | `references/simplification-cascades.md` |
| Conventional solutions not enough, breakthrough needed | Collision-Zone Thinking | `references/collision-zone-thinking.md` |
| Same problem recurring across domains, done this before | Meta-Pattern Recognition | `references/meta-pattern-recognition.md` |
| Solution feels forced, "must do it this way" | Inversion Exercise | `references/inversion-exercise.md` |
| Not sure if it will scale | Scale Game | `references/scale-game.md` |
| Two directions, reasoning exhausted, metric is mechanical | **Empirical bake-off** → `hs-think:bakeoff` (not a reframing technique — decide by running) |
| Type of block unclear | Flowchart dispatch | `references/when-stuck.md` |

## Process (hard)

1. **Identify the type of block** — match against the Dispatch table; if unclear, load
   `references/when-stuck.md` and follow the flowchart. Do not skip this step — applying the
   wrong technique wastes more time.

2. **Load the reference** — open the reference file for the chosen technique. References contain
   the detailed process, examples, and red flags. Do not apply a technique from memory.

3. **Apply systematically** — follow the technique's process; record:
   - Input (specific problem, observed constraints)
   - Steps applied
   - Insights gained (anchored to `file:line` or a concrete observation)
   - What could not be applied and why

4. **Check results** — does the insight resolve the original block?
   - Yes -> propose next step (`hs-think:sequential-thinking`, `hs:plan`, or implement)
   - No -> try another technique or combine them (see Combinations table below)

5. **Record** — if `--report` flag is set or the scope is complex: summarize insights ->
   `plans/reports/<slug>-problem-solving-<date>.md`; return the absolute path.

## Combining techniques

Some blocks require multiple techniques:

| Combination | When |
|---|---|
| Simplification + Meta-Pattern | Recognize pattern -> simplify all instances |
| Collision + Inversion | Force a metaphor -> invert its assumptions |
| Scale + Simplification | Test extremes -> reveal what can be removed |
| Meta-Pattern + Scale | Universal pattern -> test at extremes |

## Boundaries

- NO implementation, NO code edits, NO writes outside `plans/reports/`.
- If the problem is **broken code / failing tests**: use `hs:debug` — this skill does not
  replace hs:debug; debugging is its own domain with a hypothesis loop and root-cause chain.
- If the problem requires **multi-step analysis with revision**: use `hs-think:sequential-thinking`.
- If the problem requires **exploring multiple directions with trade-offs**: use `hs-think:brainstorm`.
- On completion: return insights anchored to evidence and a clear next-step recommendation.

## Wiring

This skill is a **reframing scaffold** — it does not trigger a harness gate and does not emit
a gate-required artifact. Do not call `harness/hooks/gate_stage.py`.

Cross-refs when the skill's output leads to action:
- `hs-think:sequential-thinking` — when the insight needs further multi-step analysis
- `hs-think:brainstorm` — when the insight opens multiple design directions to evaluate
- `hs:debug` — when the block is actually a bug (switch to debug, do not use this skill)
- `hs:plan` — when the insight is clear enough to create an action plan

## Workflow position

**Typically called from:** `hs-think:sequential-thinking` (when stuck in a reasoning chain),
`hs:debug` (when a hypothesis fails 3+ times), `hs-think:brainstorm` (complex sub-problem).
**Typically leads to:** `hs-think:sequential-thinking` (if the insight needs further validation),
`hs:plan` (if the insight is ready for action), or directly to implementation once the block is resolved.
