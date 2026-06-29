---
name: hs-think:sequential-thinking
description: Multi-step analysis with revision — decompose complex problems, verify hypotheses, adjust direction mid-stream. Use when scope is unclear, reasoning needs a trace, or errors must be caught early.
category: think
license: AGPL-3.0
keywords: [sequential-thinking, multi-step, analysis, revision, decompose, complex]
when_to_use: "Use when scope is unclear, reasoning needs a trace, or errors must be caught early."
argument-hint: "<problem> [--report]"
user-invocable: true
allowed-tools: [Read, Write, Glob, Grep, Bash]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs-think:sequential-thinking — verified sequential reasoning

Step-by-step analysis with the ability to revise, branch, and converge. Does **not** implement
code. Does not write files outside `plans/reports/`. The primary output is a labeled Thought
sequence and a report if the user requests one.

**Evidence rule** at `harness/rules/verification-mechanism.md` — a claim not anchored to
`file:line` or real command output → tag `[UNVERIFIED]`; subsequent steps must not build on it.

## When to use

- Decomposing a complex problem where scope is unclear or emerges gradually
- Reasoning trace needs to be public so the user can review / catch errors early
- Hypotheses need verification before transitioning to `hs:plan` or `hs:debug`
- Architecture decision with multiple parallel hard constraints
- Stuck in a loop — `hs-think:sequential-thinking` forces externalized thinking

## Modes

| Mode | When | Behavior |
|---|---|---|
| `explicit` (default) | scope is unclear, user wants to follow along | Thought markers displayed |
| `implicit` | task is clear, thinking supports internal work | No markers printed, result delivered directly |

Flag `--report`: save the Thought sequence as a report in `plans/reports/`.

## Structure of each Thought

```
Thought N/M [label]: [content]
```

**Labels required when a special event occurs:**

| Label | When |
|---|---|
| `[REVISION of Thought X]` | New insight invalidates a previous Thought X |
| `[BRANCH A / BRANCH B]` | Exploring ≥2 parallel directions |
| `[CONVERGENCE]` | Integrating branches, selecting a direction |
| `[HYPOTHESIS]` | Proposing a hypothesis that needs testing |
| `[VERIFICATION]` | Result of testing a hypothesis |
| `[META]` | Observing the thinking process itself — use when going in circles |
| `[FINAL]` | Last Thought, solution is fully qualified |

## Procedure

1. **Initial estimate** — select total N (initial M) based on perceived complexity.
   `Thought 1/N: [initial analysis]`

2. **Dynamic adjustment** — after each Thought:
   - More complex than expected → increase M
   - Simpler than expected → decrease M
   - Major revision encountered → add label, assess downstream impact (see `references/patterns.md`)

3. **Branch when needed** — maximum 2-3 branches at a time; convergence is required before opening a new branch.
   Load `references/patterns.md` for trade-off evaluation and hypothesis testing patterns.

4. **Stop when conditions are met** — place `[FINAL]` only when:
   - Solution has been verified
   - All hard constraints have been addressed
   - No unaddressed uncertainty remains
   - Load `references/advanced.md` if Spiral Refinement or Parallel Constraint Satisfaction is needed

5. **Report (optional)** — if `--report` flag or user requests it: summarize the reasoning →
   `plans/reports/<slug>-sequential-thinking-<date>.md`. Return the absolute path.

## Boundaries

- Do NOT write code, do NOT implement.
- Do NOT write markdown outside `plans/reports/` (CLAUDE.md rule #5).
- Claims in Thoughts must be anchored to `file:line` or command output — no anchor → `[UNVERIFIED]`.
- If the problem needs multi-direction brainstorming: suggest `hs-think:brainstorm`.
- If reasoning leads to a plan: suggest `hs:plan` (do not open it automatically).
- If reasoning leads to a bug root-cause: suggest `hs:debug`.

## Wiring

This skill is a **pure reasoning scaffold** — no harness gate blocks stage.
Emits no gate-required artifact; does not trigger `harness/hooks/gate_stage.py`.

Cross-refs when reasoning needs to escalate:
- `hs-think:brainstorm` — when more option divergence is needed
- `hs:plan` — when reasoning has converged and an action plan is needed
- `hs:debug` — when reasoning focuses on bug root-cause
- `hs-think:problem-solving` — when stuck and a hard structured reframe is needed

## Workflow position

**Typically called from:** `hs-think:brainstorm` (complex sub-problem), `hs:plan` (internal
constraint analysis), `hs:debug` (multi-step root-cause trace).
**Typically leads to:** `hs:plan` (if output is an approach), `hs:debug` (if output
is a root-cause), or directly to implementation when reasoning is short enough.
