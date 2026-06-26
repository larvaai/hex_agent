# Naming and routing — skill naming conventions and linking

## Naming rules

| Component | Rule | Example |
|---|---|---|
| Dir name | kebab-case, matching the part of the name after `:` | `skill-creator/` for `hs-create:skill-creator` |
| `name:` frontmatter | `hs:<dir>` | `name: hs-create:skill-creator` |
| Files inside dir | kebab-case | `references/naming-and-routing.md` |
| Reference drawers | short topic, self-documenting | `frontmatter-and-packaging.md` |

## Cross-skill routing in prose

Use the skill name, not a path:

```markdown
# CORRECT
Activate hs-research:research before planning.
See hs-think:brainstorm to explore options.
Invoke /hs:cook after the plan is approved.

# WRONG — exposes runtime path into the dot-claude tree (banned, see TestOwnershipBoundary)
Read dot-claude/skills/research/ ...
See harness/plugins/hs-think/skills/brainstorm/SKILL.md
```

## When to write `/hs:<name>` in prose

- Only write `/hs:<name>` when directing the user to invoke directly (user-facing instruction)
- In internal skill-to-skill mentions: use `hs:<name>` (no `/`)

## Skill name map (ck -> hs)

Ported skills — use these names in all cross-references:

| Skill | Invoke | Status |
|---|---|---|
| hs:plan | `/hs:plan` | Available |
| hs:cook | `/hs:cook` | Available |
| hs:test | `/hs:test` | Available |
| hs:git | `/hs:git` | Available |
| hs-research:research | `/hs-research:research` | Available |
| hs-think:brainstorm | `/hs-think:brainstorm` | Available |
| hs:debug | `/hs:debug` | Available |
| hs:fix | `/hs:fix` | Available |
| hs:code-review | `/hs:code-review` | Available |
| hs:scout | `/hs:scout` | Available |
| hs-flow:afk | `/hs-flow:afk` | Available |
| hs-create:skill-creator | `/hs-create:skill-creator` | Available |
| hs-meta:find-skills | `/hs-meta:find-skills` | Forward ref (not yet ported) |

Skills EXCLUDED (not ported, no references):
stack-specific (frontend/ui/mobile/shopify/db/deploy) -> omit all references.

## When a skill wants to call another skill

Write in SKILL.md as:

```markdown
Activate hs-research:research to gather context before step X.
After completion -> the runner invokes /hs:cook <path>.
```

Do not hardcode file paths of other skills. Do not create runtime dependencies between skill files.

## Catalog resolve

`harness/scripts/catalog.py` -> `load_catalog()` returns:
- `dirs` — set of dir names that have a SKILL.md
- `slug_to_dir` — map from `name:` value and variants -> dir name
- `owned` — dirs with `name: hs:*` (harness-native)

A new skill appears in `owned` once it has a correctly formatted `name: hs:<name>` in its frontmatter.
Verify:

```bash
python3 -c "
import sys; sys.path.insert(0, 'harness/scripts')
from catalog import load_catalog
c = load_catalog()
print('owned:', sorted(c['owned']))
"
```

## Wiring block — naming in HARD-GATE

Point to the actual filename, not a phantom:

```markdown
# CORRECT
Gate `harness/hooks/gate_stage.py` blocks push when an artifact is missing.
Script `harness/scripts/catalog.py` -> load_catalog() builds the owned set.

# WRONG — phantom backing
"Harness will automatically check on push"  <- mechanism is unclear
"Internal gate"                             <- no real file referenced
```
