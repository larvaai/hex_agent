<!-- generated: plugin-readme -->

# hs-mem

SDLC harness — trí nhớ / phản tư / tài liệu (hs-mem:remember / insights / journal / retro / docs / docs-seeker / document-skills). Sibling của plugin hs (spine).

**Default:** opt-in. Enable with `hs-cli components --enable mem` (or choose it at install time).
**Version:** 2.0.0

## Skills (7)

| Invoke | Purpose |
|---|---|
| `/hs-mem:docs` | Analyze codebase and manage project documentation — init, update, summarize. |
| `/hs-mem:docs-seeker` | Look up library/framework documentation via llms.txt (context7.com) — API docs, GitHub repo analysis, latest features. |
| `/hs-mem:document-skills` | Create, edit, and analyze office files (.docx, .pdf, .pptx, .xlsx). |
| `/hs-mem:insights` | Surface read-only usage insights from harness telemetry — hot vs never-used skills, workflow chains, gate-block patterns — and propose end-… |
| `/hs-mem:journal` | Write a technical journal entry — record decisions, failures, and lessons learned after each session. |
| `/hs-mem:remember` | Capture the session's real knowledge — decisions made, non-obvious facts learned, user feedback — into the right durable home (DEC ledger, … |
| `/hs-mem:retro` | Generate data-driven retrospective reports from git history — velocity, code health, hotspots, plan progress. |

Each skill's full contract lives in its `SKILL.md`; load-on-demand detail lives under the skill's `references/`. This index is generated — regenerate with `harness/scripts/generate_plugin_readme.py`.
