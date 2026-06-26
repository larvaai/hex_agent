---
name: hs-think:predict
description: 5 expert personas independently debate a proposed change before implementation, catching architectural, security, performance, and UX risks early. Use before large features or high-risk changes.
category: think
license: AGPL-3.0
keywords: [predict, expert, personas, independently, debate, proposed]
when_to_use: "Use before large features or high-risk changes."
argument-hint: "<proposal> [--files <glob>] [--chain reason | --chain probe]"
user-invocable: true
allowed-tools: [Read, Grep, Glob, Bash, Write]
metadata:
  owner: harness
  compliance-tier: knowledge
---

# hs-think:predict — Multi-persona analysis before implementation

Five expert personas independently analyze a proposed change, debate conflicts, then converge
on a verdict of **GO / CAUTION / STOP** — before a single line of code is written.

## When to use

- Before implementing a large or high-risk feature
- Before a significant architecture refactor
- When evaluating competing technical approaches
- To check assumptions in a proposed design

## When NOT to use

- Small, low-risk changes (use `hs:debug` for bugs, `hs:plan` for decided work)
- Work that has already been approved with no open design questions
- Pure dependency upgrades that do not change the API
- **Decision is load-bearing AND a mechanical metric exists AND probes are cheap** → escalate to
  `hs-think:bakeoff`. predict is a fast/cheap LLM verdict; bake-off decides by real numbers when guessing is
  too risky to trust to persona debate.

---

## 5 Personas

| Persona | Focus | Core questions |
|---------|-------|----------------|
| **Architect** | System design, scalability, coupling | Does it fit the architecture? Can it scale? What new coupling is introduced? |
| **Security** | Attack surface, data protection, auth boundaries | What can be abused? Where is data exposed? Are auth boundaries intact? |
| **Performance** | Latency, memory, queries, bundle size | Latency impact? N+1 queries? Memory leaks? Bundle bloat? |
| **UX** | User experience, accessibility, error states | Is it intuitive? What do error states look like? Accessible on mobile? |
| **Devil's Advocate** | Hidden assumptions, simpler alternatives | Why not do nothing? What is the simplest option? Which assumptions could be wrong? |

---

## Debate process

1. **Read the proposal** — from the argument or provided file
2. **Read related code** if file paths are given (grep affected areas)
3. **Each persona analyzes independently** — personas must not influence each other in this phase
4. **Identify consensus points** — where all (or >=4) personas agree
5. **Identify conflicts** — where personas disagree meaningfully
6. **Weigh trade-offs** — for each conflict, assess which concern has higher impact
7. **Deliver verdict** — GO / CAUTION / STOP with actionable recommendations

---

## Output

```
## Prediction Report: [proposal name]

## Verdict: GO | CAUTION | STOP

### Consensus points (all personas agree)
- [Point 1]
- [Point 2]

### Conflicts & resolutions

| Topic | Architect | Security | Performance | UX | Devil's Advocate | Resolution |
|-------|-----------|----------|-------------|-----|-----------------|------------|
| [Issue] | [View] | [View] | [View] | [View] | [View] | [Recommendation] |

### Risk summary

| Risk | Severity | Mitigation |
|------|----------|------------|
| [Risk description] | Critical/High/Medium/Low | [Concrete action] |

### Recommendations
1. [Action — reason]
2. [Action — reason]
```

---

## Verdict levels

| Verdict | Meaning |
|---------|---------|
| **GO** | All personas agree, no critical risks, proceed with confidence |
| **CAUTION** | Concerns exist but are manageable — mitigations identified, proceed carefully |
| **STOP** | Unresolved critical issue found — redesign or gather more information before proceeding |

**STOP triggers** (any one of these is sufficient):
- Security: identified auth bypass or data exposure with no viable mitigation
- Architect: identified fundamental design incompatibility requiring significant rework
- Performance: identified unacceptable latency or query explosion with no workaround
- Devil's Advocate: discovered a wrong assumption that invalidates the entire approach

---

## Chain modes (`--chain`)

When the verdict is **CAUTION**, an additional refinement loop can be activated:

| Flag | Purpose | When to use |
|------|---------|-------------|
| `--chain reason` | Subjective refinement loop — generate -> critique -> synthesize -> blind judge -> loop until convergence | CAUTION with subjective trade-offs (architecture, design) |
| `--chain probe` | Mine missing requirements — harvest unstated constraints + assumptions | CAUTION/STOP due to missing constraints or unclear assumptions |

Detailed protocol: `references/chain-modes.md`.

---

## Harness integration

| Next step | Skill | How |
|-----------|-------|-----|
| Create implementation plan | `hs:plan` | Attach Recommendations as constraints for the planner |
| Expand risk scenarios | `hs-think:scenario` | Feed the Risk table as the feature description |

---

## Examples

```
/hs-think:predict "Add WebSocket for real-time notifications"
/hs-think:predict "Migrate auth from JWT to session cookies"
/hs-think:predict "Add multi-tenancy to the database layer"
/hs-think:predict "Replace REST API with GraphQL" --files src/api/**/*.ts

# Chain modes
/hs-think:predict "Choose auth lib: Passport vs Better Auth" --chain reason
/hs-think:predict "Switch from REST to GraphQL" --chain probe
```
