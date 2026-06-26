# Chain orchestration — hs-research:discover

Call order for component skills, exact flags, and handoff to hs:plan.
Load this drawer in steps 3 and 6 of hs-research:discover when chain details are needed.

## Standard chain (without --quick)

```
hs-research:discover
  │
  ├─ 1. hs-research:research            (evidence gathering)
  │       └─ output: plans/reports/<slug>-research-<date>.md
  │
  ├─ 2. hs-think:brainstorm --diverge  (generate option space)
  │       └─ output: 2-4 approaches, no selection yet
  │
  ├─ 3. hs-think:brainstorm --critique (attack the hypotheses)
  │       └─ output: failure modes + reconsider conditions per option
  │
  ├─ 4. hs-think:brainstorm --converge (finalize recommendation)
  │       └─ output: chosen direction + trade-offs
  │
  └─ 5. Synthesize -> discovery-brief.md
```

## --quick chain

```
hs-research:discover --quick
  │
  ├─ 1. hs-think:brainstorm --quick   (single fast pass)
  │       └─ output: 1-2 directions + preliminary recommendation
  │
  └─ 2. Synthesize -> discovery-brief.md  (no evidence link -> write [SKIPPED])
```

## Calling component skills — specific guidance

### hs-research:research

Call with the central question = the problem framing identified in step 1.

```
/hs-research:research
  Topic: <problem to discover>
  Mode: breadth (default) or depth if implementation detail is needed
  Max sources: 5
```

Returns: absolute path to report -> use as the evidence link in the brief.
Do not paste the full report content into the brief — only the link + 3-5 bullet summary.

### hs-think:brainstorm --diverge

```
/hs-think:brainstorm --diverge
  Problem: <problem framing>
  Hard constraints: <from step 1>
  Evidence: <research report link>
```

Output: 2-4 clearly named approaches, no selection made. Record in the option space of the brief.

### hs-think:brainstorm --critique

```
/hs-think:brainstorm --critique
  Options: <A>, <B>, <C> from the diverge step
```

Output per option: Adopt / Adopt-with-guard / Reject + failure modes.
Use to fill the "Cons" column and "Risks" section of the brief.

### hs-think:brainstorm --converge

```
/hs-think:brainstorm --converge
  Options: <after critique>
  Constraints: <unchanged from step 1>
```

Output: chosen direction + clear trade-offs -> fill section 5 of the brief.

### hs-think:problem-solving (when blocked)

Trigger: option space is empty after diverge, or frame does not converge after 2 rounds.

```
/hs-think:problem-solving
  <description of where the block is>
```

After hs-think:problem-solving returns -> resume the chain from the blocked step.

## Handoff to hs:plan

After the brief is written and the user confirms:

1. Return absolute path: `plans/<slug>/discovery-brief.md`
2. `AskUserQuestion`:
   - Option A (recommended): `/clear` then `/hs:plan <brief-path>`
   - Option B: Revise the brief further before planning
   - Option C: Stop, save the brief, plan later
3. If the user chooses A -> remind: the `discover_isolation_nudge` will advise if
   planning continues in the same session, but `/clear` is the surest way to ensure a clean context
   (`harness/rules/workflow-handoffs.md` #5).

## Subagent fan-out (if needed)

When research scope is broad (>5 sources) or the user requests autonomous operation: spawn a
`researcher` agent following `harness/rules/orchestration-protocol.md`.
Controller (hs-research:discover) retains: merging decisions, user approval, writing the brief.
Subagent: research only, returns report + path.

## Chain invariants

- Do not skip critique in the standard chain — critique prevents premature convergence,
  it is not optional polish.
- Only write the brief AFTER converge output is available — do not draft it in advance.
- All links in the brief must be absolute paths (usable after a /clear in a future session).
