---
name: hs-mem:docs-seeker
description: Look up library/framework documentation via llms.txt (context7.com) — API docs, GitHub repo analysis, latest features. Use when current official docs for a library are needed.
category: mem
license: AGPL-3.0
keywords: [docs-seeker, look, library, framework, documentation, llms]
when_to_use: "Use when current official docs for a library are needed."
argument-hint: "[<library> [topic] [version]]"
user-invocable: true
allowed-tools: [Read, WebFetch, WebSearch]
metadata:
  owner: harness
  compliance-tier: knowledge
---

# hs-mem:docs-seeker — library documentation lookup

Locate and retrieve authoritative technical documentation from official sources.
Does not write code or modify files. Results are returned directly in the session
or handed off to `hs-research:research` for deeper synthesis.

No argument: `AskUserQuestion` — library name, specific topic (if any), target
version (default: latest).

## Process (hard)

1. **Classify the query** — determine: (a) topic-specific ("caching in Next.js")
   or general ("all Astro docs"); (b) library name; (c) version.

2. **Look up llms.txt** — load `references/url-patterns.md`; build the URL and
   fetch with WebFetch in priority order:
   - Topic-specific: `https://context7.com/{org}/{repo}/llms.txt?topic={keyword}`
   - General: `https://context7.com/{org}/{repo}/llms.txt`
   - Fall back to the official site if context7.com returns 404.

3. **Process results** — count URLs returned in llms.txt; distribute reads
   according to `references/agent-distribution.md` (1-3 URLs: read directly;
   4-10 URLs: up to 2 agents in parallel; 11+ URLs: split into phases).

4. **Fallback when llms.txt is absent** — load `references/fallback-chain.md`;
   try WebSearch, then repo analysis via `hs-research:repomix`, then `hs-research:research`
   with multiple web sources.

5. **Present results** — summarize: source, version, key points (installation /
   API / examples). Mark inferred information as `[UNVERIFIED]` when it comes
   from code rather than official docs. Suggest next steps: `hs-mem:docs` (write
   internal docs) or `hs-research:research` (comparative research).

## Boundaries

- Do NOT write implementation code: only locate and present documentation.
- Do NOT create markdown files: output stays in the session.
- Information inferred from source code (repo analysis) must clearly state its
  source and caveats.
- Do not assume context7.com is available; always verify before using.

## Session close

Return:
- Documentation sources used (URL or file path).
- List of open questions (if any).
- Suggested next step: `hs-research:research` (deep evaluation) | `hs-mem:docs` (write internal documentation).
