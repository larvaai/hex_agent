# Thin-core and references — skill content structure

## Core principles

**Backing-or-cut (hard):** every directive in SKILL.md must point to real backing.
No backing -> cut from the thin-core (move to references as advisory or drop entirely).

**Progressive disclosure:**
1. Description (~200 chars) — always in context
2. SKILL.md body (<=150 lines) — loaded when the skill activates
3. references/ drawers — only loaded when needed

## Valid backing types

| Type | Path | Example |
|---|---|---|
| Gate hook | `harness/hooks/<name>.py` | `gate_stage.py`, `artifact_check.py` |
| Script | `harness/scripts/<name>.py` | `catalog.py`, `decision_register.py` |
| Rule | `harness/rules/<name>.md` | `tdd-discipline.md`, `verification-mechanism.md` |
| Schema | `harness/schemas/<name>.json` | artifact schemas |
| Policy | `harness/data/<name>.yaml` | `stage-policy.yaml` |

When referencing backing in SKILL.md: use the **filename** (not a `.claude/` path).

## Thin-core <=150 lines — required blocks

### 1. Boundaries
```markdown
## Boundaries
- Do NOT do X — when to stop
- When Y occurs -> ask the user via AskUserQuestion
- On completion: return [specific artifact]
```

### 2. Wiring block
```markdown
## HARD-GATE (real wiring)
<gate/script name> blocks/checks <condition> — points to a real target, not phantom.
```
If the skill has no gate -> use a "Backing" block instead of "HARD-GATE".

### 3. Modes / Flags (if applicable)
```markdown
## Modes
| Mode | When | Gates |
|---|---|---|
| fast | ... | skip X |
| hard | ... | X -> Y -> Z |
```

### 4. Process
- Numbered steps, each step <=3 lines
- Details -> "load `references/<drawer>.md`"
- Do not repeat content already in references

### 5. Quick reference table
```markdown
## Quick reference
| Content | Drawer |
|---|---|
| Topic A | `references/topic-a.md` |
```

## Backing-or-cut — quick decision

```
Directive X ->
  Has gate/script/rule in harness? -> KEEP, point to backing name
  No backing, important?           -> OPEN references drawer (advisory)
  No backing, not important?       -> CUT
```

## References drawers — when to split

Split into `references/<topic>.md` when:
- Details exceed 10 lines for one topic
- Content is only needed in one branch of the workflow (not every time)
- Schemas, checklists, or full examples

Each file <=300 lines. Filename: kebab-case, self-documenting.

## Example of correct separation

```
SKILL.md (thin-core):
  "Identify backing -> load references/thin-core-and-references.md"

references/thin-core-and-references.md:
  Backing types table, decision process, full examples  <- this file
```

Do not put the full backing types table in SKILL.md — too heavy for a thin-core.
