---
name: hs-create:skill-creator
description: Create or update hs:* skills for the harness — SKILL.md, frontmatter, thin-core, references, validate via catalog.py. Use to create a new skill, refine triggers, or extend the harness.
category: create
license: AGPL-3.0
keywords: [skill-creator, create, update, skills, harness, skill]
when_to_use: "Use to create a new skill, refine triggers, or extend the harness."
user-invocable: true
argument-hint: "[skill-name or description]"
allowed-tools: [Bash, Read, Write, Edit, Grep, Glob]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs-create:skill-creator — create harness-native skills

Create a new `hs:*` skill following the harness packaging convention: thin-core SKILL.md <=150 lines
+ `references/` drawers. Every directive **must have real backing** (gate/script/rule/schema)
or be cut (backing-or-cut).

**Base convention** (full details): `references/frontmatter-and-packaging.md`.

## Boundaries

- Only create files in `harness/plugins/hs/skills/<skill-name>/` — do NOT edit
  shared files (catalog.py, CLAUDE.md, BACKLOG.md).
- Non-skill primitives (hook/rule/schema/data/script/agent) do NOT belong here
  -> use `hs-create:harness-creator`. This skill only creates `hs:*` skills (leaf + orchestrator).
- Do not scaffold example skills into other directories.
- On completion: return the absolute path + `grep` clean-check result + STANDARDIZE row.

## Modes

| Mode | When |
|---|---|
| `new` (default) | Create a skill from scratch |
| `refine` | Update an existing SKILL.md or references |
| `validate` | Check an existing skill (structure + optional trigger-eval); no file creation |

## Process (new)

### Step 1 — Gather intent

Ask via `AskUserQuestion`:
- What does the skill do? Example of when the user would invoke it?
- Expected output (file, report, action)?
- Is there real backing in the harness (gate/script/rule)?

### Step 2 — Check the catalog

```bash
python3 -c "from harness.scripts.catalog import load_catalog; print(load_catalog())"
```

Check `harness/plugins/hs/skills/` — avoid duplicating an existing skill. If a
similar skill exists -> suggest `refine` instead of `new`.

### Step 3 — Identify backing

For **each feature** in the new skill:

1. Find backing in the harness: gate (`harness/hooks/*.py`), script
   (`harness/scripts/*.py`), rule (`harness/rules/*.md`), schema
   (`harness/schemas/*.json`).
2. **Has backing** -> keep the directive, point to the backing name (not a `.claude/` path).
3. **No backing** -> CUT or move into `references/` as advisory.

See the full backing-or-cut table: `references/thin-core-and-references.md`.

### Step 4 — Create the structure

```
harness/plugins/hs/skills/<name>/
├── SKILL.md          (required, <=150 lines)
└── references/       (optional: load-on-demand drawers)
    ├── <topic-a>.md
    └── <topic-b>.md
```

Create `SKILL.md` following the frontmatter convention:

```yaml
---
name: hs:<name>
description: <<=200 chars, clear trigger phrase, third-person>
user-invocable: true
argument-hint: "<syntax hint>"   # optional
metadata:
  owner: harness
  compliance-tier: workflow | gate | telemetry
---
```

Full details: `references/frontmatter-and-packaging.md`.

### Step 5 — Write the thin-core

The thin-core SKILL.md must contain:

1. **Boundaries** — clearly state "what NOT to do", when to stop, when to ask the user.
2. **Wiring block** — "HARD-GATE (real wiring)" or "Backing" pointing to real targets
   (actual gate/script filename, not phantom).
3. **Modes/Flags table** — if the skill has multiple modes.
4. **Process** — numbered steps, each <=3 lines; details -> references drawer.
5. **Quick reference** — table of reference drawers with short descriptions.

Language: English, imperative, sacrifice grammar for brevity.

### Step 6 — Validate

```bash
# Grep clean check (must be EMPTY) — see full commands at references/validation.md
python3 harness/scripts/catalog.py
# Or verify the slug appears in load_catalog()['owned']
```

Full checklist: `references/validation.md`. To measure whether the description actually
**triggers** on indirect queries (not just that it is well-formed), run the trigger-eval:
`references/eval-validate.md` — and iterate it automatically with the optimize loop:
`references/optimize-loop.md`.

### Step 7 — Write the STANDARDIZE row

Add one line to `docs/STANDARDIZE.md`:

```
| ADAPT | hs:<name> skill (native thin-core + references) | <source> (origin, MIT) | harness/plugins/hs/skills/<name>/ | <notes> | grep-clean invariant + SKILL.md |
```

## HARD-GATE (real wiring)

Catalog loader `harness/scripts/catalog.py` -> `load_catalog()` -> field `owned`
contains every directory with frontmatter `name: hs:*`. A skill without a correctly
formatted `name: hs:` -> **not in owned set** -> telemetry lens treats it as vendor, not harness-native.

CI invariant (`harness/tests/test_bug_class_invariants.py` ->
`TestOwnershipBoundary`): any path reference of the form `dot-claude/skills/` or
`dot-claude/hooks/` in `harness/` -> test fails, except lines with `# learn:`.
Grep clean check is required before reporting DONE — commands at `references/validation.md`.

## Quick reference

| Content | Drawer |
|---|---|
| Frontmatter fields + compliance-tier | `references/frontmatter-and-packaging.md` |
| Backing-or-cut + thin-core structure | `references/thin-core-and-references.md` |
| Naming + routing + cross-skill calls | `references/naming-and-routing.md` |
| Authoring orchestrator skills (chain meta-skills) | `references/orchestrator-skills.md` |
| Validate checklist + grep patterns | `references/validation.md` |
| Trigger-eval a description (does it activate?) | `references/eval-validate.md` |
| Optimize loop: iterate a description until it triggers right | `references/optimize-loop.md` |
