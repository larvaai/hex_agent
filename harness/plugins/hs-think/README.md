<!-- generated: plugin-readme -->

# hs-think

SDLC harness — suy luận / ra quyết định / phản biện (hs-think:brainstorm / predict / scenario / sequential-thinking / problem-solving / critique / bakeoff). Sibling của plugin hs (spine).

**Default:** opt-in. Enable with `hs-cli components --enable think` (or choose it at install time).
**Version:** 2.0.0

## Skills (7)

| Invoke | Purpose |
|---|---|
| `/hs-think:bakeoff` | Empirical bake-off — run 2-4 candidate probes on one mechanical metric, pick the winner by numbers or hand to a human when inside the noise… |
| `/hs-think:brainstorm` | Brainstorm solutions with honest trade-off analysis — ideation, architecture decisions, technical debate, feasibility exploration. |
| `/hs-think:critique` | Multi-lens adversarial critique — fan independent lenses at an artifact, consolidate into one ranked verdict. |
| `/hs-think:predict` | 5 expert personas independently debate a proposed change before implementation, catching architectural, security, performance, and UX risks… |
| `/hs-think:problem-solving` | Structured unblocking — identify the block type, choose the right technique, reframe before resuming implementation. |
| `/hs-think:scenario` | Decompose a feature/code path across 12 dimensions to generate edge cases, risks, and test targets before implementation. |
| `/hs-think:sequential-thinking` | Multi-step analysis with revision — decompose complex problems, verify hypotheses, adjust direction mid-stream. |

Each skill's full contract lives in its `SKILL.md`; load-on-demand detail lives under the skill's `references/`. This index is generated — regenerate with `harness/scripts/generate_plugin_readme.py`.
