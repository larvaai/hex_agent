---
name: hs-uiux:design
description: "Design brand identity, logos, banners, and visual assets. Use for brand systems, design tokens, corporate identity programs. Not for UI code patterns."
user-invocable: true
when_to_use: "Invoke for brand systems and visual identity, not UI code."
category: frontend
keywords: [brand, logo, CIP, banners, identity]
argument-hint: "[design-type] [context]"
license: MIT
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep, WebFetch, WebSearch]
metadata:
  owner: harness
  compliance-tier: knowledge
---

# Design

Unified design skill: brand, tokens, UI, logo, CIP, slides, banners, social photos, icons.
Each sub-skill keeps its commands + deep guide in `references/` — this file routes.

## When to Use

- Brand identity, voice, assets · design system tokens and specs
- Logo design + AI generation · corporate identity program (CIP) deliverables
- Presentations / pitch decks · banners (social, ads, web, print)
- Social photos (IG/FB/LinkedIn/X/Pinterest/TikTok) · SVG icons

Not for UI *code* patterns — that is `hs-uiux:ui-ux-pro-max` / `hs-uiux:frontend-design`.

## Sub-skill Routing

| Task | Where | Guide |
|------|-------|-------|
| Brand identity, voice, assets | `brand` | External skill |
| Tokens, specs, CSS vars | `design-system` | External skill |
| shadcn/ui, Tailwind, code | `ui-styling` | External skill |
| Logo creation, AI generation | Logo (built-in) | `references/logo-design.md` |
| CIP mockups, deliverables | CIP (built-in) | `references/cip-design.md` |
| Presentations, pitch decks | Slides (built-in) | `references/slides-create.md` |
| Banners, covers, headers | Banner (built-in) | `references/banner-sizes-and-styles.md` |
| Social media images/photos | Social Photos (built-in) | `references/social-photos-design.md` |
| SVG icons, icon sets | Icon (built-in) | `references/icon-design.md` |

> `brand` / `design-system` / `ui-styling` are optional sibling skills. When present they
> live under `${CLAUDE_PLUGIN_ROOT}/skills/<name>/`; when absent, use the built-in guides.

## Built-in Sub-skills

### Logo

55+ styles, 30 color palettes, 25 industry guides via Gemini image models. Search styles/
colors/industries, generate a design brief, then generate logos (white background).
Commands + style/color/prompt guides: `references/logo-design.md`,
`references/logo-style-guide.md`, `references/logo-color-psychology.md`,
`references/logo-prompt-engineering.md`.

### CIP (Corporate Identity Program)

50+ deliverables, 20 styles, 20 industries. Search domains, generate a brief, render
mockups (logo recommended), then an HTML presentation. Models: `flash` (default) / `pro`.
Commands + guides: `references/cip-design.md`, `references/cip-deliverable-guide.md`,
`references/cip-style-guide.md`, `references/cip-prompt-engineering.md`.

### Slides

Strategic HTML presentations with Chart.js, design tokens, copywriting formulas. Start
with `references/slides-create.md`; patterns / template / copy / strategy in
`references/slides-layout-patterns.md`, `references/slides-html-template.md`,
`references/slides-copywriting-formulas.md`, `references/slides-strategies.md`.

### Banner

22 art-direction styles across social, ads, web, print. Build HTML/CSS with
`hs-uiux:frontend-design`, capture to PNG at exact size. Sizes, styles, safe-zone and
print rules: `references/banner-sizes-and-styles.md`.

### Social Photos

Multi-platform social images: HTML/CSS → screenshot export. Sizes, workflow, export
tooling, best practices: `references/social-photos-design.md` (+ export commands in
`references/social-photos-export.md`).

### Icon

15 styles, 12 categories. Gemini Pro Preview emits SVG text (no image API). Single /
batch / multi-size generation: `references/icon-design.md`.

## References

| Topic | File |
|-------|------|
| Design Routing | `references/design-routing.md` |
| Logo Design Guide | `references/logo-design.md` |
| Logo Styles | `references/logo-style-guide.md` |
| Logo Colors | `references/logo-color-psychology.md` |
| Logo Prompts | `references/logo-prompt-engineering.md` |
| CIP Design Guide | `references/cip-design.md` |
| CIP Deliverables | `references/cip-deliverable-guide.md` |
| CIP Styles | `references/cip-style-guide.md` |
| CIP Prompts | `references/cip-prompt-engineering.md` |
| Slides Overview | `references/slides.md` |
| Slides Create | `references/slides-create.md` |
| Slides Layouts | `references/slides-layout-patterns.md` |
| Slides Template | `references/slides-html-template.md` |
| Slides Copy | `references/slides-copywriting-formulas.md` |
| Slides Strategy | `references/slides-strategies.md` |
| Banner Sizes & Styles | `references/banner-sizes-and-styles.md` |
| Social Photos Guide | `references/social-photos-design.md` |
| Social Photos Export | `references/social-photos-export.md` |
| Icon Design Guide | `references/icon-design.md` |

## Scripts

Logo + CIP run a BM25 search engine over bundled CSV data, then call Gemini image models;
Icon emits SVG text. All resolve data relative to the script dir, so they run wherever the
plugin is installed.

| Script | Purpose |
|--------|---------|
| `scripts/logo/search.py` | Search logo styles, colors, industries |
| `scripts/logo/generate.py` | Generate logos with Gemini |
| `scripts/logo/core.py` | BM25 search engine for logo data |
| `scripts/cip/search.py` | Search CIP deliverables, styles, industries |
| `scripts/cip/generate.py` | Generate CIP mockups with Gemini |
| `scripts/cip/render-html.py` | Render HTML presentation from CIP mockups |
| `scripts/cip/core.py` | BM25 search engine for CIP data |
| `scripts/icon/generate.py` | Generate SVG icons with Gemini |

## Setup

```bash
export GEMINI_API_KEY="your-key"  # https://aistudio.google.com/apikey
pip install google-genai pillow
```

## Integration

**Optional sibling skills:** brand, design-system, ui-styling.
**Related:** hs-uiux:frontend-design, hs-uiux:ui-ux-pro-max, hs-ai:ai-multimodal, hs-devops:agent-browser, hs-devops:chrome-profile.
