# Per-phase TDD — red→green execution per phase

References `harness/rules/tdd-discipline.md` (the single source of truth for the red→green rule).
This drawer explains how to apply it per-phase inside hs:cook.

## Three sub-steps per phase

```
3.T  Write test for NEW behavior → run to confirm intentional FAIL (wrong assert / ImportError)
3.I  Implement the minimum required to make the test pass
3.V  Re-run FULL suite (`python3 -m pytest harness/tests/ -q`) → paired commit test+module
```

Sub-step 3.T must NOT be green before 3.I — if it is already green, the test is wrong; rewrite it.

## Paired commit

Commit after 3.V includes test + module, conventional commit, no AI references.
Hard stage gate (`harness/hooks/gate_stage.py`) reads `verification.json` —
this artifact must exist before advancing to the next stage.

## Fix loop

When 3.V fails: fix the **code**, do not delete/skip/weaken tests. Report lists ALL
failures (name + 1-line reason). Verdict PASS / PASS_WITH_RISK / BLOCKED is written to
`plans/<plan>/artifacts/verification.json`.

## Stateless phase

Phase with `stateless: true` in frontmatter: skip trace for that phase;
`gate_stage.py` still runs (`harness/hooks/gate_stage.py` fail-closed).
Trace is telemetry fail-open — not a compliance gate.
