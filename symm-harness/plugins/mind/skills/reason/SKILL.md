---
name: mind:reason
description: The hidden thinker — decompose a hard problem, dispatch reasoning sub-agents, consolidate their chains into ONE conclusion.json at the seam. Deep technical reasoning lives here and never reaches the user raw.
user-invocable: true
argument-hint: "[problem | question | artifact]"
when_to_use: "Invoke for anything needing real reasoning — a decision, a design, a diagnosis, a judgement. Backstage: produces a structured conclusion, not a user-facing answer. Always hand its output to voice:render."
layer: thinker
logged: true
allowed-tools: Read, Grep, Glob, Bash, Write, WebSearch, WebFetch, Task
metadata:
  owner: symm-harness
  seam: symm-harness/state/handoff/conclusion.json
---

# mind:reason — think hard, backstage

This is the back room. Reason as deeply and technically as the problem demands —
long chains, multiple lenses, dead-ends are all fine here. The user never sees
this. The **only** thing that leaves the room is a `conclusion.json` written to
the seam; `voice:render` turns that into what the user reads.

## The firewall — read first

- You are BACKSTAGE. Nothing you reason here is shown to the user verbatim.
- The ONLY artifact that crosses to `voice/` is
  `symm-harness/state/handoff/conclusion.json` (shape defined in
  `plugins/mind/agents/consolidator.md`).
- Do NOT write a user-facing answer and do NOT polish prose — that is
  `voice:render`'s job. Ending your turn by relaying a sub-agent's raw report to
  the user breaks the firewall. End by pointing at the seam file.

## Process

1. **Decompose** the problem into independent sub-questions / lenses
   (`references/decompose.md`). Trivial problems skip straight to step 4 — don't
   spin up agents for a one-liner.
2. **Dispatch** one `Task → deep-reasoner` per sub-question (and a second lens on
   the same question when an adversarial check earns its keep). Fan as wide as
   the problem needs; each runs in an isolated context and returns a compact
   finding, not its chain.
3. **Consolidate**: `Task → consolidator`, handing it the collected findings. It
   writes the fixed seam `symm-harness/state/handoff/conclusion.json` — the single
   crossing artifact (no session id to thread; the path is constant).
4. **Stop.** Return one line: the seam path + the bottom-line verdict. Do NOT
   render. The next move is `voice:render <seam path>`.

## Boundaries

- Encouraged: depth, technical jargon, many lenses, exploration. This room has
  no readability budget.
- Forbidden: speaking to the user in final voice; spawning render from here;
  softening or shaping the conclusion's substance.
- Every dispatch + skill call is logged (S4/S5) by the hooks — you never log by
  hand.

## References

| Content | Source |
|---|---|
| how to split a problem + fan lenses | `plugins/mind/skills/reason/references/decompose.md` |
| the `conclusion.json` contract | `plugins/mind/agents/consolidator.md` |
| why only the seam crosses | `rules/two-layer-firewall.md` |
