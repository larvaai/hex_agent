# Frontmatter and packaging convention

Harness-native skills live at `harness/plugins/hs/skills/<name>/SKILL.md`.
The catalog loader (`harness/scripts/catalog.py`) reads frontmatter to build the `owned` set.

## Required frontmatter

```yaml
---
name: hs:<name>          # hs: namespace required; name = dir (kebab-case)
description: <<=200 chars, clear trigger phrase, third-person style>
user-invocable: true
metadata:
  owner: harness
  compliance-tier: <workflow | gate | telemetry | knowledge>
---
```

### Useful optional fields

```yaml
argument-hint: "[arg1] [arg2]"   # syntax hint for the user
when_to_use: "Invoke when..."    # additional trigger context
```

## compliance-tier

| Tier | Meaning | Examples |
|---|---|---|
| `workflow` | Skill coordinates workflow, does not block git | hs:plan, hs:cook, hs-create:skill-creator |
| `gate` | Skill may exit 2 / block flow | hs:code-review |
| `telemetry` | Skill only reads/writes telemetry, no intervention | analytics skills |
| `knowledge` | Read-only or reference skill, no gate claim | hs-viz:excalidraw, lookup skills |

## Naming rules

- `name: hs:<name>` — name must match the directory name (segment after the last `/`)
- No uppercase, no spaces; use kebab-case
- "claude" and "anthropic" are banned in names
- Cross-skill references in prose: `hs:<name>` (no `/`); when invoking: `/hs:<name>`

## Directory structure

```
harness/plugins/hs/skills/<name>/
├── SKILL.md              required, <=150 lines (harness standard)
└── references/           optional, each file <=300 lines
    ├── <topic-a>.md      load-on-demand: workflow details
    └── <topic-b>.md      load-on-demand: schemas, checklists, etc.
```

Do not create `scripts/`, `agents/`, or `assets/` unless there is a real need and
corresponding harness backing.

## Description — "pushy" style

```yaml
# Under-triggers — too generic
description: Skill that creates documentation

# Correct triggers — specific phrase + third-person
description: Analyze the codebase and manage project documentation — initialize, update,
  summarize. Use when documentation needs to be created, refreshed, or audited.
```

Description rules:
- Third-person: "Use when..." / "Invoke when..."
- At least 1 specific trigger phrase
- <=200 chars (harness standard; spec allows <=1024)

## CI invariant (check_fence.py)

Files in `harness/` must not contain path references of the form `dot-claude/skills/` or
`dot-claude/hooks/` (CI test `TestOwnershipBoundary`), and must not contain
external brand names, old invoke prefixes, or dev-trace labels.
Lines that explain a learned technical pattern need a `# learn:` suffix to be
whitelisted in CI.

Run the grep clean check before reporting DONE — full commands at `references/validation.md`.
Empty output = pass.
