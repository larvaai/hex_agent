---
name: hs-research:research
description: Verified technical research — pose a question, gather multiple sources, verify evidence, synthesize a report. Use before implementing or when evaluating technology or architecture.
category: research
license: AGPL-3.0
keywords: [research, verified, technical, pose, question, gather]
when_to_use: "Use before implementing or when evaluating technology or architecture."
argument-hint: "[breadth|depth] [--delegate] [topic]"
user-invocable: true
allowed-tools: [Bash, Read, Write, Grep, Glob, Task, WebFetch, WebSearch]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs-research:research — verified research

Collect, triangulate, and synthesize technical information into a report anchored to
evidence. **No code writing.** Output = report in `plans/reports/`.

**Evidence rule** (verified-vs-assumed, two-way Evidence Filter) in
`harness/rules/verification-mechanism.md` — read first. Not repeated here.

## Modes

| Mode | When | Depth |
|---|---|---|
| `breadth` (default) | quick survey, compare multiple options | <=5 sources, parallel search |
| `depth` | deep study of one topic, implementation detail needed | <=10 sources, sequential drill |

No argument -> `AskUserQuestion`: topic, mode, max sources, deadline.

Flag `--delegate`: spawn a `researcher` agent to handle multi-source work when the scope
is complex or the user requests autonomous operation.

## Process (hard)

1. **Pose the research question** — define clearly: central question, evaluation criteria
   (performance / security / maturity / fit), boundary (what is NOT in scope).
   No question -> stop and ask.

2. **Gather multiple sources** — load `references/source-triangulation.md`; run
   WebSearch in parallel (<=5 times); priority order: official docs -> maintainer blog ->
   production case study -> tutorial. Do not build conclusions from a single source.

3. **Verify evidence** — apply the Evidence Filter: every claim must have a `URL` or
   `file:line` anchor. Unanchored claim -> tag `[UNVERIFIED]`. Load
   `references/evidence-standard.md` when a detailed quality bar is needed.

4. **Synthesize + rank** — load `references/depth-modes.md` for the active mode;
   compare options using a trade-off matrix; give a ranked recommendation
   (not a flat list). **Escalation:** when the top trade-off is MEASURABLE and the choice is
   load-bearing, a paper matrix is weaker than a run — recommend escalating from paper-compare
   to `hs-think:bakeoff` (empirical probes) rather than ranking by argument alone.

5. **Generate the report** — load `references/report-format.md`; save to
   `plans/reports/<slug>-research-<date>.md`; end with open questions (if any).
   Return the absolute path.

6. **Delegate when needed** — scope > 5 independent sources or `--delegate` flag ->
   spawn a `researcher` agent with full context (question, criteria, report path).
   Agent does not write code; returns report + absolute path to controller.

## HARD-GATE (real wiring)

- **Evidence Filter** (`harness/rules/verification-mechanism.md`): unanchored claim
  = `UNVERIFIED` — subsequent steps must not build on it (invariant #2).
- **Output boundary**: reports must live in `plans/reports/` (CLAUDE.md rule #5).
  Creating markdown elsewhere violates the CI invariant.
- `researcher` agent (delegate): `harness/plugins/hs/agents/researcher.md` —
  must exist before spawning; if missing -> fall back to self-research, record
  `[NO_AGENT_DELEGATE]` in the report.

## Output language

Generated output (reports, docs, human-facing summaries) follows `harness/data/output.yaml`. Read its `language:` value (default `vi`) and write the prose in that language. Before finalizing, apply `harness/rules/humanizer-and-anti-ai-tells.md`: strip AI-writing tells, and when `language: vi`, also strip the Vietnamese translation-tells. Evidence is never translated or rewritten: keep `file:line` references, IDs, SHAs, numbers, and verbatim quotes exactly as found.

## Boundaries

- Do NOT write code, do NOT edit files outside `plans/reports/`.
- Do not invent facts — all information needs a source or an `[UNVERIFIED]` tag.
- When scope is too broad for one pass: prefer `--delegate` over cutting depth.
- On completion: absolute report path + list of open questions + suggested
  next step (implement / hs:plan / more depth).
