<!-- generated: plugin-readme -->

# hs-viz

SDLC harness — skill trực quan hoá (hs-viz:excalidraw / mermaidjs / graphify / tech-graph / preview): sơ đồ, knowledge graph, preview hình ảnh. Sibling của plugin hs.

**Default:** opt-in. Enable with `hs-cli components --enable viz` (or choose it at install time).
**Version:** 1.0.0

## Skills (5)

| Invoke | Purpose |
|---|---|
| `/hs-viz:excalidraw` | Generate editable `.excalidraw` JSON files on canvas (architecture, data flow, system design). |
| `/hs-viz:graphify` | Build a queryable knowledge graph from code, docs, and media — architecture analysis, cross-file relationship discovery, token-efficient na… |
| `/hs-viz:mermaidjs` | Text-based Mermaid.js v11 diagrams INLINE in markdown -- flowchart, sequence, class, ER, state, gantt, architecture -- renders natively on … |
| `/hs-viz:preview` | Explain a change or architecture with a diagram when visuals are clearer than prose — flow/architecture, before-after, sequence; output to … |
| `/hs-viz:tech-graph` | Generate publish-grade static technical diagrams (SVG+PNG, 8 styles) — architecture, data flow, sequence, agent/memory, concept map — for e… |

Each skill's full contract lives in its `SKILL.md`; load-on-demand detail lives under the skill's `references/`. This index is generated — regenerate with `harness/scripts/generate_plugin_readme.py`.
