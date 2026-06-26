---
name: hs-research:discover
description: Shape an ambiguous problem into a discovery brief for hs:plan — research + brainstorm chain -> direction summary, trade-offs, open questions.
category: research
license: AGPL-3.0
keywords: [discover, shape, ambiguous, problem, discovery, brief]
when_to_use: "Shape an ambiguous problem into a discovery brief for hs:plan — research + brainstorm chain -> direction summary, trade-offs, open questions."
user-invocable: true
argument-hint: "<problem description / feature idea> [--quick]"
allowed-tools: [Bash, Read, Write, Edit, Grep, Glob, Task, WebFetch, WebSearch]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs-research:discover — shape the problem -> discovery brief

Input: a problem description or feature idea (may be very vague). No input ->
`AskUserQuestion`: what is the problem, hard constraints, who is affected, what does
done look like.

**Context isolation:** after the brief is complete, `/clear` is RECOMMENDED before calling
`hs:plan` — discovery research and debate carry heavy context that skews planning.
The `discover_isolation_nudge` nudge prompts when hs-research:discover and hs:plan are detected in
the same session (advisory, fail-open). Backing: `discover_isolation_nudge` +
`harness/rules/workflow-handoffs.md` section Orchestrator (mirrors handoff #5 isolation pattern).

Flag `--quick`: skip hs-research:research, run `hs-think:brainstorm --quick` instead of the full
diverge/critique/converge chain. Use when the problem is simple or context is already sufficient.

## Process

1. **Scout + frame**: read `docs/` (incl. `GLOSSARY.md` for the canonical shared
   language), active `plans/`, relevant codebase. Summarize in
   3-6 bullets for the user. Ask a scoping question if ambiguity spans 2+ dimensions.
   Details -> `references/when-to-discover.md`.

2. **Research** (skip with `--quick`): call `hs-research:research` — central question = the
   framed problem; save report to `plans/reports/`. Use the absolute report path as the
   evidence link in the brief.

3. **Explore options**: call `hs-think:brainstorm --diverge` -> generate 2-4 approaches.
   Then `hs-think:brainstorm --critique` -> 2-lens honest attack.
   Finally `hs-think:brainstorm --converge` -> recommendation + trade-offs.
   (With `--quick`: replace with a single `hs-think:brainstorm --quick` call.)
   **Escalation:** if ≥2 surviving approaches differ on a MEASURABLE axis (latency, size, %pass)
   and reasoning cannot separate them, escalate to `hs-think:bakeoff` — build cheap probes and decide
   by real numbers — instead of guessing the direction in the brief.

4. **Synthesize the brief**: write `plans/<slug>/discovery-brief.md` using the template
   at `references/brief-template.md`. Required sections: problem framing,
   evidence summary (link to research report), option space, chosen direction +
   rationale, open questions, risks, explicitly OUT of scope.

5. **DEC (optional)**: if discovery finalizes an architectural choice ->
   `python3 harness/scripts/decision_register.py --append-alloc ...`.
   Only record architecture-level decisions — not every idea.

6. **Handoff**: return the absolute path to `discovery-brief.md`. Propose
   `AskUserQuestion`: proceed with `/hs:plan <path>` or revise the brief.
   Remind to `/clear` before planning. Chain details -> `references/chain-orchestration.md`.

## Backing

- `harness/rules/workflow-handoffs.md` (section Orchestrator: discover->plan; brief =
  "problem description + constraints" enriching handoff #1; isolation mirrors handoff #5).
- `harness/rules/documentation-management.md` (brief in `plans/`;
  CI invariant bans markdown outside `plans/` or `docs/`).
- `harness/rules/orchestration-protocol.md` (if fan-out to subagents).
- `harness/scripts/decision_register.py` (record DEC in step 5).
- `discover_isolation_nudge` (advisory nudge in `harness/hooks/`;
  referenced by name).
- Component skills: `hs-research:research`, `hs-think:brainstorm`, `hs:plan`,
  `hs-think:problem-solving` (when discovery is blocked).

## Output language

Generated output (reports, docs, human-facing summaries) follows `harness/data/output.yaml`. Read its `language:` value (default `vi`) and write the prose in that language. Before finalizing, apply `harness/rules/humanizer-and-anti-ai-tells.md`: strip AI-writing tells, and when `language: vi`, also strip the Vietnamese translation-tells. Evidence is never translated or rewritten: keep `file:line` references, IDs, SHAs, numbers, and verbatim quotes exactly as found.

## Boundaries

- Do NOT write code, do NOT edit harness files, do NOT create a plan.
- Only output = discovery brief (markdown in `plans/<slug>/`).
  The brief is input for hs:plan — not a replacement for the plan.
- NO hard gate — hs-research:discover does not block any stage. Gates live in
  hs:plan -> hs:cook downstream.
- Scope creep -> add to `BACKLOG.md`, do not expand the brief.
- When discovery is blocked (empty option space, frame does not converge) ->
  call `hs-think:problem-solving` first, then continue.
- On completion: absolute path to brief + list of open questions +
  clear next-step recommendation.

## References (load on demand)

| Drawer | Content | When to load |
|---|---|---|
| `references/brief-template.md` | Discovery brief template, required sections, example | When writing the brief in step 4 |
| `references/chain-orchestration.md` | Call order for hs-research:research / hs-think:brainstorm, flags, handoff to hs:plan | When chain details are needed |
| `references/when-to-discover.md` | When hs-research:discover is needed vs skippable; signs the problem is clear enough | When unsure whether discover is needed |

## Interview rigor (voice knobs)

Read three knobs from `harness/data/terminal-voice.yaml` (resolved by `voice_prefs.py`, injected at
session start) and let them shape the discovery interview, not the brief:

- `interview_rigor` (light | standard | **deep**) — at `deep`, challenge the problem framing harder
  and probe more unknowns / assumptions / success-criteria gaps; at `light`, ask only the blocking
  questions.
- `action_prompting` (minimal | standard | proactive) — at `proactive`, offer more next-step
  suggestions at turn boundaries.
- `detail_level` (concise | standard | verbose) — sizes interview prose + follow-up count (turn
  verbosity only; the brief's length stays governed by `output.yaml`).
