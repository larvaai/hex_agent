# Disabled-group handling

Load when a skill reference points at a group that may be disabled.

After the 2.0.0 decomposition the core skills live across a spine plus six themed
sibling plugins. A fresh install enables only the spine `hs`; the groups
`hs-flow / hs-think / hs-research / hs-create / hs-mem / hs-meta` (and the ck-port
siblings `hs-viz / hs-ai / hs-devops / hs-stack / hs-uiux / hs-integrations / hs-extra`)
are opt-in, chosen at install time.

Because skills still reference each other across groups (the SDLC handoffs are a
contract), a reference like `hs-think:critique` or `hs-mem:remember` can name a skill
whose group is currently disabled. **This is not a broken reference.** The handoff
still stands — never delete or rewrite it to make a green check.

## When you hit a reference to a disabled group

You have two equally valid ways forward — pick by context:

1. **Enable the group** (preferred when the skill will be used repeatedly):
   `hs-cli components --enable <group>` (e.g. `--enable think`), or re-run the
   installer and select the group. The plugin ships in the install tree already;
   enabling only flips it on in `enabledPlugins`.

2. **Read the skill inline** (preferred for a one-off): open
   `harness/plugins/hs-<group>/skills/<skill>/SKILL.md` and perform its steps
   directly. The skill's instructions are plain files — a disabled plugin only means
   the `/hs-<group>:<skill>` slash command is not registered, not that the knowledge
   is gone.

## What never to do

- Do **not** drop the cross-skill reference or replace it with prose to dodge a
  resolver check — that erases the handoff contract.
- Do **not** treat a disabled-group reference as a dangling/typo'd reference in
  review or migration tooling.

## The nudge

`harness/hooks/disabled_ref_nudge.py` (nudge class, advisory, fail-open) watches the
session context for `hs-<group>:<skill>` references whose group is not enabled and
prints a one-line reminder pointing at the two options above. It never blocks; a
reference into a disabled group is a normal, expected state, not an error.
