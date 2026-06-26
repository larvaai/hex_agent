# Primary workflow

Load this when a task needs an implementation workflow beyond a direct answer and no
specific SDLC skill has been invoked yet. It is the default entry router; the SDLC skills
(`hs:plan`, `hs:cook`, `hs:test`, `hs:code-review`, `hs:ship`) own the detailed steps.

## 1. Understand

- Read the request, relevant docs, and nearby code before planning.
- Clarify only decisions that cannot be discovered from the repo (scout first).
- For broad or risky work, route to `hs:plan` and create/update a plan in `plans/`.
- For an ambiguous step sequence, load `harness/plugins/hs/skills/cook/references/workflow-steps.md`.

## 2. Implement

- Change existing files when that matches the design; create new files only for real boundaries.
- Keep behavior compatible unless the accepted scope says otherwise.
- Prefer local helpers, conventions, and test utilities over new abstractions (YAGNI, KISS, DRY).
- For bugs, prove the cause before changing behavior (route to `hs:debug`).
- Drive multi-phase work through `hs:cook` so each phase records its verification artifact.

## 3. Verify

- Run focused tests for touched behavior.
- Broaden to lint, typecheck, build, or integration tests when shared contracts changed.
- Fix regressions instead of weakening tests or gates.

## 4. Review and explain

- Use `hs:code-review` for high-risk, cross-module, or public-contract changes.
- Update docs only when user-facing behavior, workflows, commands, or architecture changed.
- Explain the result plainly; reach for `/hs-viz:preview` only for complex workflows or architecture.

The hard stages (`push|pr|ship|deploy`) always pass through the presence gate
(`harness/hooks/gate_stage.py`); this rule routes, it does not replace the gate.
