---
name: hs-think:critique
description: Multi-lens adversarial critique — fan independent lenses at an artifact, consolidate into one ranked verdict. Advisory by default; gate mode writes a machine verdict; optional --loop refute cycle.
category: think
license: AGPL-3.0
keywords: [critique, multi-lens, adversarial, fan, independent, lenses]
when_to_use: "Multi-lens adversarial critique — fan independent lenses at an artifact, consolidate into one ranked verdict."
user-invocable: true
argument-hint: "<artifact path / idea> [--gate] [--advisory] [--loop] [--lenses a,b,c]"
allowed-tools: [Bash, Read, Write, Glob, Grep, Task]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs-think:critique — multi-lens critique -> consolidated verdict

Input: an artifact to challenge — a plan, a decision, a design, a code diff, or a stated approach.
No input -> `AskUserQuestion`: what is under critique, where it lives, what "done" looks like.

This skill fans SEVERAL independent lenses at one artifact, then merges their findings into a single
ranked verdict. It does not replace the single-lens `hs-think:brainstorm --critique` (one advisor, one
pass); reach for `hs-think:critique` when one perspective is not enough and you want independent lenses that
do not see each other's reasoning. Tone is neutral and professional throughout — the lenses attack
the artifact, never the author.

## Modes and flags

| Flag | Effect | When to use |
|---|---|---|
| _(default)_ | advisory: lens fan-out -> consolidate -> report. Never blocks. | challenge an artifact before committing to it |
| `--gate` | also write `critique-consensus.json` (verdict PASS / PASS_WITH_RISK / BLOCKED) | a downstream stage opts into the critique gate (see Boundaries) |
| `--advisory` | force report-only for this run, even if `critique.yaml` says `mode: gate` | override config once |
| `--loop` | bounded critique -> refute -> consolidate cycle | a contested verdict where a defense pass may change the outcome. Detail -> `references/refute-loop.md` |
| `--lenses a,b,c` | override the lens set from `critique.yaml` | unusual artifact, or a specific perspective set is wanted |

Default mode comes from `harness/data/critique.yaml` (`mode:`, default advisory). `--gate`/`--advisory`
override it for one run.

## Process

1. **Frame + classify**: read the artifact and nearby context. Classify its type
   (plan / decision / design / code / diff) and pick the lens set from `harness/data/critique.yaml`
   (`lenses:` by type; unknown -> `default`). `--lenses` overrides. Summarize scope in 3-6 bullets.

2. **Fan out the lenses**: run each lens read-only, in **batches of ≤2** (respect the
   2-subagent-per-turn limit — collect a batch, then start the next). Each lens returns its own
   report AND the normalized JSON finding contract. Lenses do not see each other's output.
   Detail -> `references/critique-protocol.md`.

3. **Consolidate**: hand all lens findings + any prior critique reports + the scope to the
   `critique-consolidator` agent. It dedups across lenses, ranks by severity, attaches repeat-offense
   metadata, flags DEC-worthy items, and proposes one verdict.
   Detail -> `references/consolidation-contract.md`.

4. **Refute (only with `--loop`)**: give the surviving blockers a defense pass that tries to rebut
   each with evidence, re-consolidate, and stop on convergence or `loop.max_rounds`.
   Detail -> `references/refute-loop.md`.

5. **Report**: write the consolidated critique to `plans/reports/<slug>-critique-report.md`.

6. **Gate artifact (only in gate mode)**: write the consolidator's verdict to
   `plans/<active-plan>/artifacts/critique-consensus.json` (schema
   `harness/schemas/artifact-critique-consensus.json`). Enforcement ships OFF: the shipped
   `stage-policy.yaml` lists `critique-consensus` at no stage, so a spine-only install is never
   blocked by it. An org opts in by adding `critique-consensus` to a stage's `requires:` (the
   verdict must then be `PASS`). The skill itself never blocks — `gate_stage` + `stage-policy.yaml` do.

7. **DEC-worthy**: for each flagged item, `AskUserQuestion` (Keep / Change / Hybrid). On a confirmed
   architecture decision -> `python3 harness/scripts/decision_register.py --append-alloc ...`.

## Backing

- `harness/data/critique.yaml` (mode, lens sets by artifact type, loop bound, verdict taxonomy).
- `harness/schemas/artifact-critique-consensus.json` (gate-mode verdict shape).
- `harness/rules/workflow-handoffs.md` (row: `hs-think:critique -> artifact (critique-consensus.json)`).
- `harness/rules/verification-mechanism.md` (Evidence Filter the lenses and consolidator obey).
- `harness/rules/orchestration-protocol.md` (lens fan-out / batching).
- `harness/scripts/decision_register.py` (record a DEC in step 7).
- Component agents: `red-teamer`, `independent-revalidator`, `code-reviewer`, `brainstormer`
  (lenses), `critique-consolidator` (merge). Referenced by name; never imported.

## Output language

Generated output (the report, human-facing summaries) follows `harness/data/output.yaml`. Read its
`language:` value (default `vi`) and write the prose in that language. Before finalizing, apply
`harness/rules/humanizer-and-anti-ai-tells.md`: strip AI-writing tells, and when `language: vi`, also
strip the Vietnamese translation-tells. Tone stays neutral and professional — no escalating register,
no remarks about the author. Evidence is never translated: keep `file:line`, IDs, SHAs, numbers, and
verbatim quotes exactly as found.

## Boundaries

- Lenses and the consolidator are READ-ONLY advisory agents: they attack and report, they do not edit
  code, plans, or artifacts. The skill controller writes the report and (gate mode) the artifact.
- Respect the 2-subagent-per-turn limit: fan out lenses in batches, do not spawn the whole set at once.
- The skill never blocks directly: it writes `critique-consensus.json`; `gate_stage` + `stage-policy.yaml`
  enforce. Enforcement ships OFF — the shipped policy lists `critique-consensus` at no stage; opt in by
  adding it to a stage's `requires:` in `stage-policy.yaml` (write-guarded, edit outside the session),
  after which the verdict must be `PASS`.
- Only output = the critique report (markdown in `plans/reports/`) plus, in gate mode, the verdict
  artifact. Do NOT implement fixes here.
- Scope creep (a fix worth doing) -> note it in the report and `BACKLOG.md`; do not start building.
- On completion: absolute path to the report + the verdict + any DEC-worthy items.

## Observe checkpoint (end-of-work)

When the critique is done, if this run surfaced a judgment a counter cannot see, record ONE
closed-vocab signal so the harness learns from it — emit only a REAL observation, not every run.
Vocabulary lives in `harness/data/observation-signals.yaml`.

```bash
python3 harness/scripts/emit_observation.py --skill hs-think:critique \
    --signal <thin-evidence|red-team-reopened|gate-repeat-block> \
    --payload "<one line: what happened>"
```

Surfaces in the read-only `observations` lens (honesty-gated). Skip it silently when nothing notable
happened — a fabricated signal is worse than none.

## References (load on demand)

| Drawer | Content | When to load |
|---|---|---|
| `references/critique-protocol.md` | Lens selection by artifact type, batched fan-out, the JSON finding contract | Every invocation (step 2) |
| `references/consolidation-contract.md` | Consolidator inputs/outputs, dedup, severity, repeat-offense, verdict rule | When consolidating (step 3) |
| `references/refute-loop.md` | The `--loop` critique -> refute -> consolidate cycle and its convergence rule | Only with `--loop` (step 4) |
