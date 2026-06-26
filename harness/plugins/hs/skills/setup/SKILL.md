---
name: hs:setup
description: "Configure this project's harness posture — terminal voice, guard/stage policy, reviewer roster, output language — through the validated config CLIs. Use when onboarding a fresh install or changing a posture decision."
category: core
license: AGPL-3.0
keywords: [setup, configure, project, harness, posture, terminal]
user-invocable: true
allowed-tools: [Bash, Read, Grep, Glob]
when_to_use: "Invoke to onboard a fresh install or to change a posture decision (voice, guard/stage strictness, reviewers, lease, output language). Reads config-reference.md, writes via the per-config CLIs, and reminds about the session restart env-bound guard/stage needs."
argument-hint: "[full | short | show | none]"
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs:setup — project posture configuration

Walks the user through the harness's tunable posture and writes their choices through the
validated config CLIs (never by hand-editing the YAML from inside the session). The authoritative
index of every knob, its file, default, and env override is `harness/rules/config-reference.md` —
read it before presenting options so the defaults you quote are correct.

This skill is for BOTH onboarding (a fresh install) and changing a decision later. Re-invoking
always re-shows the menu.

## Preamble — pick the depth (present in the project's output language)

Present these four options first and wait for the choice (output language per `harness/data/output.yaml`):

1. **Full** — walk every group (voice, guard/stage, roster, output language) with current value + default.
2. **Short** — only the three that matter most on day one: reviewer roster, guard preset, output language.
3. **Show meanings + defaults** — read `config-reference.md` back to the user, change nothing.
4. **None** — exit without changes.

## The groups and their CLIs

Quote the CURRENT resolved value before asking for a new one (run the read form, no `--set`).

| Group | Knobs | Tool | Takes effect |
|---|---|---|---|
| Terminal voice | persona, voice_level, terminal_voice_level, no_markdown, interview_rigor, action_prompting, detail_level | `harness/scripts/voice_prefs.py --set k=v` (or `/hs-meta:voice`) | **live** — no restart |
| Output prose | language (en\|vi), humanize | `harness/scripts/output_config.py --set k=v` | live — read per invocation |
| Reviewer roster | reviewers (csv), lease_s | `harness/scripts/team_config.py --set k=v` | live — read per gate |
| Guard policy | preset (strict\|balanced\|lenient), per-guard off\|warn\|block | `harness/scripts/guard_config.py set-preset <p>` / `set <guard> <mode>` | **restart** (env-bound) |
| Stage policy | per-stage artifact requirements / hard | edit `harness/data/stage-policy.yaml` (hand edit; git-visible) | **restart** (env-bound) |
| Components | which optional plugins/hooks ship-on (viz, uiux, devops, rbac, …) | `harness/scripts/component_config.py --set <name>=enabled\|disabled` (read: `show` / `list`) | hook-side **live**; plugin-side **restart** |

Components are ship-all-but-off: every plugin/hook is shipped on disk; turning one off flips its
runtime switch (a plugin's `enabledPlugins:false`, a hook's `enabled:false`), never deleting it. A
hook component takes effect live (the hook self-skips on the flag); a **plugin** component needs a
restart, because Claude Code only reads the plugin list when a session opens (see the restart reminder).

Read forms (no write): `voice_prefs.py`, `output_config.py --file <path>`, `team_config.py`,
`guard_config.py show`.

## Restart reminder — say this out loud

Guard and stage policy are **env-bound** (`HARNESS_GUARD_POLICY` / `HARNESS_STAGE_POLICY`): the
pre-push hook scrubs every `HARNESS_*` before judging a push, so these must NOT be live-discovered —
they only take effect on a **new session**. After changing guard or stage, tell the user plainly:

> Guard/stage changed — restart the session (or open a new terminal) for it to take effect. Voice,
> roster, and output language are live and need no restart.

The same restart applies to turning a **plugin component** on or off (e.g. `hs-viz`): Claude Code
reads its plugin list at session start, so a newly enabled plugin's `/<plugin>:<skill>` commands
only appear after a restart. Verified live: enabling `hs-viz` then restarting surfaced
`/hs-viz:excalidraw`.

The `setup_nudge` SessionStart hook also surfaces this automatically when settings.json wires those
env vars but the running session does not match them.

## allow_self_review is NOT settable here

Turning solo-mode self-review on weakens the approval gate. It is deliberately not a `--set` knob:
edit `harness/data/team.yaml` by hand so the flip is a visible git diff (the plan-approval role
check is the backstop). If the user asks for it, explain this and point them at the file.

## Boundaries

- Always write through the CLIs (`*_config.py --set`, `voice_prefs.py --set`, `guard_config.py`) so
  validation runs and the change is a clean git diff. Do not hand-edit the YAML from inside the session.
- An unknown key or out-of-range value exits non-zero and writes nothing — report the failure, do
  not retry blindly.
- Setting `voice_level` 6–9 is a deliberate save; there is no second prompt. The universal-harm
  floor in `harness/rules/terminal-voice.md` is what holds at every level.
- This skill changes CONFIG, never code or evidence. Gate decisions still follow the written files.
