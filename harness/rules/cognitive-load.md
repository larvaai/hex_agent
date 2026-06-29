# cognitive-load — explain complex findings so a human brain absorbs them

Apply when the harness explains something HARD to a person: review verdicts,
report findings, plan narration, architecture answers in the terminal. The reader
is a brain with a small working memory (~4 live items), not a log sink. This rule
decides *what to say and in what order*; it is the structural layer above
`humanizer-and-anti-ai-tells.md` (which strips machine-stiffness sentence by
sentence) and `terminal-voice.md` (which sets harshness and persona).

Advisory, never a gate. It never touches substance: every finding, every
`file:line` / ID / SHA, every number and verbatim quote survives unchanged. You
reshape how it lands, not what it concludes. Same contract as humanizer.

## The five laws

1. **Chunk to working memory.** A reader holds ~4 things at once. Group any
   finding set into <=4 buckets; never force more held at once. A real review of
   a dozen issues collapses to three: *guards declared but not wired* /
   *string-matching where an OS sandbox is needed* / *README overclaims*. Three
   buckets, each carrying its own evidence — the reader can hold the whole shape.

2. **Price the jargon.** A term the whole field decodes on sight (kill-chain,
   sandbox, regex, race, idempotent) is ~free — use it. A term that makes a
   senior stop and translate costs a working-memory slot: drop it, or anchor it
   to a physical image. "a Turing-complete interpreter can't be caged by argv
   regex" → "regex can't cage a thing that runs arbitrary code". Sensitivity
   scales with the term's cost, not its accuracy.

3. **Pain before cure.** An abstract risk does not land; a felt one does. Make
   the reader feel the bite before naming the fix. "secret leaks to the UI and to
   disk, uncensored, in one unbroken chain" lands; "insufficient redaction
   coverage" does not. Verified-by-running beats hypothetical every time — show
   the chain firing.

4. **Every abstraction must cash out.** term -> an image they can see -> a step
   they can take. If it maps to neither, cut it. "you tested the door, not
   whether the door is bolted to the wall" makes an entire class of gap visible
   in one line — that is the bar.

5. **Compress in thinking, not on the page.** Do the reduction silently; ship
   only the distilled result. Length is not depth. Explaining *more* is not
   explaining *clearer* — the wall of text that "covers everything" is the
   failure mode, not the safe choice.

## The move, in order

1. Before writing: ask in your head — is this problem too tangled, is this term
   hard to map? If yes, restructure *now*, in thinking.
2. Bucket the findings (law 1). Pick the <=4 groups a reader can hold.
3. For each term, price it (law 2). Keep the cheap ones, anchor or cut the
   expensive ones.
4. For each finding, lead with the felt cost (law 3), then the concrete
   picture + the step (law 4).
5. Strip everything that does not earn its slot (law 5). Ship the distilled cut.

## Before / after

Before (machine dump): "The system exhibits insufficient input validation at
multiple layers, and the redaction subsystem demonstrates incomplete coverage of
sensitive value classes, resulting in potential exposure vectors."

After (lands): "Three holes line up into one chain: code runs arbitrary input,
outside the jail, with the full environment. A secret printed by that code goes
straight to the UI and onto disk, uncensored. We verified it by running it."

Same facts. The second one you can feel, hold, and act on.

## What NOT to do

- Do not dumb down the substance to hit brevity — cut words, never evidence.
- Do not strip a hard term that is genuinely load-bearing AND has no plain
  synonym; anchor it instead.
- Do not force exactly three buckets when the material is two or four (the
  rule-of-three trap — see humanizer pattern 8). Chunk to the natural seams.
- Do not narrate the compression ("let me simplify this for you"); just deliver
  the compressed version.

## Composition

This rule, `humanizer-and-anti-ai-tells.md`, and `terminal-voice.md` stack:
structure (this) -> sentence polish (humanizer) -> register/persona
(terminal-voice). Run them in that order. None of them moves a number, an ID, or
a gate decision.
