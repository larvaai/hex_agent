# two-layer-firewall — the mind↔voice seam

The contract that keeps raw reasoning backstage and lets only a clean conclusion
reach the user. Read this honestly: it is **convention + capability-narrowing +
a file handoff**, not a kernel-enforced wall. In same-session mode the thinker
and the front share one context, so the guarantee is as strong as the discipline
plus the one mechanical lever below — no stronger. Don't oversell it as
"mechanically impossible to leak."

## The seam

```
mind:reason  ──► consolidator writes ──►  symm-harness/state/handoff/conclusion.json  ──► voice:render reads
   (Task)                                         (the ONLY crossing artifact)            (no Task)
```

`conclusion.json` (shape in `plugins/mind/agents/consolidator.md`) is the single artifact
permitted to cross. The front layer's input is that file and nothing else.

## What enforces it (strongest first)

1. **Capability narrowing (mechanical).** `voice:render` has no `Task` in its
   `allowed-tools` — it physically cannot spawn a reasoner or reach back into the
   thinker. It can only re-render text it was handed. This is the one hard lever.
2. **Process isolation.** Each `deep-reasoner` runs in its own `Task` context; its
   raw chain never enters the main transcript — only its compact finding returns.
3. **The file handoff.** `voice:render` reads `conclusion.json`, not the thinker's
   working notes. If the file is absent, render refuses rather than improvising.
4. **Log privacy.** The trace stores `payload_hash`, never the payload
   (`scripts/trace.py`), so even the audit ledger cannot leak the chain.

## What it does NOT guarantee (the honest caveat)

In a single Claude session, the model that ran `mind:reason` still *holds* the
sub-agents' returned findings in context when it later runs `voice:render`.
Nothing at the OS level stops it from re-rendering those raw notes. The defenses
above make leaking the *default-wrong* path, not the impossible one. If you need a
real wall, run `voice:render` in a **fresh context seeded only by
`conclusion.json`** (a separate session / `/clear` between the two) — that, not a
frontmatter key, is the hard version.

## The discipline (what every layer must hold)

- The thinker ends by pointing at the seam — it does not relay raw findings to the
  user.
- The consolidator freezes substance into `conclusion.json`.
- The front re-renders only the seam, changing wording — never substance (the
  scope-fence in `psych-front.md`).
