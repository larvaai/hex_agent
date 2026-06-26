<!-- generated: plugin-readme -->

# hs

SDLC harness — skill quy trình có kiểm chứng (hs:plan / hs:cook / hs:test / hs-flow:afk), neo vào gate hook fail-closed của harness.

**Default:** always-on (the SDLC spine — installed and enabled on every harness).
**Version:** 1.1.0

## Skills (13)

| Invoke | Purpose |
|---|---|
| `/hs:code-review` | Review code with technical rigor — bugs, regressions, security. |
| `/hs:cook` | Execute an approved plan phase by phase — TDD red→green, generate verification/review-decision artifacts, trace every step. |
| `/hs:debug` | Systematic debugging with root-cause analysis before fixing. |
| `/hs:fix` | Fix bugs, test failures, and CI/CD failures with an evidence-based workflow. |
| `/hs:git` | Git operations with conventional commits. |
| `/hs:plan` | Create a verified implementation plan — research, constraint-scan, phase design, red-team, and validate before cook. |
| `/hs:review-pr` | Review GitHub PR — diff, CI, correctness, security, breaking changes, anti-slop. |
| `/hs:scout` | Fast codebase exploration using parallel agents — find files, locate code, gather context before implementing or debugging. |
| `/hs:setup` | Configure this project's harness posture — terminal voice, guard/stage policy, reviewer roster, output language — through the validated con… |
| `/hs:ship` | Gated ship pipeline: review PASS → verification PASS → human approval → push/pr. |
| `/hs:test` | Run and validate tests for the current change — unit/integration profiles, concise QA report, 100% pass gate. |
| `/hs:triage` | Orchestrate the defect lifecycle — reproduce, classify, and gate bugs via hs:scout→hs:debug→hs:fix→hs:test. |
| `/hs:understand` | Orchestrate codebase comprehension before touching code — chain hs-research:repomix, hs:scout, hs-meta:context-engineering to build a codeb… |

Each skill's full contract lives in its `SKILL.md`; load-on-demand detail lives under the skill's `references/`. This index is generated — regenerate with `harness/scripts/generate_plugin_readme.py`.
