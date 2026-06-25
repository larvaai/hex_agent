# E15 — Acceptance Criteria (draft)

## S15.1 baseline present
- Given any evaluated run, When it completes, Then a simple-answer baseline is recorded next to the full-flow answer.

## S15.2 blind eval
- Given candidate answers, When the evaluator scores, Then it receives anonymized labels (A/B/C), not source names.

## S15.3 theater detection
- Given a run with redundant agents adding no value, When audited, Then the critical auditor flags it with a recommendation.

## S15.4 trace health
- Given repeated identical outputs or a handoff loop, When checked, Then trace-health marks `needs_review` with the cause.

## S15.5 proposal-only
- Given an evolution decision, When produced, Then it is stored as a proposal; no skill/lens/agent file is modified automatically.

## S15.6 human approval
- Given a proposal, When applied, Then it required an explicit approval event (E16) first.
