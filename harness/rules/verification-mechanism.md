# Verification mechanism — evidence rules on-demand (hs:plan/cook/test)

Supplements `harness/rules/harness-contract.md` (posture gate / actor=attribution
/ fail-open-closed are already in the contract — do NOT repeat them). These are the
shared evidence rules.

## 5 verification invariants

Every claim of "done / correct" must be accompanied by **machine-readable evidence**:

1. **Must be anchored**: SHA commit, `file:line`, or real command output. No anchor
   means the claim is `UNVERIFIABLE`.
2. **Downstream rejects UNVERIFIABLE**: the next step (red-team, validate, gate) treats
   an unanchored claim as if it does not exist — do not build further on it.
3. **Artifact is the source, not narration**: verdicts/checks are written to machine-
   readable JSON (`verification.json`, `review-decision.json`), not stated verbally.
4. **Self-report does not self-approve**: the gate reads the artifact plus the verdict
   policy; it does not trust "I PASS" (actor = attribution, not authorization — see
   contract).
5. **Trace keeps a record**: significant steps emit via `trace_log.append_event` (actor
   and ts are resolved automatically).

## No "done" without fresh-run evidence (the human-side discipline)

The 5 invariants gate the *artifact*; this gates *you*, and the machine gate does NOT
replace it. **Iron Law: no completion claim without verification evidence produced in
THIS turn.** If you have not run the proving command in this message, you cannot say it
passes — a stale/partial run, or "should pass", does not count. Violating the letter
is violating the spirit: a paraphrase or an implied "Done!" is still the claim.

Before any "done / fixed / passing": identify the command that proves it → run it fresh
and complete → read the full output and exit code → only then state the claim, evidence
inline.

| Excuse | Reality |
|--------|---------|
| "Should work now" | Run the verification. |
| "I'm confident" / "seems to" | Confidence ≠ evidence. |
| "Just this once" / "I'm tired" | No exceptions. |
| "Linter passed" | Linter ≠ compiler ≠ tests. |
| "Agent said success" | Verify independently — check the diff. |
| "Partial check is enough" | Partial proves nothing. |
| "Different words, so the rule doesn't apply" | Spirit over letter. |

Red flags you are about to claim without proof: "should / probably / seems"; a "Great! /
Perfect! / Done!" before the command ran; about to commit/push/PR unverified; trusting an
agent's success report; a regression test that passed once but never ran the red→green cycle.

## Evidence filter — bidirectional

The same standard applies in both directions:

- **Finding** (red-team/review): no `file:line` or reproducible command means reject.
- **Planner's own position** (open decision Q-x): finalized by analogy, no `file:line`
  means **evidence debt**, not an exempt choice. Tag `[UNVERIFIED]`, bring into
  validate. Without this step, a decision can place the canonical tree OUTSIDE the
  `ownership.yaml` fence zone without any red-team or cook catching it.

## Decisions are sticky (verified + user-owned)

Two classes of decision do NOT get reopened on an abstract objection:

- **Verified decision** — once a choice is backed by source, a test, or an empirical
  check, an audit/red-team raising only an *abstract* concern does NOT reverse it.
  Reverse only on NEW evidence or a changed context; when rejecting the concern,
  state the verification source in one line.
- **User decision** — an explicit user choice (threshold, library, feature scope,
  schema shape, pricing, timeline, compliance choice, UX trade-off) is never silently
  undone. If an audit argues for reversing one, present the original decision, the
  concern, the trade-off, and the concrete options — then wait for the user.

## Artifacts on the filesystem

The gate reads `plans/<plan>/artifacts/*.json` from **disk** (no commit required).
`.gitignore plans/**/*` masks the new plan dir, so artifacts do NOT auto-commit (correct
policy behavior, not a bug).
