---
name: hs-viz:mermaidjs
description: Text-based Mermaid.js v11 diagrams INLINE in markdown -- flowchart, sequence, class, ER, state, gantt, architecture -- renders natively on GitHub/GitLab without a separate file.
category: visualization
license: MIT
keywords: [mermaidjs, text-based, mermaid, v11, diagrams, inline]
when_to_use: "Invoke for inline GitHub/GitLab-rendered Mermaid.js v11 diagrams in markdown (flowchart/sequence/class/ER/state/gantt/architecture), no separate file."
argument-hint: "[diagram-type] <topic>"
user-invocable: true
allowed-tools: [Bash, Read, Write, Edit]
metadata:
  owner: harness
  compliance-tier: knowledge
---

# hs-viz:mermaidjs — diagrams with Mermaid.js v11

Create text-based diagrams using Mermaid.js v11 syntax. Primary path: write a
` ```mermaid ` block in markdown -- renders immediately on GitHub, GitLab, Obsidian, VS Code,
no installation needed. Image export (SVG/PNG/PDF) is OPTIONAL via the `mmdc` CLI.

## Diagram types

| Type | Use when | Reference |
|---|---|---|
| `flowchart` | process, decision tree | `references/diagram-types.md` |
| `sequenceDiagram` | API flow, actor interaction | `references/diagram-types.md` |
| `classDiagram` | OOP, data model | `references/diagram-types.md` |
| `stateDiagram-v2` | state machine, workflow | `references/diagram-types.md` |
| `erDiagram` | database schema | `references/diagram-types.md` |
| `gantt` | sprint/project timeline | `references/diagram-types.md` |
| `architecture-beta` | cloud infra, services | `references/diagram-types.md` |
| `gitGraph` | branching strategy | `references/diagram-types.md` |
| `journey` | user experience flow | `references/diagram-types.md` |

Full 24+ types and detailed syntax: `references/diagram-types.md`.

## Primary path -- inline markdown (zero deps)

````markdown
```mermaid
flowchart TD
    A[Start] --> B{Decision}
    B -->|Yes| C[Action]
    B -->|No| D[End]
```
````

**Config via frontmatter** (diagram-level):

````markdown
```mermaid
---
theme: dark
look: handDrawn
---
flowchart LR
    A --> B
```
````

Theme options: `default`, `dark`, `forest`, `neutral`, `base`.

**Comment:** prefix ` %% ` for single-line comments.

## Optional path -- export images with mmdc

> Only needed when a SVG/PNG/PDF file is required. Not a hard dependency.

```bash
# Install (requires Node.js >=18)
npm install -g @mermaid-js/mermaid-cli

# Export
mmdc -i diagram.mmd -o diagram.svg
mmdc -i diagram.mmd -o diagram.png -t dark -b transparent
mmdc -i diagram.mmd -o diagram.pdf

# Use without installing
npx -p @mermaid-js/mermaid-cli mmdc -i diagram.mmd -o diagram.svg
```

Batch, Docker, config file details: `references/cli-export.md`.

## Boundaries and cross-references

- **hs-viz:tech-graph** -- when a publish-grade SVG with layout rules (spacing, anti-collision) is needed.
- **hs-viz:preview** -- when you want to view the diagram in a browser before adding it to docs.
- **hs-mem:docs** -- when the diagram is part of a document that needs updating.
- Mermaid is the right choice for inline docs/markdown diagrams; for an editable canvas see hs-viz:excalidraw.

## Quick examples

See `references/examples.md` for real-world patterns:
- Microservices architecture
- Auth sequence flow
- E-commerce ER schema
- Order state machine
- Sprint Gantt
- CI/CD pipeline
- Git branching
