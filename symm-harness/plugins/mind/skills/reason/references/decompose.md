# decompose — how the thinker splits a problem and fans lenses

Load-on-demand drawer for `mind:reason`. The goal: cut a hard problem into pieces
each small enough for one sub-agent to answer well, then recombine. Borrowed from
the "decompose-until-trivial" law — hard usually means under-decomposed.

## Split

- **By sub-question.** List the distinct unknowns. One `deep-reasoner` per
  unknown that can be answered independently.
- **By lens, not just by part.** For a judgement (is X correct / safe / worth
  it), the useful split is often *perspectives* — correctness, failure-mode,
  cost, alternative — not sub-parts. Give each lens its own reasoner.
- **Stop splitting when a piece is trivial.** If you can answer it in one pass
  without a tool, don't spawn an agent for it. Agents are for depth, not ceremony.

## Fan width

- 1 reasoner: a focused question with a single right answer.
- 2–4 reasoners: a design or decision with real trade-offs — one per option or
  per lens.
- Add an adversarial second lens (a reasoner told to *refute* the first) only
  when being wrong is expensive. Don't reflexively double every call.

## Recombine

- Hand every finding to `consolidator` — it dedups, ranks, and writes the seam.
- You do not merge by hand and you do not relay raw findings onward. The
  consolidator's `conclusion.json` is the single source the front layer reads.

## Anti-patterns

- Fanning 8 agents at a one-line question (the bloat this harness exists to
  avoid).
- Passing a reasoner's whole chain to the next stage instead of its compact
  finding — that floods context and risks leaking raw reasoning past the seam.
