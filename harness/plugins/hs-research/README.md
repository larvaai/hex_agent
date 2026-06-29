<!-- generated: plugin-readme -->

# hs-research

SDLC harness — điều tra / khám phá / quét (hs-research:research / autoresearch / discover / repomix / techstack / security-scan). Sibling của plugin hs (spine).

**Default:** opt-in. Enable with `hs-cli components --enable research` (or choose it at install time).
**Version:** 2.0.0

## Skills (6)

| Invoke | Purpose |
|---|---|
| `/hs-research:autoresearch` | Router for the autonomous iteration framework — routes to the right specialized skill (hs-flow:loop, hs:plan, hs-research:discover) by goal. |
| `/hs-research:discover` | Shape an ambiguous problem into a discovery brief for hs:plan — research + brainstorm chain -> direction summary, trade-offs, open question… |
| `/hs-research:repomix` | Pack a codebase or subtree into an AI-friendly digest (XML, Markdown, plain, JSON). |
| `/hs-research:research` | Verified technical research — pose a question, gather multiple sources, verify evidence, synthesize a report. |
| `/hs-research:security-scan` | Scan codebase for security issues — hardcoded secrets, dependency CVEs, injection/authz gaps, STRIDE+OWASP. |
| `/hs-research:techstack` | Detect the target repo's tech stack (languages, test command, package manager, CI) so the harness adapts instead of assuming pytest. |

Each skill's full contract lives in its `SKILL.md`; load-on-demand detail lives under the skill's `references/`. This index is generated — regenerate with `harness/scripts/generate_plugin_readme.py`.
