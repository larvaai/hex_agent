---
name: hs-viz:preview
description: Explain a change or architecture with a diagram when visuals are clearer than prose — flow/architecture, before-after, sequence; output to docs/ or plans/.
category: visualization
license: MIT
keywords: [preview, explain, change, architecture, diagram, visuals]
when_to_use: "Explain a change or architecture with a diagram when visuals are clearer than prose — flow/architecture, before-after, sequence; output to docs/ or plans/."
argument-hint: "[--explain|--diagram|--ascii|--slides] <topic>"
user-invocable: true
allowed-tools: [Read, Write, Edit]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs-viz:preview — visual explanation

Creates a visual explanation (diagram or slide-outline) when visuals aid understanding
more than prose. Does NOT write code, does NOT create markdown outside `docs/` or
`plans/` (CLAUDE.md rule #5).

**When is a visual needed?** Read `references/when-visual-helps.md` before any
mode — it is the sole decision gate. If a visual adds nothing over prose -> return
prose; do not generate a diagram.

## Modes

| Flag | When | Output |
|---|---|---|
| _(no arg)_ | unclear | `AskUserQuestion` asks for topic + mode |
| `--explain <topic>` | explain a concept or code path | ASCII + Mermaid fenced + prose |
| `--diagram <topic>` | focused diagram (flow, arch, sequence) | ASCII + Mermaid fenced |
| `--ascii <topic>` | terminal-only, no Mermaid | ASCII box diagram + legend |
| `--slides <topic>` | outline of sequential ideas | Markdown slide-outline |

No `--html` flag — the harness does not ship an HTML renderer. Mermaid fenced
blocks render in the markdown preview of editors and GitHub.

## Workflow

1. **Decision gate** (required): load `references/when-visual-helps.md` — if there
   is no evidence a visual helps, return prose and stop.
2. **Parse arg**: determine topic + mode; if missing -> `AskUserQuestion`.
3. **Read context**: scout related code/docs (use `hs:scout` when the topic is a
   real codebase); do NOT diagram a system that has not been read.
4. **Choose diagram pattern**: load `references/diagram-patterns.md` — select type
   (flowchart, sequence, architecture, before-after) based on content.
5. **Create output**: follow the template in `references/diagram-patterns.md`;
   always include an ASCII fallback alongside Mermaid (except `--ascii`).
6. **Save location**:
   - Active plan -> `plans/<slug>/visuals/<topic-slug>.md`
   - No active plan -> `plans/visuals/<topic-slug>.md`
   - Durable architecture doc -> `docs/` (via `hs-mem:docs`)
   - Create directory if missing.
7. **Report**: return the absolute path of the saved file + recommended next step.

## Boundaries

- Do NOT create markdown outside `docs/` or `plans/` — violates CLAUDE.md rule #5.
- Do NOT diagram assumed architecture (unread code) — violates the Evidence Filter
  (`harness/rules/verification-mechanism.md`).
- Do NOT use external render libraries (HTML server, Excalidraw, video) — the harness
  has no such renderer; diagrams are Mermaid fenced blocks or ASCII.
- Durable diagram output (architecture decision) -> update `docs/` via `hs-mem:docs`.
- Finish: return the absolute path of the saved file.

## HARD-GATE (real wiring)

No hard gate specific to visuals — but:
- Output files must be under `docs/` or `plans/` -> `harness/hooks/write_guard.py`
  enforces containment (CLAUDE.md rule #5 + `harness/data/ownership.yaml`).
- If the diagram is a stage artifact (cook/ship), `harness/hooks/gate_stage.py`
  still runs per normal stage-policy.

## Workflow position

**Typically after:** `hs:plan` (visualize plan), `hs:cook` (explain diff),
`hs-think:brainstorm` (diagram the chosen approach).
**Typically before:** review / handoff (diagram accompanies the report).
**Related:** `hs-mem:docs` (save durable diagram to `docs/`).
