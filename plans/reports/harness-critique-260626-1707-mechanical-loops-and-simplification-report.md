---
type: harness-critique
date: 260626-1707
scope: harness/ (rules + hooks + core hs skills)
verdict: harness is a production-SDLC discipline machine; user is prototyping — wrong posture for the phase
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Harness: where it loops, and how to make it shut up

## The one sentence

The harness is built to make **"done" un-fakeable** — every claim anchored, every gate
backed by a JSON artifact, every stage human-approved. That is correct for shipping to
a shared repo. You are doing the opposite job: build a local-35B agent, run it, watch it
fail, fix, repeat. **Production discipline applied to prototyping IS the wasted time.**
The fix is not to gut the harness — it's to stop invoking the production pipeline during
the fail-fix phase.

## Where the time actually goes (ranked)

The hooks are **not** your bottleneck. `commit` is `hard:false` (stage-policy.yaml:14) —
local commits are already free. Gates only bite at `push/pr/ship`. The loops come from
**rules the agent self-imposes** the moment it reads CLAUDE.md routing:

| # | Source | Mechanism | Why it loops you | Cost |
|---|--------|-----------|------------------|------|
| 1 | `rules/verification-mechanism.md:23-43` (Iron Law) | No "done/fixed/passing" without a fresh command run + full output read **in this turn**. Stale runs rejected. | Agent re-runs the whole suite and re-reads output before it'll say anything, even for a one-line edit. | HIGH |
| 2 | `rules/tdd-discipline.md:3-12` | Write test → run to **real red** → implement → run green → run **full suite**. No fake green, no skip. | 3 test runs per change. For a prototype where "does it run once" is the real gate, that's 2 wasted runs. | HIGH |
| 3 | `rules/workflow-handoffs.md:6-49` | 10 handoffs: idea→plan→red-team→validate→**HUMAN approval**→cook→test→artifact→ship. Can't merge stages. | A 2-file fix gets threaded through a plan+approval pipeline meant for a team. | HIGH |
| 4 | Orchestrator skills (`plan` 8 steps/2 agents, `cook` per-phase, `understand` 3 agents, `triage` 6 steps, `ship` 10 steps/3 artifacts) | Each fans out 2-6 subagents; each subagent is a fresh context window + latency; several chain into each other. | You ask for a small thing, the skill spins up a research team. | HIGH |
| 5 | `rules/verification-mechanism.md:9-21` + `tdd-discipline.md:19` | Verdicts written to `verification.json` / `review-decision.json`; verbal claims don't gate. | Even passing tests → write+validate JSON before the next stage. | MED |
| 6 | `rules/plannotator-review-gates.md:43` | Plan approval = reviewer in team.yaml who is **not the author**. Solo → you approve yourself, multi-turn. | Async ceremony for a one-person project. | MED |

Hooks, for completeness — mostly inert for you:
- `simplify_gate` = `mode: warn` (soft, never blocks, fires only at pr/ship). Already harmless.
- nudges (`descriptive_name`, `cook_isolation`, `memory_gap`) default OFF.
- `gate_stage` only blocks at `push`+ (needs `verification`) and `pr/ship` (needs all 3 artifacts).
- `bash_safety_guard` / `write_guard` / `privacy_read_guard` — keep them, they protect the host, not your speed.

## The simplification (in order of leverage)

### 1. Behavioral — zero config, biggest win

During the fail-fix phase, **do not invoke** `hs:plan`, `hs:cook`, `hs:ship`,
`hs:understand`, `hs:triage`. They are the production pipeline. The loop you want is:

```
edit file  →  run it (python -m / pytest -x / the actual command)  →  read the error  →  fix  →  repeat
git commit -m wip      # free, hard:false, no artifacts
```

Use at most these, and only when they earn it:
- `/hs:test` — when you want the suite, not a single run. (No human gate; writes an artifact only if you're about to push.)
- `/hs:fix` (mode `quick`) — when a failure isn't obvious. Skip the built-in review on private branches.
- `/hs:debug` — only when you've burned 2+ hypotheses and are stuck.

Everything else stays off until you actually want a PR.

### 2. Tell the agent the posture out loud

The agent loads `tdd-discipline` + `verification-mechanism` from CLAUDE.md routing and
self-imposes the 3-run / anchor-everything ceremony. Override it explicitly per session:

> "Prototype mode: run the command once, read the error, fix. No red-green, no
> verification.json, no subagents, no plan. The gate is 'does it run'."

That single instruction kills traps #1, #2, #4 for the session without touching a file.

### 3. Config flips — if you want `push` free too

Only one file worth editing (human-edit, it's write-guarded from the agent on purpose):

```yaml
# harness/data/stage-policy.yaml — let WIP push without a verification artifact
push:
  hard: false        # was: hard:true, requires:[verification]
```

And if you ever *do* run `hs:cook`, skip its pause gates:

```bash
export HARNESS_AUTONOMY=god     # cook runs end-to-end, no plan/ship pauses (trace still records)
```

Leave `simplify-policy.yaml` (already `warn`) and the safety/secret/privacy guards alone —
they cost you nothing per cycle and catch real disasters.

## The honest structural take

185k LOC across 60+ skills, 14 rules, 18 hooks. For a solo local agent you touch maybe
5 skills and 2 rules. The bulk isn't slowing you at runtime (it's inert), but it IS why
the system *feels* like it's thinking in circles: the agent reads a production rulebook
and behaves like a release engineer. This matches your own recorded decision to drop ~70%
of hex_agent and keep the propose/adjudicate split + JSON-repair + budget termination.
**Same call applies here: for the fail-fix phase, the harness should be a 3-skill subset,
not the full SDLC machine.** Turn the machine back on for the one moment it's worth it —
the PR to a shared repo.

## Open questions
- Do you want a stripped `prototype` posture baked in (a CLAUDE.md routing variant that
  loads neither tdd-discipline nor verification-mechanism), so you don't have to say it
  every session? That's a 1-file change to the rule routing.
- Are you keeping this harness for the *new* local-35B build, or vendoring only the 3-skill
  subset there? Decides whether simplification is config or deletion.
