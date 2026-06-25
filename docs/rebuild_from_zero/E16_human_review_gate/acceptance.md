# E16 — Acceptance Criteria (draft)

## S16.1 plan gate
- Given a plan awaiting approval, When the reviewer denies with annotations, Then execution does not proceed and the agent receives the feedback.

## S16.2 diff gate
- Given uncommitted changes, When the reviewer annotates lines and approves, Then the annotations are delivered and commit may proceed.

## S16.3 dangerous-action gating
- Given a multi-file edit/refactor, When attempted without approval, Then it is blocked pending review.

## S16.4 skill/lens update gating
- Given an evolution proposal, When apply is requested without approval, Then it is rejected.

## S16.5 structured feedback
- Given reviewer annotations, When sent back, Then the agent ingests them as structured feedback (not free-form copy-paste).
