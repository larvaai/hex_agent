---
name: hs-think:brainstorm
description: Brainstorm solutions with honest trade-off analysis — ideation, architecture decisions, technical debate, feasibility exploration. Use before committing to an approach.
category: think
license: AGPL-3.0
keywords: [brainstorm, solutions, honest, trade-off, analysis, ideation]
when_to_use: "Use before committing to an approach."
argument-hint: "<question> [--diverge | --converge | --critique] [--quick]"
user-invocable: true
allowed-tools: [Bash, Read, Write, Glob, Grep, Task, SlashCommand]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs-think:brainstorm — verified solution exploration

Divergent exploration, trade-off debate, convergence to a recommendation — via the `brainstormer`
agent. Does **NOT** implement, does **NOT** write code. Pure advisor, not executor.

**General rules** (YAGNI/KISS/DRY, Evidence Filter) at
`harness/rules/verification-mechanism.md` — read before running any mode.

## Modes and flags

| Flag | Effect | When to use |
|---|---|---|
| _(default)_ | full diverge → converge | open question, direction not yet known |
| `--diverge` | exploration phase only, no convergence | need multiple options, not ready to commit |
| `--converge` | skip diverge, go straight to trade-off + recommendation | already have ≥2 options, need a verdict |
| `--critique` | adversarial pass: steelman → assumption attack → failure modes → verdict | have a specific idea/approach, want to challenge it before committing |
| `--quick` | single-pass, skip research phase | simple question, low risk |

## Standard procedure (diverge → converge)

1. **Scout** (required): use `hs:scout` to read related code, `docs/`, active `plans/`.
   Summarize 3-6 bullets for the user before asking. No scout = no brainstorm.
2. **Discovery**: use `AskUserQuestion` to extract: expected output, acceptance criteria,
   scope boundary, hard constraints, touchpoints. Loop until all 5 items are specific.
3. **Scope check**: request describes ≥3 independent concerns → decompose into sub-projects,
   brainstorm each separately, do not bundle them together.
4. **Research** (skipped with `--quick`): spawn `brainstormer` agent to explore options —
   read external documentation, query real schema/data if the decision depends on it.
5. **Analysis**: `brainstormer` presents 2-3 directions, compared across specific dimensions
   (complexity, cost, latency, maintainability, second-order effects).
   Technical details → `references/divergence-techniques.md`.
6. **Debate**: present each option with its trade-offs and your recommendation in visible
   response text *first*, then use `AskUserQuestion` to capture the choice — never offer an
   option you have not described in the response (extended-thinking analysis is invisible to
   the user). Challenge preferences, iterate to consensus.
7. **Consensus + Decision**: finalize the approach, document the decision. Details →
   `references/convergence-and-decision.md`. Architecture call →
   `python3 harness/scripts/decision_register.py --append-alloc ...` to record DEC.
8. **Report**: create a markdown report in `plans/reports/` (see "Boundaries").
9. **Plan handoff**: if brainstorm converged and the user wants to continue, `AskUserQuestion`
   proposes `/hs:plan` (fast|hard, `--tdd` if refactoring core logic).

## Mode --critique (adversarial)

Load `references/critique-protocol.md`. Steps:

1. **Steelman**: present the strongest version of the idea — no straw-manning.
2. **Assumption attack**: list ≥3 implicit assumptions; attack each with a counter-scenario.
3. **Failure modes**: predict ≥3 ways the approach breaks in practice (operational, security,
   scale, maintenance). Each failure: 1 sentence scenario + 1 sentence consequence.
4. **Verdict**: Adopt / Adopt-with-guard / Reject — with 2-3 sentences of reasoning.
5. If Adopt-with-guard or Reject → propose an alternative or conditions for reconsideration.

`--critique` never skips scout: attacks must be grounded in real code, not hypothetical targets.

## HARD-GATE (real wiring)

- `brainstormer` agent (`harness/plugins/hs/agents/brainstormer.md`) performs
  divergent exploration; the skill is the orchestrator, the agent is the executor.
- Convergence on an architecture call → must be recorded via
  `python3 harness/scripts/decision_register.py` — prevents re-litigation.
- Report must be in `plans/reports/` — CI invariant forbids markdown outside
  `plans/` and `docs/` (CLAUDE.md rule #5).
- No gate blocks stage; but `/hs:plan` generated from here will trigger
  `harness/hooks/gate_stage.py` at ship time.

## Output language

Generated output (reports, docs, human-facing summaries) follows `harness/data/output.yaml`. Read its `language:` value (default `vi`) and write the prose in that language. Before finalizing, apply `harness/rules/humanizer-and-anti-ai-tells.md`: strip AI-writing tells, and when `language: vi`, also strip the Vietnamese translation-tells. Evidence is never translated or rewritten: keep `file:line` references, IDs, SHAs, numbers, and verbatim quotes exactly as found.

## Boundaries

- Do NOT implement, do NOT write code, do NOT modify harness files.
- Do NOT finalize an approach without presenting trade-offs — a recommendation without evidence
  is treated as a violation of the Evidence Filter (`harness/rules/verification-mechanism.md`).
- Architecture call finalized → record DEC via `decision_register.py`; when revisiting old tension
  read the register first, do not relitigate.
- Report: `plans/reports/<slug>-brainstorm-report.md` (naming from `## Naming`
  in the hook's context injection); use `hs-think:sequential-thinking` if the problem
  requires multi-step analysis with revision.
- On completion: return the absolute path to the report + suggest the next step
  (further validation / `/hs:plan` / stop).

## Workflow position

**Typically after:** `hs:debug` (brainstorm solutions for a diagnosed problem),
`hs:scout` (brainstorm after gaining a codebase picture).
**Typically before:** `hs:plan` (plan the agreed approach).
**Related:** `hs-research:research` (deep research on one option), `hs-think:sequential-thinking`
(multi-step analysis with revision).

## Interview rigor (voice knobs)

Read three knobs from `harness/data/terminal-voice.yaml` (resolved by `voice_prefs.py`, injected at
session start) and let them shape how hard you interrogate the idea, not the design doc:

- `interview_rigor` (light | standard | **deep**) — at `deep`, challenge assumptions harder, push
  more alternatives, and probe more failure modes / edge-cases before converging; at `light`,
  surface only the decisive trade-offs.
- `action_prompting` (minimal | standard | proactive) — at `proactive`, offer more next-step
  suggestions at turn boundaries.
- `detail_level` (concise | standard | verbose) — sizes discussion prose + follow-up count (turn
  verbosity only; the summary report's length stays governed by `output.yaml`).
