---
name: hs-extra:markdown-novel-viewer
description: View markdown files in a calm, book-like reader served via HTTP. Use for long-form content review — RFCs, runbooks, design docs, reports, specs, novels — anywhere you want a distraction-free reading mode in the browser.
license: MIT
allowed-tools: [Bash, Read, Glob]
user-invocable: true
when_to_use: "Invoke to read long markdown comfortably in the browser."
category: utilities
keywords: [markdown, viewer, reading, preview]
argument-hint: "[file-or-directory]"
metadata:
  owner: harness
  compliance-tier: workflow
---

# markdown-novel-viewer

Background HTTP server rendering markdown files with calm, book-like reading experience.

**Note:** HTML generation mode (`/hs-viz:preview --html ...`) produces self-contained HTML files that open directly in the browser — they do not use this server.

## ⚠️ Installation Required

**This skill requires npm dependencies.** Install them once:

```bash
cd ${CLAUDE_PLUGIN_ROOT}/skills/markdown-novel-viewer
npm install   # or: bun install (a bun.lock is bundled)
```

**Dependencies:** `marked`, `highlight.js`, `gray-matter`

Without installation, you'll get **Error 500: Error rendering markdown**.

## Purpose

Universal viewer - pass ANY path and view it:
- **Markdown files** → novel-reader UI with serif fonts, warm theme
- **Directories** → file listing browser with clickable links

## Quick Start

```bash
# View a markdown file
node ${CLAUDE_PLUGIN_ROOT}/skills/markdown-novel-viewer/scripts/server.cjs \
  --file ./plans/my-plan/plan.md \
  --open

# Browse a directory
node ${CLAUDE_PLUGIN_ROOT}/skills/markdown-novel-viewer/scripts/server.cjs \
  --dir ./plans \
  --host 0.0.0.0 \
  --open

# Background mode
node ${CLAUDE_PLUGIN_ROOT}/skills/markdown-novel-viewer/scripts/server.cjs \
  --file ./README.md \
  --background

# Stop all running servers
node ${CLAUDE_PLUGIN_ROOT}/skills/markdown-novel-viewer/scripts/server.cjs --stop
```

## Skill Invocation

Use `/hs-viz:preview` for quick access:

```bash
/hs-viz:preview plans/my-plan/plan.md    # View markdown file
/hs-viz:preview plans/                   # Browse directory
/hs-viz:preview --stop                   # Stop server
```

## CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--file <path>` | Markdown file to view | - |
| `--dir <path>` | Directory to browse | - |
| `--port <number>` | Server port | 3456 |
| `--host <addr>` | Host to bind (`0.0.0.0` for remote) | localhost |
| `--open` | Auto-open browser | false |
| `--background` | Run in background | false |
| `--stop` | Stop all servers | - |

## HTTP Routes

| Route | Description |
|-------|-------------|
| `/view?file=<path>` | Markdown file viewer |
| `/browse?dir=<path>` | Directory browser |
| `/assets/*` | Static assets |
| `/file/*` | Local file serving (images) |

## Dependencies

- Node.js built-in: `http`, `fs`, `path`, `net`
- npm: `marked`, `highlight.js`, `gray-matter` (installed via `npm install`)

## References

Detailed guides (load as needed):

- `references/features.md` — novel theme, Mermaid diagrams, directory browser, focused reader mode, plan navigation, keyboard shortcuts, mobile optimization.
- `references/architecture-and-customization.md` — scripts/assets layout, theme color CSS variables, content width, remote network access.
- `references/troubleshooting-and-mermaid.md` — common server issues plus the full Mermaid.js diagram authoring/validation guide.
