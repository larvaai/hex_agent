---
name: hs:plan
description: Create a verified implementation plan — research, constraint-scan, phase design, red-team, and validate before cook.
category: core
license: AGPL-3.0
keywords: [plan, create, verified, implementation, research, constraint-scan]
when_to_use: "Create a verified implementation plan — research, constraint-scan, phase design, red-team, and validate before cook."
argument-hint: "[fast | hard] [--tdd]"
user-invocable: true
allowed-tools: [Bash, Read, Write, Edit, Grep, Glob, Task]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs:plan — verified planning

Creates a plan under `plans/<timestamp>-<slug>/` (plan.md + phase files). The plan is
the contract for hs:cook: cook runs only when the plan has been approved by a HUMAN.

**General rules** (evidence, two-way Evidence Filter, posture gate) are in
`harness/rules/verification-mechanism.md` — read that first; not repeated here.

**Review gate**: every gate requiring HUMAN approval (red-team, validate, plan approval)
applies `harness/rules/plannotator-review-gates.md` — offer the direct Review option
(Plannotator) before asking the user to read manually.

## Step 0 — Standards are input

Read `harness/standards/` BEFORE planning: `system-architecture.md` +
`code-standards.md` supplied by the user when cloning the harness. The plan must
reference shared standards, not invent its own. Standards missing -> STOP, prompt the
user to load them first (`harness/standards/README.md`). Do not plan on an empty base.

Also read `docs/GLOSSARY.md` — the harness's canonical shared language. Name things
with the settled vocabulary instead of re-coining it; respect its forbidden wording.

## Modes

| Mode | When | Gates |
|---|---|---|
| `fast` | small task, 1-2 files, low risk | skip research + red-team |
| `hard` (default) | real feature/refactor | constraint-scan -> red-team -> validate |

Flag `--tdd` (orthogonal to mode): each phase records the test-first->implement-after
pair explicitly (`harness/rules/tdd-discipline.md`).

## Workflow (hard)

1. **Understand**: read the request, docs, and related code; identify the real scope
   (cut YAGNI). Before decomposing you MUST be able to state each in one concrete
   sentence (use AskUserQuestion to pin any that stay vague): **expected output** (the
   artifact the user sees — path/behavior/endpoint+payload/CLI+flags), **acceptance
   criteria** (inputs→outputs/edge cases that mean "done"), **scope boundary** (what is
   explicitly OUT this round), **non-negotiable constraints** (stack, locations, naming,
   back-compat, perf), **touchpoints** (which existing files/contracts get modified —
   ground options in real paths).
2. **Scope challenge** (skip when `--fast` or task < 20 words and unambiguous): ask
   the user 3 questions — what existing code can be reused? what is the minimal
   change set? does the plan touch >8 files / >2 new classes / >3 phases? ->
   choose EXPANSION / HOLD / REDUCTION via AskUserQuestion before research.
3. **Research** (skip when `--fast` or a researcher report already exists): load
   `references/research-phase.md` — spawn <=2 `researcher` agents in parallel,
   read `harness/standards/` first; synthesize findings into `plans/<slug>/research/`.
4. **Constraint scan** (required BEFORE finalizing any open decision): load
   `references/constraint-scan.md` — grep `ownership.yaml`, `stage-policy.yaml`,
   `schemas/` to find zone/policy constraints that govern the decision.
5. **Plan**: load `references/phase-decomposition.md` — write plan.md (YAML
   frontmatter + phases + acceptance + rollback) + phase files sufficient for another
   developer to execute. Flag `--tdd`: load `references/tdd-plan-mode.md` — add Tests
   Before / Implement / Tests After / Regression Gate to each phase. Planner
   self-verifies inline: tag `[UNVERIFIED]` on every claim without a `file:line`
   anchor (rule `verification-mechanism.md` — two-way Evidence Filter).
6. **Red-team**: load `references/red-team-gate.md` — adversarial reviewer finds
   failure modes. After applying findings: load `references/verification-roles.md`
   -> Whole-Plan Consistency Sweep.
7. **Validate**: load `references/validate-gate.md` — finalize self-assumed decisions
   + resolve `[UNVERIFIED]` tags. Verification pass (tier Light/Standard/Full by
   phase count) runs before asking the user; load `references/verification-roles.md`
   for role definitions. Mode `interactive` (default) asks via AskUserQuestion;
   `headless` emits a table of "questions + suggested defaults"; `off` skips.
   After propagation: Whole-Plan Consistency Sweep again.
8. **Consistency sweep**: re-read plan.md + ALL phase files; scan for stale
   terms/reversed decisions + **name-honesty/SRP** (do new file/module names
   accurately and completely describe their real responsibility?). If the plan
   coins a new load-bearing term, append a row to `docs/GLOSSARY.md` so the shared
   language grows with the work. **0 unresolved contradictions** before recommending cook.

## Boundaries

- Do NOT write code, do not modify files outside `plans/`.
- Architecture decisions finalized during validate -> record DEC via
  `python3 harness/scripts/decision_register.py --append-alloc ...` — the register
  kills re-litigation: when old tension resurfaces, read the register first.
- Finish: return the **ABSOLUTE PATH** of the plan + recommend next step (additional
  validate / hs:cook / stop). Plan approval belongs to the HUMAN — autonomy at every
  level stops here. Ask for approval via AskUserQuestion with 3 options [Direct Review
  (Plannotator) / Approve / Reject] (rule `plannotator-review-gates.md`);
  "approved" -> record via `plan_approval.py`.
- **Context isolation before cook**: after approval,
  RECOMMEND the user run `/clear` then `/hs:cook <absolute-path-to-plan.md>` —
  planning carryover skews cook; absolute path because `/clear` wipes context
  (a new session can still find the plan). See `harness/rules/workflow-handoffs.md` #5.

## HARD-GATE (real wiring)

Stage `push|pr|ship|deploy` is blocked by `harness/hooks/gate_stage.py` when an active
plan is missing its artifact (`require_plan`, `harness/data/stage-policy.yaml`) — if
the plan does not exist, shipping is not possible. The gate is a presence gate
(rule verification-mechanism).

## Interview rigor (voice knobs)

Read three knobs from `harness/data/terminal-voice.yaml` (resolved by `voice_prefs.py`, injected at
session start) and let them shape the interview, not the artifact:

- `interview_rigor` (light | standard | **deep**) — at `deep`, challenge claims harder and probe
  more gaps / edge-cases / acceptance-criteria holes in the scope-challenge + validate steps; at
  `light`, ask only the blocking questions.
- `action_prompting` (minimal | standard | proactive) — at `proactive`, offer more next-step
  suggestions at turn boundaries.
- `detail_level` (concise | standard | verbose) — sizes interview prose + follow-up count (turn
  verbosity only; generated plan/report length stays governed by `output.yaml`).

## Observe checkpoint (end-of-work)

When the plan is done, if this run surfaced a judgment a counter cannot see, record ONE
closed-vocab signal so the harness learns from it — emit only a REAL observation, not every
run. Vocabulary lives in `harness/data/observation-signals.yaml`.

```bash
python3 harness/scripts/emit_observation.py --skill hs:plan \
    --signal <thin-evidence|red-team-reopened|plan-revised-post-approval|trigger-near-miss> \
    --payload "<one line: what happened>"
```

Surfaces in the read-only `observations` lens (honesty-gated). Skip it silently when nothing
notable happened — a fabricated signal is worse than none.
