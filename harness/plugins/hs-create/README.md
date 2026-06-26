<!-- generated: plugin-readme -->

# hs-create

SDLC harness — tạo artifact harness (hs-create:skill-creator / harness-creator / mcp-builder / agentize / port / bootstrap). Sibling của plugin hs (spine).

**Default:** opt-in. Enable with `hs-cli components --enable create` (or choose it at install time).
**Version:** 2.0.0

## Skills (6)

| Invoke | Purpose |
|---|---|
| `/hs-create:agentize` | Convert a codebase, feature, or module into an AI-agent-friendly npm CLI and/or MCP server. |
| `/hs-create:bootstrap` | Bootstrap a new project from scratch -- clarify requirements, init git, create doc structure, delegate to hs:plan + hs:cook. |
| `/hs-create:harness-creator` | Create new harness primitives (hook, rule, schema, data, script, agent) — not skills. |
| `/hs-create:mcp-builder` | Build MCP servers for LLM external-service integration — FastMCP (Python), MCP SDK (Node/TypeScript), tool design, API integration, resourc… |
| `/hs-create:port` | Extract, compare, port, or adapt a feature from a GitHub repository or local repo path into the current project. |
| `/hs-create:skill-creator` | Create or update hs:* skills for the harness — SKILL.md, frontmatter, thin-core, references, validate via catalog.py. |

Each skill's full contract lives in its `SKILL.md`; load-on-demand detail lives under the skill's `references/`. This index is generated — regenerate with `harness/scripts/generate_plugin_readme.py`.
