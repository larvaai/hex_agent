---
name: hs:explain
description: Rewrite a dense technical artifact so a human brain absorbs it — chunk to working memory, price the jargon, lead with felt pain. Use when a report, review, or explanation reads like a wall of jargon.
user-invocable: true
argument-hint: "[file|section]"
when_to_use: "Invoke when a finding, report, review verdict, or explanation is technically correct but does not land — too many items held at once, unanchored jargon, or risk stated abstractly instead of felt."
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs:explain — make hard findings land in a human head

Take one dense artifact (a report, a finding set, a review verdict, a drafted
answer) and reshape it so a small-working-memory reader actually absorbs it. The
five laws live in `harness/rules/cognitive-load.md`; this skill runs them against
a concrete target, then hands off to sentence-level polish.

## Boundaries

- Substance is frozen: every `file:line` / ID / SHA, every number, every verbatim
  quote survives unchanged. Cut words, never evidence.
- If the input already lands (<=4 buckets, jargon priced, pain-first) → say
  "already lands", name why, and STOP. Do not rewrite for its own sake.
- Output reshaped prose only. Do not touch code, tests, or any gate decision.
- One artifact per run. A whole-repo prose audit is out of scope → ask the user
  to point at a specific report or section.

## Backing (real wiring)

- `harness/rules/cognitive-load.md` — the five laws (chunk / price jargon / pain
  before cure / cash out / compress in thinking). Auto-loaded via the live
  rule-routing glob in `inject_prompt_context.py` — drop-in, cannot drift.
- `harness/rules/humanizer-and-anti-ai-tells.md` — sentence polish + the
  Vietnamese calque table, run AFTER structure.
- `harness/scripts/humanize_dashes.py` — mechanical em/en-dash strip (external
  publish or on request).

## Process

1. Locate the target — arg path, named section, or the prose just produced.
   Read it; read `cognitive-load.md`.
2. Restructure (law 1-2): bucket the findings into <=4 groups the reader can
   hold; price every term — keep the cheap, anchor or cut the expensive.
3. Reshape each finding (law 3-4): lead with the felt cost, then the concrete
   picture, then the step. Drop anything that cashes out to neither (law 5).
4. Polish: run `humanizer-and-anti-ai-tells.md` in the configured output
   language; for external publish, `humanize_dashes.py <file> --fix`.
5. Self-check + return: read aloud, confirm <=4 buckets, no orphan jargon, every
   abstraction maps to picture+step. Edit the file in place (or return the inline
   rewrite) + one line naming what changed.

## What this is NOT

- Not `hs-extra:ask` (answers a question) and not `hs:code-review` (judges
  correctness). It changes *delivery*, never the verdict.
- Not a humanizer replacement — humanizer fixes sentences, this fixes the
  information architecture above them. They compose, in that order.

## Quick reference

| Content | Source |
|---|---|
| The five laws + before/after | `harness/rules/cognitive-load.md` |
| Sentence-level tells + calque table | `harness/rules/humanizer-and-anti-ai-tells.md` |
| Em/en-dash strip (mechanical) | `harness/scripts/humanize_dashes.py` |
