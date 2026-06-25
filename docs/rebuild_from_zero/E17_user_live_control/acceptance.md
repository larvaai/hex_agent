# E17 — Acceptance Criteria (draft)

## S17.1 mid-run pickup
- Given an active run, When a directive is appended to `control/inbox.jsonl`, Then it is applied before the next agent step.

## S17.2 priority
- Given a user directive conflicting with an agent suggestion, When resolved, Then the user directive wins.

## S17.3 compliance
- Given a directive "stop logging" or "use tool X that doesn't exist", When evaluated, Then it is rejected with a reason.

## S17.4 replan
- Given a directive that changes the goal, When accepted, Then the plan is updated and subsequent steps follow it.

## S17.5 logged
- Given an accepted directive, When applied, Then a `user_directive` event appears in the trace.
