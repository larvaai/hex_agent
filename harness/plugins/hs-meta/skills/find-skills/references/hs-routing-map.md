# hs:* Routing Map — by intent and SDLC stage

Use this file from `hs-meta:find-skills` to map intent to skill. Every skill listed
here has a `SKILL.md` confirming it exists in `harness/plugins/hs/skills/`
(46 skills). Update this map when skills are added or removed.

**Selection rules**:

- Use the most specific skill first; router skills (`find-skills`, `autoresearch`,
  `triage`, `understand`) are only for genuine orchestration tasks, not because
  you are unsure which skill to use.
- `--stage <plan|build|verify|ship|doc|meta>` filters by the "Stage" column below.
- Tier `workflow` = has gates/artifact constraints; `knowledge` = advisory, generates
  output, does not block the pipeline.

---

## Planning and discovery (Stage: PLAN)

| When to use | Skill | Tier |
|---|---|---|
| Create a verified implementation plan (research → phase → red-team) | `/hs:plan` | workflow |
| Multi-source technical research, evidence verification, option comparison | `/hs-research:research` | workflow |
| Brainstorm solutions, trade-offs, architecture debate before committing to a direction | `/hs-think:brainstorm` | workflow |
| Shape an ambiguous problem into a discovery brief for `hs:plan` | `/hs-research:discover` | workflow |
| Multi-step analysis with revision, trace reasoning, verify hypotheses | `/hs-think:sequential-thinking` | workflow |
| Structured unblocking when a loop or hypothesis has failed 3+ times | `/hs-think:problem-solving` | workflow |
| 5 personas debate risk before a large or high-risk change | `/hs-think:predict` | knowledge |
| Decompose a feature across 12 dimensions into edge cases, risks, test targets | `/hs-think:scenario` | knowledge |

## Understanding the codebase before touching it (Stage: PLAN)

| When to use | Skill | Tier |
|---|---|---|
| Orchestrate comprehension: chain repomix→scout→context-engineering into a map | `/hs:understand` | workflow |
| Fast discovery with parallel agents — find files, locate code | `/hs:scout` | workflow |
| Package a codebase or subtree into an LLM-friendly digest (XML/MD/JSON) | `/hs-research:repomix` | workflow |
| Build a queryable knowledge graph from code/docs — cross-file relationships | `/hs-viz:graphify` | knowledge |
| Manage context budget, multi-agent coordination, debug context failures | `/hs-meta:context-engineering` | workflow |

## Execution / cook (Stage: BUILD)

| When to use | Skill | Tier |
|---|---|---|
| Execute an approved plan by phase — TDD red→green, produce artifacts | `/hs:cook` | workflow |
| Start a new project from scratch → delegate to `hs:plan` + `hs:cook` | `/hs-create:bootstrap` | workflow |
| In-session self-optimizing loop against a measurable metric (no ship) | `/hs-flow:loop` | workflow |
| Run a plan/PRD in unattended AFK mode (Ralph sandbox or native fallback) | `/hs-flow:afk` | workflow |
| Router for the autonomous iteration group → choose loop/plan/discover | `/hs-research:autoresearch` | knowledge |

## Bug fixing / debug (Stage: BUILD)

| When to use | Skill | Tier |
|---|---|---|
| Orchestrate the full error lifecycle: scout→debug→fix→test, gate bug | `/hs:triage` | workflow |
| Fix a specific bug/error or CI failure (cause is already known) | `/hs:fix` | workflow |
| Debug root cause before fixing (cause is not yet known) | `/hs:debug` | workflow |

## Review and gate (Stage: VERIFY)

| When to use | Skill | Tier |
|---|---|---|
| Review diff/commit/full-codebase — verdict blocks the pr/ship/deploy stage | `/hs:code-review` | workflow |
| Review a GitHub PR broadly, supports `--fix` / `--reply` | `/hs:review-pr` | workflow |
| Security scan — hardcoded secrets, CVE, injection/authz, STRIDE+OWASP | `/hs-research:security-scan` | workflow |

## Test (Stage: VERIFY)

| When to use | Skill | Tier |
|---|---|---|
| Run and validate tests for current changes, gate 100% pass | `/hs:test` | workflow |

## Ship (Stage: SHIP)

