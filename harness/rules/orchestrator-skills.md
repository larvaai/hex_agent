# Orchestrator skills (on-demand)

Contract for **orchestrator**-type skills -- skills that compose multiple `hs:*`
meta-skills into a fixed workflow (hs:cook, hs:plan, hs-research:discover, hs:triage,
hs:understand, hs-flow:afk). Unlike leaf skills (one task each), orchestrators
COORDINATE other skills. Load this file when writing or editing an orchestrator,
or when reviewing a handoff chain.

## Invariants

1. **Clear input contract.** An orchestrator declares what input it needs
   (hs:cook needs an approved plan; hs:triage needs a defect description;
   hs-research:discover needs an idea + constraints). Missing input -> return to the
   upstream skill or ask the human; do NOT guess.
2. **Chain-by-name.** Invoke component skills BY NAME (`hs-research:research`, `hs:fix`...),
   do NOT import the code/hooks of another skill, do NOT copy their logic into
   yourself. Each component skill keeps its own boundaries + gate. Circular
   coordination is forbidden.
3. **Gate-vs-handoff** -- distinguish clearly which type of output is produced:
   - **Gate (hard):** only when the orchestrator GENERATES a machine-readable
     artifact that a gate can read (hs:triage/hs:cook -> `verification.json` via
     `harness/hooks/gate_stage.py`; review -> `artifact-review-decision.json`).
     When a suitable gate already exists -> **REUSE IT**, do not create a new gate.
   - **Handoff (soft):** orchestrator only produces documentation/handover
     (hs-research:discover -> brief, hs:understand -> map) -> do NOT claim a hard-gate;
     connect onward via `harness/rules/workflow-handoffs.md` +
     `harness/data/skill-chains.yaml`.
4. **Do not bypass safety steps of component skills.** If hs:fix requires TDD
   red->green, an orchestrator calling hs:fix may NOT skip that step. Orchestrators
   coordinate; they do not "optimize" by cutting a child skill's gate.
5. **Context isolation for heavy handoffs.** Handoffs carrying substantial context
   (discovery, planning) -> recommend /clear, backed by the corresponding nudge
   (`discover_isolation_nudge` for discover->plan, `cook_isolation_nudge` for
   plan->cook). Nudges are advisory fail-open, default OFF, do NOT block.
6. **Out-of-scope -> `BACKLOG.md`**, do not steer the workflow mid-run.

## Registration (wiring into the harness)

- Add the chain pair to `harness/data/skill-chains.yaml` -- the workflow-chains lens
  compares declared-vs-actual telemetry; drift becomes data. (e.g. hs-flow:afk declares
  `[hs:plan, hs-flow:afk]` + `[hs-flow:afk, hs:test]` -- the unattended branch of the
  plan->test pipeline.)
- Add a handoff row to `harness/rules/workflow-handoffs.md`.
- Register the skill in the `owned` set via frontmatter `name: hs:<name>`
  (`harness/scripts/catalog.py`).
- New nudge (if any): file `harness/hooks/*.py` with `HOOK_CLASS` constant +
  register in `harness/install/hooks-registration.yaml` + TDD tests. Details:
  `hs-create:harness-creator`.

## Name honesty

An orchestrator's name describes what it COORDINATES, not over-claiming the work
of component skills: hs:triage *triages + routes + gates* a defect -- the actual
fix is done by hs:fix; hs-research:discover *shapes* a problem into a brief -- the planning
is done by hs:plan.
