<!-- >>> harness onboarding (generated; edits between markers are overwritten on reinstall) >>> -->

## SDLC harness

This repo runs a file-based **SDLC harness** for Claude Code, vendored self-contained under `harness/`.

- **Skills** — drive the workflow with `/hs:<name>` (e.g. `/hs:plan`, `/hs:cook`, `/hs:test`, `/hs:ship`, `/hs:review-pr`). `/hs-meta:find-skills` lists the full catalog.
- **Rules** — shared conventions load on demand from `harness/rules/` (routing in this file's project section, or ask a skill).
- **Hooks** — gates/telemetry are wired in `.claude/settings.json`; config knobs live in `harness/data/*.yaml` and `harness/hooks/*.yaml`. Run `/hs:setup` to configure posture (voice, guard, reviewers).
- **State** — runtime telemetry/state is written under `harness/state/` (gitignored; never commit it).

<!-- <<< harness <<< -->