| When to use | Skill | Tier |
|---|---|---|
| Git commit/push/PR/merge, auto-split, secret scan before commit | `/hs:git` | workflow |
| Ship pipeline with gate: review→verification→human approval→push/pr | `/hs:ship` | workflow |

## Documentation (Stage: DOC)

| When to use | Skill | Tier |
|---|---|---|
| Analyze codebase and manage project docs — init/update/summarize | `/hs-mem:docs` | workflow |
| Look up library/framework docs via llms.txt (context7) | `/hs-mem:docs-seeker` | knowledge |
| Write technical journal entries — decisions, failures, lessons after a session | `/hs-mem:journal` | workflow |
| Work with office files (.docx/.pdf/.pptx/.xlsx) — read/create/edit/fill | `/hs-mem:document-skills` | knowledge |

## Diagram and graph tooling

| When to use | Skill | Tier |
|---|---|---|
| Publish-grade static diagram image (SVG+PNG, 8 styles) to embed in docs/slides | `/hs-viz:tech-graph` | knowledge |
| INLINE diagram in markdown (renders on GitHub/GitLab) via Mermaid.js v11 | `/hs-viz:mermaidjs` | knowledge |
| EDITABLE canvas diagram (`.excalidraw` JSON file, hand-editable) | `/hs-viz:excalidraw` | knowledge |
| EXPLAIN a change or architecture as a diagram (no diagram file delivered) | `/hs-viz:preview` | workflow |

## Orchestrator / coordination (Stage: META)

| When to use | Skill | Tier |
|---|---|---|
| Find the right `hs:*` skill for a task (this skill itself) | `/hs-meta:find-skills` | workflow |
| Coordinate parallel Agent Teams — research/cook/review/debug | `/hs-flow:team` | workflow |
| Track progress, plan status, task hydration, session handoff | `/hs-flow:project-management` | workflow |
| View the file-based kanban for all plans in `plans/` | `/hs-flow:plans-kanban` | workflow |
| Git-data-driven retrospective — velocity, hotspot, code health | `/hs-mem:retro` | workflow |

## AFK / unattended

| When to use | Skill | Tier |
|---|---|---|
| Run a plan/PRD unattended, human reviews at both ends | `/hs-flow:afk` | workflow |
| Multi-iteration self-optimizing loop against a metric (in session) | `/hs-flow:loop` | workflow |
| Router to choose the right autonomous iteration variant | `/hs-research:autoresearch` | knowledge |

## Harness utilities and extension

| When to use | Skill | Tier |
|---|---|---|
| Create or update an `hs:*` skill (SKILL.md, frontmatter, references) | `/hs-create:skill-creator` | workflow |
| Create a harness primitive (hook/rule/schema/data/script/agent) — not a skill | `/hs-create:harness-creator` | workflow |
| Organize files/directories, determine output paths, standardize layout | `/hs-meta:project-organization` | workflow |
| Create, inspect, and clean isolated git worktrees | `/hs-flow:worktree` | workflow |
| Expose existing code as an npm CLI and/or MCP server for agents | `/hs-create:agentize` | knowledge |
| Build or extend an MCP server (FastMCP / MCP SDK) | `/hs-create:mcp-builder` | knowledge |

---

## Role assignment when multiple skills match

- **Clear cause → `hs:fix`; unknown cause → `hs:debug`; full error lifecycle → `hs:triage`.**
- **Small diff/commit → `hs:code-review`; GitHub PR/branch → `hs:review-pr`.**
- **Unfamiliar codebase → `hs:understand` (orchestrate) before `hs:plan`.**
- **Ambiguous problem → `hs-research:discover` before `hs:plan`; multi-source needed → `hs-research:research`.**
- **Diagram: inline-doc → `hs-viz:mermaidjs`; canvas/JSON → `hs-viz:excalidraw`; publish-grade → `hs-viz:tech-graph`; explain a change → `hs-viz:preview`.**
- **Create a skill → `hs-create:skill-creator`; create a hook/script/rule/agent → `hs-create:harness-creator`.**

## Gap report

If no skill matches the intent: clearly state "No skill for [intent]", suggest
a workaround using the nearest skill or native tools. Do not fabricate skills and do not
suggest skills outside the 46 skills listed above.
