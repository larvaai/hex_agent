---
name: hs-meta:find-skills
description: Locate and route to the correct hs:* skill — analyze intent, query the hs plugin registry, return the exact invoke command. Use when unsure which skill fits or to browse the full hs:* catalog.
category: meta
license: AGPL-3.0
keywords: [find-skills, locate, route, correct, skill, analyze]
when_to_use: "Use when unsure which skill fits or to browse the full hs:* catalog."
argument-hint: "[task description] | --list | --stage <sdlc>"
user-invocable: true
allowed-tools: [Bash, Read, Grep, Glob]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs-meta:find-skills — skill discovery and routing

Analyze the user's task → query the hs plugin catalog → return the matching skill
with its invoke command. Does not write code or modify files.

**Registry wiring**: the catalog is loaded via `harness/scripts/catalog.py`
(`load_catalog()`) — reads `harness/plugins/*/SKILL.md` frontmatter `name:`
across the whole hs plugin family (core `hs` + siblings like `hs-viz`). A skill
must have an existing `SKILL.md` to be considered available.

## Modes / flags

| Argument | When to use |
|---|---|
| _(task description)_ | route to the most suitable skill |
| `--list` | list all hs:* skills that have a SKILL.md |
| `--stage <sdlc>` | filter by SDLC stage (plan/build/verify/ship/meta) |

No argument → `AskUserQuestion`: what are you trying to do?

## Workflow

1. **Parse intent** — identify task type: planning, implement, debug, review,
   deploy, or meta (skill/project management).

2. **Query routing map** — load `references/hs-routing-map.md`; find the skill that
   matches the SDLC stage and intent. If 2 or more skills match, return the primary
   skill plus a supporting skill and explain the division of responsibilities.

3. **Verify existence** — call `load_catalog()` from `catalog.py` (or `ls
   harness/plugins/*/skills/`) to confirm the proposed skill's directory and
   SKILL.md actually exist. A sibling-plugin skill (e.g. `/hs-viz:excalidraw`) is
   in the same family catalog — invoke it under its own prefix. **Do not propose
   phantom skills.**

4. **Return result** — format:
   ```
   Suggested skill: /hs:<name>
   Purpose: <one sentence>
   Invoke: /hs:<name> [args if any]
   Supporting skill (if needed): /hs:<name2>
   ```

5. **Gap report** — if no skill matches: clearly state "No skill for [intent]";
   suggest a workaround using the nearest skill or native Claude tools.
   Do not fabricate skills.

## HARD-GATE (actual wiring)

- **Catalog**: `harness/scripts/catalog.py` `load_catalog()` — the sole authority
  for confirming a skill exists. `owned` set = directories whose `name:` is in the
  hs family (`hs:*` / `hs-viz:*` / future siblings).
- **Registry root**: `harness/plugins/*/skills/` — every family plugin's skills;
  only directories with `SKILL.md` are counted as available (catalog.py invariant).
- **Phantom guard**: a skill without `SKILL.md` → listed as "not yet ported" (directory
  exists but file is missing) or "does not exist" (directory also absent).

## Boundaries

- Do NOT write code. Do NOT modify files.
- Route only to `hs:*` skills. Do not suggest skills from other plugins.
- Do not self-invoke the chosen skill — the user decides when to invoke.
- End with: full invoke command + the SDLC stage the skill serves.
