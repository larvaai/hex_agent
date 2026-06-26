<!-- generated: plugin-readme -->

# hs-meta

SDLC harness — harness tự quản (hs-meta:find-skills / voice / context-engineering / project-organization). Sibling của plugin hs (spine).

**Default:** opt-in. Enable with `hs-cli components --enable meta` (or choose it at install time).
**Version:** 2.0.0

## Skills (4)

| Invoke | Purpose |
|---|---|
| `/hs-meta:context-engineering` | Manage the context budget — check limits, optimize tokens, coordinate subagents, debug context failures. |
| `/hs-meta:find-skills` | Locate and route to the correct hs:* skill — analyze intent, query the hs plugin registry, return the exact invoke command. |
| `/hs-meta:project-organization` | Organize files, directories, and content structure in any project. |
| `/hs-meta:voice` | Switch the terminal voice for this session — persona, harshness, explanation depth, no-markdown — plus the output_style audience axis. |

Each skill's full contract lives in its `SKILL.md`; load-on-demand detail lives under the skill's `references/`. This index is generated — regenerate with `harness/scripts/generate_plugin_readme.py`.
